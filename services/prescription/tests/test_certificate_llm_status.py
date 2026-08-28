"""CertificateGenerateResponse.llmStatus 와 게이트웨이 호출 계약을 검증한다.

Task 7 리뷰(services/prescription/tests/test_gateway_call.py 서문 참조)에서
확인된 함정을 certificate 이관에도 그대로 적용한다:
- `_invoke_gateway_text` 를 통째로 monkeypatch 하면 X-LLM-Caller 헤더 삭제,
  temperature 재도입, 에러 핸들러를 "지어낸 진단서로 교체" 같은 변이가
  테스트를 전부 통과시킬 수 있다. 여기서는 `httpx.MockTransport` 로 실제
  요청을 가로채 유선 계약과 실패 계약을 모두 검증한다.
- httpx.HTTPStatusError 분기와 순수 ``except Exception``(타임아웃/커넥션 실패)
  분기를 모두 커버한다. 하나만 커버하면 다른 쪽에서 "지어낸 응답 반환"으로
  바꿔도 초록불이 나온다.
"""
import json
import logging
import os

import httpx  # noqa: E402
import pytest  # noqa: E402

import certificate_api as ca  # noqa: E402
from certificate_api import CertificateGenerateResponse  # noqa: E402

_REAL_HTTPX_CLIENT = httpx.Client


def _install_transport(monkeypatch, handler):
    """httpx.Client 생성을 가로채 MockTransport 를 주입한다.

    certificate_api.py 는 매 호출마다 httpx.Client(timeout=...) 를 새로 만들기
    때문에, 실제 네트워크 없이 요청을 가로채려면 이 지점을 대체해야 한다.
    """

    def _factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return _REAL_HTTPX_CLIENT(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", _factory)


def _success_response(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def _request(**overrides):
    defaults = dict(
        history_id=1,
        certificate_type="GENERAL",
        patient_name="홍길동",
        patient_age=30,
        patient_gender="남",
        entry_date="2026-08-28",
        symptom_detail="발열",
        diagnosis_kind="최종 진단",
        purpose="회사 제출용",
        diseases=[{"code": "J00", "name": "급성 비인두염"}],
        diagnoses=[{"code": "A001", "name": "아목시실린캡슐", "dose": 500, "time": 3, "days": 3}],
    )
    defaults.update(overrides)
    return ca.CertificateGenerateRequest(**defaults)


# ---------------------------------------------------------------------------
# 응답 모델
# ---------------------------------------------------------------------------


def test_response_model_has_llm_status():
    assert "llmStatus" in CertificateGenerateResponse.model_fields


def test_llm_status_defaults_to_real():
    response = CertificateGenerateResponse(medicalCertificate="본문")
    assert response.llmStatus == "real"


# ---------------------------------------------------------------------------
# 유선 계약(wire contract)
# ---------------------------------------------------------------------------


def test_gateway_request_wire_contract(monkeypatch):
    """경로 /v1/chat/completions, X-LLM-Caller 헤더, payload 키가 정확히
    {model, messages} 뿐이고 temperature/top_p/max_tokens/response_format 이
    없는지, model 이 넘긴 값과 일치하는지 확인한다."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["headers"] = request.headers
        captured["json"] = json.loads(request.content)
        return _success_response("소견 본문")

    _install_transport(monkeypatch, handler)
    # 끝에 슬래시를 붙여 rstrip('/') 이 실제로 적용되는지도 같이 검증한다.
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", "http://llm-gateway:8003/v1/")

    result = ca._invoke_gateway_text("system-prompt", "user-prompt", "openai.gpt-5.6-luna")

    assert result == "소견 본문"
    assert captured["path"] == "/v1/chat/completions"
    assert captured["headers"].get("x-llm-caller") == "certificate-api"

    payload = captured["json"]
    assert set(payload.keys()) == {"model", "messages"}
    assert payload["model"] == "openai.gpt-5.6-luna"
    assert payload["messages"] == [
        {"role": "system", "content": "system-prompt"},
        {"role": "user", "content": "user-prompt"},
    ]


def test_gateway_payload_model_follows_argument_not_hardcoded(monkeypatch):
    """payload 의 model 은 호출자가 넘긴 값을 그대로 실어야 한다.

    하드코딩된 잘못된 모델 문자열로 바뀌는 변이를 잡기 위한 테스트."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["json"] = json.loads(request.content)
        return _success_response("본문")

    _install_transport(monkeypatch, handler)
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", "http://llm-gateway:8003/v1")

    ca._invoke_gateway_text("s", "u", "some-distinctive-model-id")

    assert captured["json"]["model"] == "some-distinctive-model-id"


def test_generate_certificate_real_mode_sends_llm_model_env_as_wire_model(monkeypatch):
    """generate_certificate() 를 통째로 실행했을 때도 게이트웨이로 나가는
    model 이 os.environ['LLM_MODEL'] 과 정확히 일치하는지, llmStatus 가
    "real" 인지 확인한다."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["json"] = json.loads(request.content)
        return _success_response("치료 내용 및 향후 치료에 대한 소견입니다.")

    _install_transport(monkeypatch, handler)
    monkeypatch.setenv("LLM_PROVIDER", "real")
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", "http://llm-gateway:8003/v1")
    monkeypatch.setenv("LLM_MODEL", "openai.gpt-5.6-luna")

    resp = ca.generate_certificate(_request())

    assert captured["json"]["model"] == "openai.gpt-5.6-luna"
    assert resp.llmStatus == "real"
    assert resp.medicalCertificate == "치료 내용 및 향후 치료에 대한 소견입니다."


# ---------------------------------------------------------------------------
# 실패 계약(failure contract)
# ---------------------------------------------------------------------------


def test_gateway_502_raises_http_exception_502(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            502,
            json={"error": {"type": "upstream_error", "upstreamStatus": 401, "attempts": 3}},
        )

    _install_transport(monkeypatch, handler)
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", "http://llm-gateway:8003/v1")

    with pytest.raises(ca.HTTPException) as exc_info:
        ca._invoke_gateway_text("s", "u", "openai.gpt-5.6-luna")

    assert exc_info.value.status_code == 502


@pytest.mark.parametrize(
    "upstream_status,attempts",
    [(401, 1), (400, 1), (429, 3)],
)
def test_gateway_502_detail_carries_upstream_status_and_attempts(monkeypatch, upstream_status, attempts):
    """상류 401/400/429 가 전부 동일 문자열로 뭉개지면 안 된다. 게이트웨이는
    이미 상류 응답을 걷어내고 upstreamStatus/attempts 만 구조화해 돌려주므로
    (GC-7 충족됨), 그 값을 detail 에 그대로 실어 운영자가 대조할 수 있게 한다."""

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

    with pytest.raises(ca.HTTPException) as exc_info:
        ca._invoke_gateway_text("s", "u", "openai.gpt-5.6-luna")

    detail = exc_info.value.detail
    assert f"upstreamStatus={upstream_status}" in detail
    assert f"attempts={attempts}" in detail


def test_gateway_502_logs_upstream_body(monkeypatch, caplog):
    """exc.response.text 가 로그에서 사라지면 안 된다. 게이트웨이 본문은 이미
    상류 응답을 걷어낸 구조화된 값이라 로그에 실어도 안전하다(GC-7)."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            502,
            json={"error": {"type": "upstream_error", "upstreamStatus": 429, "attempts": 2}},
        )

    _install_transport(monkeypatch, handler)
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", "http://llm-gateway:8003/v1")

    with caplog.at_level(logging.ERROR, logger="certificate_api"):
        with pytest.raises(ca.HTTPException):
            ca._invoke_gateway_text("s", "u", "openai.gpt-5.6-luna")

    assert "429" in caplog.text
    assert "upstream_error" in caplog.text


def test_gateway_502_non_json_body_falls_back_to_raw_text_in_detail(monkeypatch):
    """상류가 502 를 주면서 JSON 이 아닌 본문(HTML 에러 페이지 등)을 돌려주면,
    error_body 파싱이 실패해 ``detail += f" body={body}"`` 폴백으로 빠져야
    한다. 이 폴백 라인을 지우는 변이를 잡는다."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="<html><body>Bad Gateway</body></html>")

    _install_transport(monkeypatch, handler)
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", "http://llm-gateway:8003/v1")

    with pytest.raises(ca.HTTPException) as exc_info:
        ca._invoke_gateway_text("s", "u", "openai.gpt-5.6-luna")

    assert exc_info.value.status_code == 502
    assert "body=" in exc_info.value.detail
    assert "Bad Gateway" in exc_info.value.detail


def test_gateway_connect_timeout_raises_502_with_reason_preserved(monkeypatch):
    """``except httpx.HTTPStatusError`` 만 덮으면, 타임아웃/커넥션 실패/
    (200이지만 형식이 깨진) 응답이 모두 떨어지는 ``except Exception`` 분기가
    무커버리지로 남는다. 이 분기의 detail 이 ``f"...: {exc}"`` 형태를
    유지하는지(사유가 사라지지 않는지) 확인한다."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out", request=request)

    _install_transport(monkeypatch, handler)
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", "http://llm-gateway:8003/v1")

    with pytest.raises(ca.HTTPException) as exc_info:
        ca._invoke_gateway_text("s", "u", "openai.gpt-5.6-luna")

    assert exc_info.value.status_code == 502
    assert "timed out" in exc_info.value.detail


def test_generate_certificate_real_mode_propagates_gateway_failure_instead_of_fabricating(monkeypatch):
    """GC-2 핵심: 게이트웨이 장애를 삼키고 지어낸 진단서를 llmStatus="real" 로
    내보내면 안 된다. generate_certificate() 전체 경로에서 502가 그대로
    올라와야 한다."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            502,
            json={"error": {"type": "upstream_error", "upstreamStatus": 500, "attempts": 3}},
        )

    _install_transport(monkeypatch, handler)
    monkeypatch.setenv("LLM_PROVIDER", "real")
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", "http://llm-gateway:8003/v1")

    with pytest.raises(ca.HTTPException) as exc_info:
        ca.generate_certificate(_request())

    assert exc_info.value.status_code == 502


def test_generate_certificate_real_mode_propagates_connect_error_instead_of_fabricating(monkeypatch):
    """게이트웨이 컨테이너 재기동 중 커넥션이 거부되는 상황이 재현 가능한
    시나리오다. ``except Exception`` 분기를 "지어낸 진단서 반환" 으로 바꾼
    변이를 이 테스트가 잡아야 한다."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    _install_transport(monkeypatch, handler)
    monkeypatch.setenv("LLM_PROVIDER", "real")
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", "http://llm-gateway:8003/v1")

    with pytest.raises(ca.HTTPException) as exc_info:
        ca.generate_certificate(_request())

    assert exc_info.value.status_code == 502
    assert "refused" in exc_info.value.detail


def test_invoke_gateway_text_missing_base_url_raises_503(monkeypatch):
    monkeypatch.delenv("LLM_GATEWAY_BASE_URL", raising=False)

    with pytest.raises(ca.HTTPException) as exc_info:
        ca._invoke_gateway_text("s", "u", "openai.gpt-5.6-luna")

    assert exc_info.value.status_code == 503


# ---------------------------------------------------------------------------
# llmStatus 실행 경로 검증
# ---------------------------------------------------------------------------


def test_stub_provider_reports_llm_status_stub(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "stub")

    resp = ca.generate_certificate(_request())

    assert resp.llmStatus == "stub"


def test_real_provider_reports_llm_status_real(monkeypatch):
    """게이트웨이 호출이 실제로 성공한 경로에서만 "real" 이 나오는지 본다."""

    def handler(request: httpx.Request) -> httpx.Response:
        return _success_response("실제 게이트웨이 응답입니다.")

    _install_transport(monkeypatch, handler)
    monkeypatch.setenv("LLM_PROVIDER", "real")
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", "http://llm-gateway:8003/v1")

    resp = ca.generate_certificate(_request())

    assert resp.llmStatus == "real"
    assert resp.medicalCertificate == "실제 게이트웨이 응답입니다."


# ---------------------------------------------------------------------------
# /health 계약
# ---------------------------------------------------------------------------


def test_health_reports_llm_gateway_configured(monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", "http://llm-gateway:8003/v1")
    client = TestClient(ca.app)
    body = client.get("/health").json()
    assert "llm_gateway_configured" in body
    assert body["llm_gateway_configured"] is True
