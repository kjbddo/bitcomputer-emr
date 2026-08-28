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

Task 8 리뷰(CRITICAL C1 / IMPORTANT I2)에서 추가된 함정:
- 게이트웨이가 200 을 주면서 `content: null`/`""`/비문자열을 돌려주면
  `str(response.json()[...]["content"]).strip()` 이 `"None"` 같은 지어낸
  문자열을 진짜 진단서 소견으로 통과시킨다. 이 케이스가 무커버리지였다
  (표 기반 테스트로 각 행을 고정한다).
"""
import json
import logging

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


def _success_response(content) -> httpx.Response:
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


def test_llm_status_field_is_required_with_no_default():
    """MINOR: prescription 의 PrescriptionRecommendResponse.llmStatus 와 동일한
    강도로 맞춘다 — 기본값이 있으면 생성 시 값을 빠뜨려도 "모델이 실제로
    판단했다"는 거짓 신호를 조용히 내보낼 수 있다(GC-2).

    이 테스트는 브리프 Step 1 이 지시한 `test_llm_status_defaults_to_real`
    (기본값 "real" 이 존재함을 전제로 한 테스트) 을 대체한다 — 그 테스트는
    위험한 기본값의 존재 자체를 고정하고 있었으므로 삭제했다."""
    field = CertificateGenerateResponse.model_fields["llmStatus"]
    assert field.is_required(), "llmStatus 에 기본값이 있으면 안 된다 — 값을 빠뜨려도 조용히 통과해서는 안 된다"


def test_llm_status_field_enum_is_pinned_to_real_or_stub():
    """`Literal["real", "stub"]` 를 `str` 로 되돌리는 변이를 잡는다 — OpenAPI
    스키마의 enum 자체를 고정한다(prescription MINOR 9 와 동일 패턴)."""
    schema = CertificateGenerateResponse.model_json_schema()
    llm_status_schema = schema["properties"]["llmStatus"]
    assert llm_status_schema.get("enum") == ["real", "stub"]
    assert schema["required"] and "llmStatus" in schema["required"]


# ---------------------------------------------------------------------------
# 유선 계약(wire contract)
# ---------------------------------------------------------------------------


def test_gateway_request_wire_contract(monkeypatch):
    """경로 /v1/chat/completions, X-LLM-Caller 헤더, payload 키가 정확히
    {model, messages} 뿐이고 temperature/top_p/max_tokens/response_format 이
    없는지, model 이 넘긴 값과 일치하는지, Authorization 헤더가 없는지(GC-7)
    확인한다."""
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
    # N9 (GC-7): 게이트웨이가 자격증명을 갖는다 — 호출자가 Authorization 을
    # 실어 보내면 자격증명이 이중으로 흩어지고, 게이트웨이가 이를 덮어쓰지
    # 않는 구현이면 잘못된/새어나간 값이 그대로 상류로 나갈 수 있다.
    assert "authorization" not in captured["headers"]

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


def test_gateway_success_content_is_stripped(monkeypatch):
    """M7: 응답 content 양끝 공백/개행이 .strip() 되어야 한다."""

    def handler(request: httpx.Request) -> httpx.Response:
        return _success_response("  진단서 본문입니다.  \n")

    _install_transport(monkeypatch, handler)
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", "http://llm-gateway:8003/v1")

    result = ca._invoke_gateway_text("s", "u", "openai.gpt-5.6-luna")

    assert result == "진단서 본문입니다."


def test_generate_certificate_real_mode_sends_llm_model_env_as_wire_model(monkeypatch):
    """generate_certificate() 를 통째로 실행했을 때도 게이트웨이로 나가는
    model 이 os.environ['LLM_MODEL'] 과 정확히 일치하는지, llmStatus 가
    "real" 인지 확인한다.

    N12: LLM_MODEL 을 하드코딩된 기본값("openai.gpt-5.6-luna")과 다른 값으로
    설정해야 이 테스트가 비어있지(vacuous) 않다 — 같은 값이면 하드코딩된
    기본값이 우연히 일치해도 테스트가 통과한다."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["json"] = json.loads(request.content)
        return _success_response("치료 내용 및 향후 치료에 대한 소견입니다.")

    _install_transport(monkeypatch, handler)
    monkeypatch.setenv("LLM_PROVIDER", "real")
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", "http://llm-gateway:8003/v1")
    monkeypatch.setenv("LLM_MODEL", "distinct-model-for-test-xyz")

    resp = ca.generate_certificate(_request())

    assert captured["json"]["model"] == "distinct-model-for-test-xyz"
    assert resp.llmStatus == "real"
    assert resp.medicalCertificate == "치료 내용 및 향후 치료에 대한 소견입니다."


def test_health_default_model_matches_wire_model_from_same_env(monkeypatch):
    """N12: certificate_api.py:61(import 시점)과 :207(호출 시점)이 각각
    LLM_MODEL 을 따로 읽던 중복을 없앤다 — /health 가 보고하는
    default_model 이 실제로 유선에 실리는 model 과 항상 같은 값이어야
    한다. import 시점 상수를 쓰면, 이 테스트에서 monkeypatch.setenv 가
    "import 이후" 에 일어나므로 값이 어긋나 실패한다."""
    from fastapi.testclient import TestClient

    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", "http://llm-gateway:8003/v1")
    monkeypatch.setenv("LLM_MODEL", "distinct-model-for-test-xyz")

    client = TestClient(ca.app)
    body = client.get("/health").json()

    assert body["default_model"] == "distinct-model-for-test-xyz"


def test_default_llm_model_fallback_when_env_absent(monkeypatch):
    """M5(X9 변이): ``_default_llm_model()`` 의 폴백 기본값을
    "gemini-2.0-flash" 등으로 바꿔도 모든 model 테스트가 LLM_MODEL 을
    명시적으로 설정해서 무커버리지였다. infra/docker-compose.yml 은
    ``${LLM_MODEL:-openai.gpt-5.6-luna}`` 로 기본값을 제공하지만, 실제로
    적용되는 건 Python 쪽 기본값이다 — LLM_GATEWAY_BASE_URL 만 주입하고
    LLM_MODEL 은 주입하지 않는 EmbeddedPrescriptionAgentStarter 경로에서
    이 기본값이 그대로 쓰인다."""
    monkeypatch.delenv("LLM_MODEL", raising=False)

    assert ca._default_llm_model() == "openai.gpt-5.6-luna"


def test_gateway_uses_llm_timeout_seconds_env(monkeypatch):
    """M5: timeout 이 하드코딩되지 않고 LLM_TIMEOUT_SECONDS 를 반영해야 한다."""
    captured_kwargs: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        return _success_response("본문")

    def _factory(*args, **kwargs):
        captured_kwargs.update(kwargs)
        kwargs["transport"] = httpx.MockTransport(handler)
        return _REAL_HTTPX_CLIENT(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", _factory)
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", "http://llm-gateway:8003/v1")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "37")

    ca._invoke_gateway_text("s", "u", "openai.gpt-5.6-luna")

    assert captured_kwargs.get("timeout") == 37.0


def test_gateway_invalid_timeout_env_raises_clean_error_not_500(monkeypatch):
    """certificate_api.py:143 — LLM_TIMEOUT_SECONDS 가 숫자가 아니면 try 밖에서
    ValueError 가 그대로 터져 트레이스백이 노출된 500 이 나갔다. 여기서는
    깔끔한 HTTPException(503) 으로 바뀌어야 한다.

    M1(T2 변이): 잘못된 LLM_TIMEOUT_SECONDS 를 조용히 180.0 으로 되돌리는 변이가
    `in (502, 503)` 이라는 느슨한 disjunction 때문에 살아남았다 — 파싱이 더 이상
    실패하지 않으면 MockTransport 없이 실제 httpx.Client 가 llm-gateway:8003 에
    접속을 시도하고, DNS/커넥션 실패가 ``except Exception`` 에서 502 로 잡혀
    disjunction 을 통과했다(4.55s vs 기준 ~1.5s 가 그 커넥트 타임아웃이었다).
    여기서는 == 503 으로 좁히고, 소켓에 닿을 수 없도록 MockTransport 를 설치해
    파싱이 실패하지 않는 한 이 테스트가 절대 통과할 수 없게 한다."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(
            "LLM_TIMEOUT_SECONDS 파싱이 실패하면 httpx.Client 자체가 생성되지 "
            "않아야 한다 — 이 handler 가 호출됐다는 건 파싱 실패가 503 으로 "
            "떨어지지 않고 실제 요청 경로까지 흘러갔다는 뜻이다."
        )

    _install_transport(monkeypatch, handler)
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", "http://llm-gateway:8003/v1")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "not-a-number")

    with pytest.raises(ca.HTTPException) as exc_info:
        ca._invoke_gateway_text("s", "u", "openai.gpt-5.6-luna")

    assert exc_info.value.status_code == 503


# ---------------------------------------------------------------------------
# CRITICAL C1 / IMPORTANT I2 — 200 이지만 형식이 깨진 본문
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "body,description",
    [
        ({"choices": [{"message": {"content": None}}]}, "content-null"),
        ({"choices": [{"message": {"content": ""}}]}, "content-empty-string"),
        ({"choices": [{"message": {"content": "   \n\t"}}]}, "content-whitespace-only"),
        ({"choices": [{"message": {"content": {"text": "x"}}}]}, "content-non-string-dict"),
        ({"choices": [{"message": {"content": 42}}]}, "content-non-string-number"),
        ({"choices": [{"message": {"content": ["a", "b"]}}]}, "content-non-string-list"),
        ({"error": {"type": "no-choices-key"}}, "missing-choices-key"),
        ({"choices": []}, "empty-choices-list"),
        ({"choices": [{"message": {}}]}, "missing-content-key"),
        ({"choices": [{}]}, "missing-message-key"),
    ],
)
def test_gateway_200_malformed_body_raises_502_not_fabricated(monkeypatch, body, description):
    """CRITICAL C1 표의 모든 행 + IMPORTANT I2 가 지시한 누락 케이스들.

    HTTP 200 이지만 본문 형식이 깨져 있으면, 절대 "None"/빈 문자열/딕셔너리를
    str() 로 뭉갠 값을 진짜 진단서 소견으로 반환하면 안 된다 — 502 로
    떨어져야 한다.

    M3(G7 변이): ``raise ValueError("빈 본문")`` 처럼 ``content!r`` 사유를 빼도
    status_code == 502 만 보는 assert 는 통과했다. 사유가 사라지면 운영자는
    상류가 null/""/모양이 바뀐 것 중 무엇을 돌려줬는지 구분할 수 없다 — 행마다
    detail 안에 실제 사유가 남아있는지 고정한다."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    _install_transport(monkeypatch, handler)
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", "http://llm-gateway:8003/v1")

    with pytest.raises(ca.HTTPException) as exc_info:
        ca._invoke_gateway_text("s", "u", "openai.gpt-5.6-luna")

    assert exc_info.value.status_code == 502, description

    detail = exc_info.value.detail
    if description == "missing-choices-key":
        assert "choices" in detail, description
    elif description == "empty-choices-list":
        assert "index out of range" in detail, description
    elif description == "missing-content-key":
        assert "content" in detail, description
    elif description == "missing-message-key":
        assert "message" in detail, description
    else:
        content = body["choices"][0]["message"]["content"]
        assert repr(content) in detail, description


def test_generate_certificate_real_mode_content_null_does_not_produce_fake_certificate(monkeypatch):
    """CRITICAL C1 재현 시나리오 그대로: 게이트웨이가 200과 함께
    content: null 을 돌려주면, str(None) == "None" 이 llmStatus="real" 인
    진짜 진단서 소견으로 응답에 실려서는 안 된다. generate_certificate()
    전체 경로에서 502가 그대로 올라와야 한다."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": None}}]})

    _install_transport(monkeypatch, handler)
    monkeypatch.setenv("LLM_PROVIDER", "real")
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", "http://llm-gateway:8003/v1")

    with pytest.raises(ca.HTTPException) as exc_info:
        ca.generate_certificate(_request())

    assert exc_info.value.status_code == 502


def test_generate_certificate_real_mode_empty_content_does_not_produce_fake_certificate(monkeypatch):
    """CRITICAL C1 표 2번째 행: content: "" 도 마찬가지로 502 여야 한다 —
    빈 문자열이 medicalCertificate="" / llmStatus="real" 로 새어나가면
    Java 쪽 blank 필터를 통과해 템플릿으로 대체되긴 하지만, 그 판단은
    Python 서비스가 "real" 이라고 잘못 보고한 뒤에 벌어지는 우연이다."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": ""}}]})

    _install_transport(monkeypatch, handler)
    monkeypatch.setenv("LLM_PROVIDER", "real")
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", "http://llm-gateway:8003/v1")

    with pytest.raises(ca.HTTPException) as exc_info:
        ca.generate_certificate(_request())

    assert exc_info.value.status_code == 502


def test_gateway_200_zero_width_space_only_content_raises_502_not_fabricated(monkeypatch):
    """M6: content 가 U+200B(zero-width space) 하나뿐이면 str.strip() 을
    그대로 통과해 medicalCertificate="​" / llmStatus="real" 인 "진짜"
    진단서로 새어나간다 — Spring 쪽 blank 필터도 이걸 non-blank 로 본다.
    blank 판정 전에 zero-width 문자를 지워서 이 케이스를 502 로 닫는다."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "​"}}]}
        )

    _install_transport(monkeypatch, handler)
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", "http://llm-gateway:8003/v1")

    with pytest.raises(ca.HTTPException) as exc_info:
        ca._invoke_gateway_text("s", "u", "openai.gpt-5.6-luna")

    assert exc_info.value.status_code == 502


def test_gateway_200_blank_content_guard_detail_is_truncated(monkeypatch):
    """M2: content 가 대용량(예: 200KB dict)이면 형식 위반 ValueError 의
    ``content={content!r}`` 이 그대로 502 detail·로그에 실려 200,000자를
    넘는 응답을 만든다. 형제 분기인 HTTPStatusError 의 body[:500] 과 같은
    정신으로, 여기서도 잘려야 한다 — 500자 훨씬 이전, 200자 근방에서
    잘렸는지 마커로 확인한다."""
    marker = "MARKER_AFTER_200_CHARS_END"
    large_content = {"x": "A" * 200 + marker}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"choices": [{"message": {"content": large_content}}]}
        )

    _install_transport(monkeypatch, handler)
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", "http://llm-gateway:8003/v1")

    with pytest.raises(ca.HTTPException) as exc_info:
        ca._invoke_gateway_text("s", "u", "openai.gpt-5.6-luna")

    assert exc_info.value.status_code == 502
    assert marker not in exc_info.value.detail
    assert len(exc_info.value.detail) < 400


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


def test_gateway_502_detail_uses_attempts_only_body(monkeypatch):
    """N7: `"upstreamStatus" in upstream_info or "attempts" in upstream_info`
    에서 "attempts" 체크를 빼는 변이를 잡는다 — upstreamStatus 없이
    attempts 만 있는 본문도 구조화된 detail 로 실려야 한다."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            502,
            json={"error": {"type": "upstream_error", "attempts": 5}},
        )

    _install_transport(monkeypatch, handler)
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", "http://llm-gateway:8003/v1")

    with pytest.raises(ca.HTTPException) as exc_info:
        ca._invoke_gateway_text("s", "u", "openai.gpt-5.6-luna")

    detail = exc_info.value.detail
    assert "attempts=5" in detail
    assert "body=" not in detail


def test_gateway_502_json_array_body_does_not_crash(monkeypatch):
    """N7/N8: `isinstance(error_body, dict)` 가드를 지우는 변이를 잡는다 —
    JSON 이지만 dict 가 아닌 본문(배열 등)에서 `.get()` 을 호출하면
    AttributeError 로 크래시한다. 여기서는 크래시 없이 502 로 떨어져야
    한다."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, json=[1, 2, 3])

    _install_transport(monkeypatch, handler)
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", "http://llm-gateway:8003/v1")

    with pytest.raises(ca.HTTPException) as exc_info:
        ca._invoke_gateway_text("s", "u", "openai.gpt-5.6-luna")

    assert exc_info.value.status_code == 502


def test_gateway_502_detail_full_shape_and_exception_chaining(monkeypatch):
    """N4/N5: status= 가 detail 에서 빠지는 변이와 `from exc` 체이닝이
    빠지는 변이를 한 번에 잡는다."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            502,
            json={"error": {"type": "upstream_error", "upstreamStatus": 401, "attempts": 2}},
        )

    _install_transport(monkeypatch, handler)
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", "http://llm-gateway:8003/v1")

    with pytest.raises(ca.HTTPException) as exc_info:
        ca._invoke_gateway_text("s", "u", "openai.gpt-5.6-luna")

    exc = exc_info.value
    assert exc.detail == "LLM 게이트웨이 호출 실패: status=502 upstreamStatus=401 attempts=2"
    assert exc.__cause__ is not None, "`raise ... from exc` 체이닝이 보존되어야 한다"


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


def test_gateway_502_body_truncated_at_500_chars(monkeypatch):
    """N6: `exc.response.text[:500]` 를 `[:50000]` 등으로 넓히는 변이를 잡는다.
    500 번째 문자 이후에 심어둔 마커가 detail 에 나타나면 안 된다."""
    marker = "MARKER_AFTER_500_CHARS_END"
    body_text = ("A" * 500) + marker

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text=body_text)

    _install_transport(monkeypatch, handler)
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", "http://llm-gateway:8003/v1")

    with pytest.raises(ca.HTTPException) as exc_info:
        ca._invoke_gateway_text("s", "u", "openai.gpt-5.6-luna")

    assert marker not in exc_info.value.detail


@pytest.mark.parametrize("status", [404, 405, 422])
def test_gateway_non_5xx_status_still_raises_502_with_status_preserved(monkeypatch, status):
    """N3: `raise_for_status()` 를 `status >= 500` 로 좁히는 변이를 잡는다 —
    좁히면 4xx 에서 예외가 안 나고 이어지는 content 파싱이 KeyError('choices')
    로 떨어져, detail 에서 실제 상류 상태코드(status=404 등)가 사라진다."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"detail": "gateway error"})

    _install_transport(monkeypatch, handler)
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", "http://llm-gateway:8003/v1")

    with pytest.raises(ca.HTTPException) as exc_info:
        ca._invoke_gateway_text("s", "u", "openai.gpt-5.6-luna")

    assert exc_info.value.status_code == 502
    assert f"status={status}" in exc_info.value.detail


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


def test_gateway_connect_error_logs_at_error_level_with_traceback(monkeypatch, caplog):
    """M4(X5 변이): ``except Exception`` 분기의 ``logger.exception`` 을
    ``logger.debug`` 로 낮추는 변이가 무커버리지였다 — 형제 분기
    (HTTPStatusError)는 test_gateway_502_logs_upstream_body 가 로그를
    고정하지만, 이 분기는 아무 테스트도 로그 레벨을 보지 않았다. 타임아웃/
    커넥션 실패마다 트레이스백이 조용히 사라지는 건 GC-2 위반이다.
    caplog 를 ERROR 로 필터링해두면, logger.debug 로 낮아지는 순간 레코드가
    아예 안 잡혀 이 테스트가 붉어진다."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    _install_transport(monkeypatch, handler)
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", "http://llm-gateway:8003/v1")

    with caplog.at_level(logging.ERROR, logger="certificate_api"):
        with pytest.raises(ca.HTTPException):
            ca._invoke_gateway_text("s", "u", "openai.gpt-5.6-luna")

    records = [r for r in caplog.records if r.name == "certificate_api"]
    assert any(r.levelno == logging.ERROR for r in records), (
        "게이트웨이 호출 실패가 ERROR 레벨로 로깅되지 않았다"
    )
    assert any(r.exc_info for r in records), (
        "logger.exception 이 트레이스백(exc_info)을 남겨야 한다"
    )


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


@pytest.mark.parametrize("raw_value", ["STUB", "  stub  ", "Stub", "sТub".replace("Т", "T")])
def test_stub_provider_case_and_whitespace_insensitive(monkeypatch, raw_value):
    """N10: `resolve_provider()` 를 raw `os.environ.get("LLM_PROVIDER")` 로
    바꾸는 변이를 잡는다 — `.strip().lower()` 가 없으면 `LLM_PROVIDER=STUB`
    같은 값이 조용히 real 경로로 빠진다(GC-3 위반)."""
    monkeypatch.setenv("LLM_PROVIDER", raw_value)

    resp = ca.generate_certificate(_request())

    assert resp.llmStatus == "stub"


# ---------------------------------------------------------------------------
# /health 계약
# ---------------------------------------------------------------------------


def test_health_reports_llm_gateway_configured_true(monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", "http://llm-gateway:8003/v1")
    client = TestClient(ca.app)
    body = client.get("/health").json()
    assert "llm_gateway_configured" in body
    assert body["llm_gateway_configured"] is True


def test_health_reports_llm_gateway_configured_false(monkeypatch):
    """M15: True 케이스만 검증되어 하드코딩된 True 변이가 살아남았다.
    False 케이스도 고정한다."""
    from fastapi.testclient import TestClient

    monkeypatch.delenv("LLM_GATEWAY_BASE_URL", raising=False)
    client = TestClient(ca.app)
    body = client.get("/health").json()
    assert body["llm_gateway_configured"] is False
