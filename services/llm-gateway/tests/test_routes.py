import json
import logging

import httpx
import pytest
from fastapi.testclient import TestClient

import app.main as main


@pytest.fixture()
def client(monkeypatch):
    """상류를 MockTransport 로 바꿔치기한 앱 클라이언트."""

    def _make(handler):
        def _fake_client(**_kwargs):
            return httpx.AsyncClient(transport=httpx.MockTransport(handler))

        monkeypatch.setattr(main, "make_upstream_client", _fake_client)
        return TestClient(main.app)

    return _make


def test_health_returns_ok():
    with TestClient(main.app) as c:
        response = c.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_chat_completions_forwards_and_returns_upstream_body(client):
    def handler(_request):
        return httpx.Response(200, json={"choices": [{"message": {"content": "hi"}}]})

    with client(handler) as c:
        response = c.post(
            "/v1/chat/completions",
            json={"model": "m", "messages": [], "temperature": 0.7},
            headers={"X-LLM-Caller": "validation-agent"},
        )
    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"] == "hi"


def test_temperature_is_stripped_before_upstream(client):
    seen = {}

    def handler(request):
        seen["body"] = request.read().decode()
        return httpx.Response(200, json={"ok": True})

    with client(handler) as c:
        c.post(
            "/v1/chat/completions",
            json={"model": "m", "messages": [], "temperature": 0.7},
        )
    assert "temperature" not in seen["body"]
    assert "reasoning_effort" in seen["body"]


def test_upstream_4xx_becomes_502_without_leaking_key(client):
    def handler(_request):
        return httpx.Response(400, text="bad request")

    with client(handler) as c:
        response = c.post("/v1/chat/completions", json={"model": "m", "messages": []})
    assert response.status_code == 502
    assert "Bearer" not in response.text


def test_upstream_failure_is_logged_as_failed(client, caplog):
    def handler(_request):
        return httpx.Response(400, text="bad request")

    # llm-gateway 로거는 명시적 레벨이 없어 effective level 이 이 로거의 레벨 미설정로
    # 풀린다. caplog 만으로는 INFO 레코드가 애초에 발생하지 않으므로 로거
    # 레벨도 함께 낮춰야 한다.
    with caplog.at_level(logging.INFO, logger="llm-gateway"):
        with client(handler) as c:
            c.post("/v1/chat/completions", json={"model": "m", "messages": []})
    assert any("failed" in rec.getMessage() for rec in caplog.records)


def test_param_notes_reach_log_record(client, caplog):
    """GC-2: build_record 가 param_notes 를 검증할 수 없으므로, 라우트가
    실제로 그것을 넘기는지는 이 테스트만 확인한다. build_record 호출부에서
    param_notes=[] 를 넘기는 회귀가 생겨도 경고 로그(test_temperature_is_...
    류)는 여전히 찍히므로 이 assert 가 없으면 아무 테스트도 못 잡는다."""

    def handler(_request):
        return httpx.Response(200, json={"ok": True})

    with caplog.at_level(logging.INFO, logger="llm-gateway"):
        with client(handler) as c:
            c.post(
                "/v1/chat/completions",
                json={"model": "m", "messages": [], "temperature": 0.7},
            )

    payloads = []
    for rec in caplog.records:
        try:
            payloads.append(json.loads(rec.getMessage()))
        except (json.JSONDecodeError, TypeError):
            continue

    assert any(
        isinstance(payload, dict) and "dropped:temperature" in payload.get("paramNotes", [])
        for payload in payloads
    ), "temperature 드롭 기록이 계측 로그(paramNotes)에 실제로 실려야 한다"


# 계측이 실제로 나가는지.
#
# 설정 전에는 루트 로거가 WARNING 이고 핸들러가 없어서, uvicorn 기본 설정에서도
# logger.info() 로 내보내는 계측 레코드가 통째로 유실됐다. warning 은 lastResort 로
# stderr 에 나가기 때문에 유실이 눈에 안 띄는 종류의 결함이었다.
def test_gateway_logger_has_its_own_handler():
    """계측이 나가려면 이 로거 자신이 INFO 이고 핸들러를 가져야 한다.

    capsys 로는 검증할 수 없다 — 핸들러가 import 시점의 sys.stdout 을 붙들기
    때문이고 그건 컨테이너에서 옳은 동작이다. 그래서 속성을 단언한다.
    """
    import logging

    lg = logging.getLogger("llm-gateway")
    assert lg.level <= logging.INFO
    assert any(getattr(h, "_llm_gateway", False) for h in lg.handlers)


def test_root_logger_is_not_touched():
    """루트를 건드리면 NOTSET 인 모든 서드파티 로거의 바닥이 함께 올라간다."""
    import logging

    root = logging.getLogger()
    assert not any(getattr(h, "_llm_gateway", False) for h in root.handlers)


def test_third_party_info_logs_stay_suppressed():
    """httpx 는 상류 호출마다 INFO 로 한 줄씩 찍는다.

    루트 레벨을 올렸을 때 이 줄들이 계측 JSON 사이에 평문으로 끼어들어
    "한 줄에 JSON 하나" 가 깨졌다. 그 회귀를 고정한다.
    """
    import logging

    assert not logging.getLogger("httpx").isEnabledFor(logging.INFO)


def test_emitted_lines_are_all_json(client):
    """이 로거가 내보내는 모든 줄은 JSON 으로 파싱돼야 한다.

    계측 레코드와 파라미터 경고가 같은 스트림을 공유하므로, 한쪽이 평문이면
    스트림을 파싱하는 쪽이 그 줄에서 깨진다.
    """
    import io
    import json as json_mod
    import logging

    lg = logging.getLogger("llm-gateway")
    buffer = io.StringIO()
    probe = logging.StreamHandler(buffer)
    probe.setFormatter(logging.Formatter("%(message)s"))
    lg.addHandler(probe)
    try:
        def handler(_request):
            return httpx.Response(
                200, json={"ok": True, "usage": {"prompt_tokens": 3, "completion_tokens": 2}}
            )

        with client(handler) as c:
            c.post(
                "/v1/chat/completions",
                json={"model": "m", "messages": [], "temperature": 0.7},
            )
    finally:
        lg.removeHandler(probe)

    lines = [line for line in buffer.getvalue().splitlines() if line.strip()]
    assert len(lines) >= 2, "경고와 계측 레코드 둘 다 나와야 한다"
    for line in lines:
        json_mod.loads(line)  # 파싱 실패하면 그 자체가 실패다


def test_metering_record_content_reaches_the_log(client, caplog):
    import logging

    def handler(_request):
        return httpx.Response(
            200, json={"ok": True, "usage": {"prompt_tokens": 10, "completion_tokens": 5}}
        )

    with caplog.at_level(logging.INFO, logger="llm-gateway"):
        with client(handler) as c:
            c.post(
                "/v1/chat/completions",
                json={"model": "m", "messages": []},
                headers={"X-LLM-Caller": "validation-agent"},
            )
    logged = " ".join(rec.getMessage() for rec in caplog.records)
    assert "estimatedCostUsd" in logged
    assert "validation-agent" in logged


def test_info_level_is_enabled_without_extra_setup():
    """caplog.at_level 같은 보조 없이도 INFO 가 살아 있어야 한다."""
    import logging

    assert logging.getLogger("llm-gateway").isEnabledFor(logging.INFO)
