"""게이트웨이 호출 본문(payload/헤더/URL)과 실패 시 계약을 검증한다.

Task 7 리뷰 IMPORTANT 4: 기존 테스트는 `_invoke_gateway_json` 을 통째로
monkeypatch 해서 실제로 무엇이 보내지는지 검증하지 않았다. 그 결과
`X-LLM-Caller` 헤더 삭제, temperature/max_tokens 재도입(중복 금지 위반),
`raise_for_status()` 삭제, HTTP 502→500 오격, 모델 하드코딩, `rstrip('/')`
누락, `/health` 필드 삭제, 에러 핸들러를 "3건 지어내기"로 통째로 바꾸는 것까지
전부 테스트 스위트를 통과했다. 이 파일은 `httpx.MockTransport` 로 실제 요청을
가로채 (a) 유선 계약과 (b) 실패 계약을 검증한다.

prescription_api 모듈은 로드 시 ARANGO_PASSWORD 를 요구하므로(env_check),
다른 테스트 파일과 동일하게 import 전에 stub 모드로 고정한다.
"""
import json
import logging
import os

os.environ.setdefault("ARANGO_PASSWORD", "test-only-not-used")
os.environ["LLM_PROVIDER"] = "stub"
os.environ.pop("GOOGLE_API_KEY", None)

import httpx  # noqa: E402
import pytest  # noqa: E402

import prescription_api as pa  # noqa: E402

_REAL_HTTPX_CLIENT = httpx.Client


def _install_transport(monkeypatch, handler):
    """httpx.Client 생성을 가로채 MockTransport 를 주입한다.

    prescription_api.py 는 매 호출마다 `httpx.Client(timeout=...)` 를 새로 만들기
    때문에, 실제 네트워크 없이 요청을 가로채려면 이 지점을 대체해야 한다.
    """

    def _factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return _REAL_HTTPX_CLIENT(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", _factory)


def _success_response(content_obj) -> httpx.Response:
    return httpx.Response(
        200,
        json={"choices": [{"message": {"content": json.dumps(content_obj, ensure_ascii=False)}}]},
    )


_FAKE_PRESCRIPTIONS = {
    "prescriptions": [
        {"rank": 1, "name": "아목시실린캡슐", "prescription_code": "A001", "dosage": "1일 3회", "reason": "발열"},
        {"rank": 2, "name": "미기재", "prescription_code": "미기재", "dosage": "미기재", "reason": "발열"},
        {"rank": 3, "name": "미기재", "prescription_code": "미기재", "dosage": "미기재", "reason": "발열"},
    ]
}


def _real_request(**overrides):
    defaults = dict(
        patient_id="p-gw-1",
        symptoms="발열",
        history="특이사항 없음",
        top_rx=[{"처방명": "아목시실린캡슐", "처방코드": "A001"}],
        fetch_top_rx_from_arango=False,
        fetch_cohort_rx_from_arango=False,
    )
    defaults.update(overrides)
    return pa.PrescriptionRecommendRequest(**defaults)


# ---------------------------------------------------------------------------
# (a) 유선 계약(wire contract)
# ---------------------------------------------------------------------------


def test_gateway_request_wire_contract(monkeypatch):
    """경로 /v1/chat/completions, X-LLM-Caller 헤더, payload 키가 정확히
    {model, response_format, messages} 뿐이고 temperature/top_p/max_tokens 가
    없는지, model 이 LLM_MODEL 과 일치하는지 확인한다."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["headers"] = request.headers
        captured["json"] = json.loads(request.content)
        return _success_response({"choices": "unused"})

    _install_transport(monkeypatch, handler)
    # 끝에 슬래시를 붙여 rstrip('/') 이 실제로 적용되는지도 같이 검증한다.
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", "http://llm-gateway:8003/v1/")

    pa._invoke_gateway_json("system-prompt", "user-prompt", "openai.gpt-5.6-luna")

    assert captured["path"] == "/v1/chat/completions"
    assert captured["headers"].get("x-llm-caller") == "prescription-api"

    payload = captured["json"]
    assert set(payload.keys()) == {"model", "response_format", "messages"}
    assert payload["model"] == "openai.gpt-5.6-luna"
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["messages"] == [
        {"role": "system", "content": "system-prompt"},
        {"role": "user", "content": "user-prompt"},
    ]


def test_gateway_payload_model_follows_llm_model_env_not_hardcoded(monkeypatch):
    """payload 의 model 은 호출자가 넘긴 값(=LLM_MODEL) 을 그대로 실어야 한다.

    하드코딩된 잘못된 모델 문자열로 바뀌는 변이를 잡기 위한 테스트."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["json"] = json.loads(request.content)
        return _success_response({"choices": "unused"})

    _install_transport(monkeypatch, handler)
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", "http://llm-gateway:8003/v1")

    pa._invoke_gateway_json("s", "u", "some-distinctive-model-id")

    assert captured["json"]["model"] == "some-distinctive-model-id"


def test_recommend_real_mode_sends_llm_model_env_as_wire_model(monkeypatch):
    """recommend() 를 통째로 실행했을 때도 게이트웨이로 나가는 model 이
    os.environ['LLM_MODEL'] 과 정확히 일치하는지 확인한다(req.model 무관)."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["json"] = json.loads(request.content)
        return _success_response(_FAKE_PRESCRIPTIONS)

    _install_transport(monkeypatch, handler)
    monkeypatch.setenv("LLM_PROVIDER", "real")
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", "http://llm-gateway:8003/v1")
    monkeypatch.setenv("LLM_MODEL", "openai.gpt-5.6-luna")

    resp = pa.recommend(_real_request(model="gemini-2.5-flash"), x_prescription_eval_trace=None)

    assert captured["json"]["model"] == "openai.gpt-5.6-luna"
    assert resp.llmStatus == "real"


# ---------------------------------------------------------------------------
# (b) 실패 계약(failure contract) — IMPORTANT 1 / IMPORTANT 4
# ---------------------------------------------------------------------------


def test_gateway_502_raises_http_exception_502(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            502,
            json={"error": {"type": "upstream_error", "upstreamStatus": 401, "attempts": 3}},
        )

    _install_transport(monkeypatch, handler)
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", "http://llm-gateway:8003/v1")

    with pytest.raises(pa.HTTPException) as exc_info:
        pa._invoke_gateway_json("s", "u", "openai.gpt-5.6-luna")

    assert exc_info.value.status_code == 502


@pytest.mark.parametrize(
    "upstream_status,attempts",
    [(401, 1), (400, 1), (429, 3)],
)
def test_gateway_502_detail_carries_upstream_status_and_attempts(monkeypatch, upstream_status, attempts):
    """상류 401/400/429 가 전부 동일 문자열로 뭉개지면 안 된다(IMPORTANT 1).

    게이트웨이는 이미 상류 응답을 걷어내고 upstreamStatus/attempts 만 구조화해
    돌려주므로(GC-7 충족됨), 그 값을 detail 에 그대로 실어 운영자가 로그
    타임스탬프로 대조하지 않아도 되게 한다."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            502,
            json={
                "error": {
                    "type": "upstream_error",
                    "upstreamStatus": upstream_status,
                    "attempts": attempts,
                }
            },
        )

    _install_transport(monkeypatch, handler)
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", "http://llm-gateway:8003/v1")

    with pytest.raises(pa.HTTPException) as exc_info:
        pa._invoke_gateway_json("s", "u", "openai.gpt-5.6-luna")

    detail = exc_info.value.detail
    assert f"upstreamStatus={upstream_status}" in detail
    assert f"attempts={attempts}" in detail


def test_gateway_502_different_upstream_statuses_produce_different_details(monkeypatch):
    """리뷰어가 관찰한 핵심 증상: 401/429/타임아웃이 전부
    '게이트웨이 호출 실패: status=502' 로 동일하게 뭉개졌었다."""

    def make_handler(upstream_status, attempts):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                502,
                json={
                    "error": {
                        "type": "upstream_error",
                        "upstreamStatus": upstream_status,
                        "attempts": attempts,
                    }
                },
            )

        return handler

    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", "http://llm-gateway:8003/v1")

    details = []
    for upstream_status, attempts in [(401, 1), (429, 3)]:
        _install_transport(monkeypatch, make_handler(upstream_status, attempts))
        with pytest.raises(pa.HTTPException) as exc_info:
            pa._invoke_gateway_json("s", "u", "openai.gpt-5.6-luna")
        details.append(exc_info.value.detail)

    assert details[0] != details[1]


def test_gateway_502_logs_upstream_body(monkeypatch, caplog):
    """exc.response.text 가 로그에서 사라지면 안 된다(IMPORTANT 1의 핵심 결함).

    게이트웨이 본문은 이미 상류 응답을 걷어낸 구조화된 값이라 로그에 실어도
    안전하다(GC-7)."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            502,
            json={"error": {"type": "upstream_error", "upstreamStatus": 429, "attempts": 2}},
        )

    _install_transport(monkeypatch, handler)
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", "http://llm-gateway:8003/v1")

    with caplog.at_level(logging.ERROR, logger="prescription_api"):
        with pytest.raises(pa.HTTPException):
            pa._invoke_gateway_json("s", "u", "openai.gpt-5.6-luna")

    assert "429" in caplog.text
    assert "upstream_error" in caplog.text


def test_recommend_real_mode_propagates_gateway_failure_instead_of_fabricating(monkeypatch):
    """GC-2 핵심: 게이트웨이 장애를 삼키고 지어낸 처방을 llmStatus="real" 로
    내보내면 안 된다. recommend() 전체 경로에서 502가 그대로 올라와야 한다."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            502,
            json={"error": {"type": "upstream_error", "upstreamStatus": 500, "attempts": 3}},
        )

    _install_transport(monkeypatch, handler)
    monkeypatch.setenv("LLM_PROVIDER", "real")
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", "http://llm-gateway:8003/v1")

    with pytest.raises(pa.HTTPException) as exc_info:
        pa.recommend(_real_request(), x_prescription_eval_trace=None)

    assert exc_info.value.status_code == 502


# ---------------------------------------------------------------------------
# IMPORTANT 2 — req.model / req.temperature 가 무시될 때 흔적을 남긴다
# ---------------------------------------------------------------------------


def test_recommend_traces_ignored_request_model_and_temperature(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return _success_response(_FAKE_PRESCRIPTIONS)

    _install_transport(monkeypatch, handler)
    monkeypatch.setenv("LLM_PROVIDER", "real")
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", "http://llm-gateway:8003/v1")
    monkeypatch.setenv("LLM_MODEL", "openai.gpt-5.6-luna")

    req = _real_request(model="gemini-2.5-flash", temperature=0.9)

    resp = pa.recommend(req, x_prescription_eval_trace="true")

    llm_generate = next(t for t in resp.toolTrace if t["tool"] == "llm_generate")
    assert llm_generate["model"] == "openai.gpt-5.6-luna", "trace 의 model 은 실제로 보낸 모델이어야 한다"
    assert llm_generate.get("ignoredRequestModel") == "gemini-2.5-flash"
    assert llm_generate.get("ignoredTemperature") == 0.9


def test_recommend_does_not_flag_ignored_fields_when_absent(monkeypatch):
    """req.model/temperature 를 아예 안 보내면 ignored* 필드도 없어야 한다(노이즈 방지)."""

    def handler(request: httpx.Request) -> httpx.Response:
        return _success_response(_FAKE_PRESCRIPTIONS)

    _install_transport(monkeypatch, handler)
    monkeypatch.setenv("LLM_PROVIDER", "real")
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", "http://llm-gateway:8003/v1")
    monkeypatch.setenv("LLM_MODEL", "openai.gpt-5.6-luna")

    resp = pa.recommend(_real_request(), x_prescription_eval_trace="true")

    llm_generate = next(t for t in resp.toolTrace if t["tool"] == "llm_generate")
    assert "ignoredRequestModel" not in llm_generate
    assert "ignoredTemperature" not in llm_generate


# ---------------------------------------------------------------------------
# /health 계약 — llm_gateway_configured 삭제 변이를 잡는다
# ---------------------------------------------------------------------------


def test_health_reports_llm_gateway_configured(monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", "http://llm-gateway:8003/v1")
    client = TestClient(pa.app)
    body = client.get("/health").json()
    assert "llm_gateway_configured" in body
    assert body["llm_gateway_configured"] is True
