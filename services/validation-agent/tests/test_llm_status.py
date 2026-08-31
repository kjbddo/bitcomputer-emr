"""`llmStatus` 와 트레이스 스텝 `source` 의 계약.

ReAct 도구 선택 루프를 제거한 뒤(아키텍처 리뷰 §5) 이 두 값의 근거가 바뀌었다.

- 예전: `llmStatus` 는 **도구 이름을 고른 결정**의 출처에서 나왔다. "real" 은
  "모델이 도구 이름을 골랐다" 를 뜻했다.
- 지금: `llmStatus` 는 **응답 본문의 문장을 만든 모델 호출**에서만 나온다
  (`gateway.ModelCallLedger`). 지금은 그 호출이 하나도 없고,
  "real" 은 처음으로 "모델이 이 응답에 무언가를 썼다" 를 뜻한다.

이 파일이 고정하는 것은 그 경계다. 특히 **오염 금지** 규율 — 도구 실행 결과나
상류 서비스(`recommendationLlmStatus`)가 장부에 들어가면 안 된다 — 는 루프가
사라진 지금 오히려 더 중요하다. 신호가 둘뿐이라 오염 한 건의 무게가 크다.
"""
from app import agent, tools
from app.agent import run_validation_agent
from app.models import ValidationAgentRequest


def _request() -> ValidationAgentRequest:
    return ValidationAgentRequest(
        historyId=1,
        symptoms="기침",
        savedDiseases=[{"code": "J00", "name": "감기"}],
        savedPrescriptions=[],
    )


def _passing_request() -> ValidationAgentRequest:
    """overallStatus 가 "PASS" 로 떨어지는 요청. 저장 상병과 저장 처방이 모두
    있어야 prescription_validator 가 "APPROPRIATE" 를 돌려주고(그래야
    "INSUFFICIENT_DATA" 체크가 안 생겨 NEEDS_REVIEW 로 빠지지 않는다), X-ray
    추론이 없어야 disease_validator 가 "MATCH" 로 판정한다."""
    return ValidationAgentRequest(
        historyId=1,
        symptoms="기침",
        savedDiseases=[{"code": "J00", "name": "감기"}],
        savedPrescriptions=[{"code": "P1", "name": "진해거담제"}],
    )


class _FakeLLM:
    """`create_llm()` 대신 쓰는 대역. 실제 게이트웨이 네트워크 호출 없이
    모델이 붙어 있는 상황을 재현한다.

    이 파이프라인은 현재 모델을 부르지 않으므로 이 대역은 한 번도 호출되지
    않는다. 그래도 남긴다 — 아래 테스트들이 지키는 것은 "모델이 붙어 있어도
    최상위 llmStatus 가 처방 RAG 의 값으로 오염되지 않는다" 이고, 대역이 없으면
    그 조건 자체를 만들 수 없다."""

    def __init__(self, summary_text="대증치료가 보고되었다."):
        self.summary_text = summary_text

    def invoke(self, messages):
        content = self.summary_text

        class _Response:
            def __init__(self, content: str) -> None:
                self.content = content

        return _Response(content)
def _real_mode(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "real")
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", "http://dummy-gateway.invalid")
    monkeypatch.delenv("VALIDATION_JOB_BUDGET_SECONDS", raising=False)


def test_fallback_trace_entries_are_marked(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "real")
    monkeypatch.delenv("LLM_GATEWAY_BASE_URL", raising=False)
    response = run_validation_agent(_request())
    assert response.reasoningTrace, "트레이스가 비어 있으면 이 테스트가 무의미하다"
    # 게이트웨이가 없는 시나리오에서는 "llm" 이 단 하나도 나오지 않아야 한다.
    assert all(e["source"] in {"fallback", "rule"} for e in response.reasoningTrace)
    assert "llm" not in {e["source"] for e in response.reasoningTrace}  # 실제 신호


def test_trace_entries_always_carry_source(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    response = run_validation_agent(_request())
    for entry in response.reasoningTrace:
        assert "source" in entry, "source 가 없으면 출처를 구분할 수 없다"


def test_successful_llm_run_has_no_fallback_trace_entries(monkeypatch):
    """흠 없는 실행에서 "fallback" 은 하나도 나오면 안 된다.

    "rule" 과 "fallback" 은 다른 말이다 — 앞은 "모델이 관여할 여지가 없는
    단계", 뒤는 "모델을 시도했는데 실패했다" 다. 둘을 한 집합으로 받아들이면
    실패 신호가 무의미해진다.
    """
    _real_mode(monkeypatch)
    monkeypatch.setattr(agent, "create_llm", lambda: _FakeLLM())
    monkeypatch.setattr(agent, "prescription_finder", _FakePrescriptionFinder("real"))

    response = run_validation_agent(_passing_request())

    assert response.overallStatus == "PASS"
    assert not any(e["source"] == "fallback" for e in response.reasoningTrace)
    assert any(e["source"] == "rule" for e in response.reasoningTrace)


class _FakeHttpResponse:
    def __init__(self, json_body):
        self._json_body = json_body

    def raise_for_status(self):
        return None

    def json(self):
        return self._json_body


class _FakeHttpxClient:
    def __init__(self, json_body, captured):
        self._json_body = json_body
        self._captured = captured

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def post(self, url, json=None):
        self._captured["url"] = url
        self._captured["payload"] = json
        return _FakeHttpResponse(self._json_body)


def _install_fake_httpx(monkeypatch, json_body, captured):
    def factory(timeout=None):
        captured["timeout"] = timeout
        return _FakeHttpxClient(json_body, captured)

    monkeypatch.setattr(tools.httpx, "Client", factory)


def test_tools_prescription_finder_forwards_upstream_llm_status(monkeypatch):
    captured: dict = {}
    _install_fake_httpx(monkeypatch, {"prescriptions": [], "llmStatus": "stub"}, captured)

    result = tools.prescription_finder.invoke({
        "patient_id": "1",
        "diseases": [],
        "symptoms": "",
    })

    assert result["recommendationLlmStatus"] == "stub"


def test_tools_prescription_finder_uses_configurable_timeout_matching_prescription_budget(monkeypatch):
    """호출자 타임아웃이 피호출자 총예산보다 짧으면, prescription-api 가 정상
    응답을 만들고 있는데도 이쪽이 먼저 포기해 "처방 RAG 호출 실패" 가 남는다."""
    captured: dict = {}
    monkeypatch.delenv("PRESCRIPTION_AGENT_TIMEOUT_SECONDS", raising=False)
    _install_fake_httpx(monkeypatch, {"prescriptions": []}, captured)

    tools.prescription_finder.invoke({"patient_id": "1", "diseases": [], "symptoms": ""})

    assert captured["timeout"] == 180.0


def test_tools_prescription_finder_timeout_reads_env(monkeypatch):
    captured: dict = {}
    monkeypatch.setenv("PRESCRIPTION_AGENT_TIMEOUT_SECONDS", "45")
    _install_fake_httpx(monkeypatch, {"prescriptions": []}, captured)

    tools.prescription_finder.invoke({"patient_id": "1", "diseases": [], "symptoms": ""})

    assert captured["timeout"] == 45.0


def test_tools_prescription_finder_failure_reports_fallback_llm_status(monkeypatch):
    def exploding(timeout=None):
        raise RuntimeError("연결 실패")

    monkeypatch.setattr(tools.httpx, "Client", exploding)

    result = tools.prescription_finder.invoke({
        "patient_id": "1",
        "diseases": [],
        "symptoms": "",
    })

    assert result["recommendationLlmStatus"] == "fallback"


# ---------------------------------------------------------------------------
# 오염 금지 — 상류 서비스의 출처가 이 서비스의 llmStatus 가 되면 안 된다
# ---------------------------------------------------------------------------


class _FakePrescriptionFinder:
    """`agent.prescription_finder` 를 통째로 대체하는 대역."""

    def __init__(self, llm_status):
        self.llm_status = llm_status

    def invoke(self, payload=None):
        return {
            "status": "LOADED",
            "evidence": ["기존 처방 RAG에서 참고 처방 후보를 조회했습니다."],
            "candidatePrescriptions": [
                {
                    "id": 1, "rank": 1, "prescription_code": "C1",
                    "prescription_name": "약1", "reason": "", "confidence_score": 0.9,
                }
            ],
            # 처방 RAG 자신이 모델을 썼는지 — Prescription Finder 트레이스 항목의
            # source 판정에만 쓰인다. 최상위 llmStatus 에 섞으면 Task 6 회귀다.
            "recommendationLlmStatus": self.llm_status,
        }


def test_prescription_finder_trace_marks_stub_recommendation(monkeypatch):
    """처방 RAG 가 스텁 응답을 돌려주면 그 스텝은 "규칙 기반" 이 아니라 "스텁" 이다.

    이 스텝을 실행한 것은 규칙이지만, 화면에 실려 가는 **데이터** 는 스텁에서
    왔다. 라이브에서 실제로 관측된 상태다(F-H3) — 그 사실이 트레이스에서
    사라지면 스텁 처방이 깨끗한 화면으로 의사에게 간다.
    """
    _real_mode(monkeypatch)
    monkeypatch.setattr(agent, "create_llm", lambda: _FakeLLM())
    monkeypatch.setattr(agent, "prescription_finder", _FakePrescriptionFinder("stub"))

    response = run_validation_agent(_request())

    finder = [e for e in response.reasoningTrace if e["action"] == "Prescription Finder"]
    assert finder, "Prescription Finder 스텝이 트레이스에 있어야 한다"
    assert finder[0]["source"] == "stub"


def test_prescription_finder_stub_does_not_flip_top_level_status(monkeypatch):
    """스텝 출처가 최상위 llmStatus 를 오염시키면 안 된다(Task 6 회귀 방지).

    방향을 반대로도 확인한다 — 처방 RAG 가 스텁이라고 해서 이 서비스가 실제로
    성사시킨 모델 호출이 지워지지도 않아야 한다.
    """
    _real_mode(monkeypatch)
    monkeypatch.setattr(agent, "create_llm", lambda: _FakeLLM())
    monkeypatch.setattr(agent, "prescription_finder", _FakePrescriptionFinder("stub"))

    # 이 파이프라인은 모델을 부르지 않으므로 최상위는 "rule" 이다. 핵심은 그
    # 값이 처방 RAG 가 보고한 "stub" 으로 바뀌지 않는다는 것이다.
    assert run_validation_agent(_request()).llmStatus == "rule"


def test_prescription_finder_real_payload_does_not_promote_failed_model_calls(monkeypatch):
    """Task 6 결함의 정확한 형태: 이 서비스의 모델 호출이 전부 실패했는데
    처방 RAG 보조 호출 하나가 "real" 을 보고했다는 이유로 최상위 llmStatus 가
    real 로 뒤바뀌면 안 된다."""
    _real_mode(monkeypatch)
    monkeypatch.setattr(agent, "create_llm", lambda: None)
    monkeypatch.setattr(agent, "prescription_finder", _FakePrescriptionFinder("real"))

    # 처방 RAG 가 "real" 을 보고해도 최상위는 승격되지 않는다.
    assert run_validation_agent(_request()).llmStatus == "rule"


def test_prescription_finder_real_payload_never_marks_trace_llm(monkeypatch):
    """"승격 금지" 는 트레이스 자체로도 확인돼야 한다.

    `_downgrade_by_payload_source` 맨 위에 승격 분기
    (`if payload_status == "real": return "llm"`)를 끼워 넣어도 최상위
    llmStatus 만 보는 테스트는 통과한다. 이 스텝에는 이 서비스의 모델이
    아무것도 쓰지 않았으므로 "llm" 이 될 수 없다.
    """
    _real_mode(monkeypatch)
    monkeypatch.setattr(agent, "create_llm", lambda: _FakeLLM())
    monkeypatch.setattr(agent, "prescription_finder", _FakePrescriptionFinder("real"))

    response = run_validation_agent(_request())

    finder_entries = [e for e in response.reasoningTrace if e["action"] == "Prescription Finder"]
    assert finder_entries, "Prescription Finder 스텝이 트레이스에 있어야 한다"
    assert all(e["source"] != "llm" for e in finder_entries)
    assert finder_entries[0]["source"] == "rule"


class _RaisingPrescriptionFinder:
    def invoke(self, payload=None):
        raise RuntimeError("처방 RAG 연결 실패")


def test_prescription_finder_exception_fails_closed_not_rule(monkeypatch):
    """호출 자체가 예외를 던지면 observation 에 `recommendationLlmStatus` 키가
    아예 없다. `observation.get(...)` 이 돌려주는 `None` 을 관대하게 다루면
    실패한 호출이 정상 실행처럼 읽힌다.

    강등 목적지까지 고정한다 — "rule"(정상 실행) 로 남으면 실패가 화면에서
    사라진다.
    """
    _real_mode(monkeypatch)
    monkeypatch.setattr(agent, "create_llm", lambda: _FakeLLM())
    monkeypatch.setattr(agent, "prescription_finder", _RaisingPrescriptionFinder())

    response = run_validation_agent(_request())

    finder_entries = [e for e in response.reasoningTrace if e["action"] == "Prescription Finder"]
    assert finder_entries, "Prescription Finder 스텝이 트레이스에 있어야 한다"
    assert finder_entries[0]["source"] == "fallback"
    assert finder_entries[0]["observation"]["status"] == "FAILED"


# ---------------------------------------------------------------------------
# F-H3 — prescription-api 자신의 llmStatus 가 응답 최상위까지 도달하는가
#
# 처방 표의 모델 출처 배지는 이 값을 읽어야 한다. validation-agent 자신의
# `llmStatus` 를 읽으면 prescription-api 가 스텁인데도 배지가 억제된다
# (F-H3 라이브 재현). `prescriptionVerification` 이 이미 쓰는 것과 같은
# 경로로, 같은 분리 원칙을 지키며 얹는다.
# ---------------------------------------------------------------------------


def test_prescription_llm_status_reaches_response_top_level(monkeypatch):
    """처방 RAG 가 보고한 llmStatus 가 최상위 `prescriptionLlmStatus` 로
    도달해야 한다. 도달하지 못하면 웹은 대신 읽을 값이 없어 다른 서비스의
    `llmStatus` 를 읽게 되고, 그것이 정확히 F-H3 이다."""
    _real_mode(monkeypatch)
    monkeypatch.setattr(agent, "create_llm", lambda: _FakeLLM())
    monkeypatch.setattr(agent, "prescription_finder", _FakePrescriptionFinder("stub"))

    response = run_validation_agent(_request())

    assert response.prescriptionLlmStatus == "stub"


def test_prescription_llm_status_does_not_contaminate_top_level_llm_status(monkeypatch):
    """두 축은 계속 분리돼 있어야 한다 — 이 서비스의 모델 호출은 성사됐고
    처방 RAG 페이로드만 스텁이다."""
    _real_mode(monkeypatch)
    monkeypatch.setattr(agent, "create_llm", lambda: _FakeLLM())
    monkeypatch.setattr(agent, "prescription_finder", _FakePrescriptionFinder("stub"))

    response = run_validation_agent(_request())

    assert response.llmStatus == "rule"
    assert response.prescriptionLlmStatus == "stub"


def test_prescription_llm_status_real_does_not_promote_stub_mode(monkeypatch):
    """반대 방향도 막는다. 처방 RAG 가 "real" 이어도 이 서비스가 스텁 모드면
    최상위 llmStatus 는 "stub" 이다."""
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    monkeypatch.setattr(agent, "prescription_finder", _FakePrescriptionFinder("real"))

    response = run_validation_agent(_request())

    assert response.llmStatus == "rule"
    assert response.prescriptionLlmStatus == "real"


def test_prescription_llm_status_is_none_when_finder_raises(monkeypatch):
    """호출이 예외로 죽으면 관측값에 그 키가 없다. 그때 "real" 로 기울면
    스텁·실패가 깨끗한 화면으로 지나간다 — None 그대로 두어 웹이 "미확인"
    으로 렌더하게 한다(GC-3)."""
    _real_mode(monkeypatch)
    monkeypatch.setattr(agent, "create_llm", lambda: _FakeLLM())
    monkeypatch.setattr(agent, "prescription_finder", _RaisingPrescriptionFinder())

    response = run_validation_agent(_request())

    assert response.prescriptionLlmStatus is None
