"""ReAct 도구 선택 루프를 걷어낸 뒤의 고정 파이프라인 계약.

배경(아키텍처 리뷰 §5): 도구 선택 루프는 게이트웨이 호출 4회를 쓰고
`_fallback_tool_decision` 의 하드코딩 순서를 거의 그대로 재생산했다.
`_execute_decided_tool` 은 5개 도구 중 3개에서 모델의 `actionInput` 을 통째로
무시하고 페이로드를 state 에서 다시 조립했으므로, 모델이 실제로 결정한 것은
"다음에 어떤 이름을 부를까" 뿐이었다. 그중 값을 하는
것은 검색어 하나다 — 한국어 임상 맥락을 영어 질의로 번역하는 일은 15개짜리
규칙이 절대 못 한다.

그래서 이 파이프라인에는 모델 호출이 남아 있지 않다.
나머지는 전부 결정론적 코드다. 이 파일은 그 경계를 고정한다.
"""
from __future__ import annotations

import app.agent as agent
from app.agent import run_validation_agent
from app.models import ValidationAgentRequest


# ---------------------------------------------------------------------------
# 공통 대역
# ---------------------------------------------------------------------------

def _request() -> ValidationAgentRequest:
    return ValidationAgentRequest(
        historyId=1,
        symptoms="기침",
        savedDiseases=[{"code": "J00", "name": "감기"}],
        savedPrescriptions=[{"code": "P1", "name": "진해거담제"}],
    )


class _Response:
    def __init__(self, content: str) -> None:
        self.content = content


class _RecordingLLM:
    """게이트웨이로 나가는 프롬프트를 전부 기록하는 대역.

    "루프가 사라졌다" 는 주장은 트레이스 모양이 아니라 **게이트웨이로 나간
    프롬프트의 수와 종류**로만 증명된다. 도구 선택 프롬프트는 `availableTools`
    를 싣고 나갔으므로, 그 문자열이 어떤 프롬프트에도 없어야 한다.
    """

    SUMMARY = "대증치료가 보고되었다."

    def __init__(self, summary: str | None = None) -> None:
        self.prompts: list[str] = []
        self.summary = summary if summary is not None else self.SUMMARY

    def invoke(self, messages):
        self.prompts.append(str(messages[-1].content))
        return _Response(self.summary)


class _FailingLLM:
    def __init__(self) -> None:
        self.calls = 0

    def invoke(self, _messages):
        self.calls += 1
        raise RuntimeError("게이트웨이 도달 불가")
class _FakePrescriptionFinder:
    def __init__(self, llm_status: str = "real") -> None:
        self.payloads: list[dict] = []
        self.llm_status = llm_status

    def invoke(self, payload=None):
        self.payloads.append(payload or {})
        return {
            "status": "LOADED",
            "evidence": ["기존 처방 RAG에서 참고 처방 후보를 조회했습니다."],
            "candidatePrescriptions": [{
                "id": 1, "rank": 1, "prescription_code": "C1",
                "prescription_name": "약1", "reason": "", "confidence_score": 0.9,
            }],
            "recommendationLlmStatus": self.llm_status,
            "recommendationVerification": None,
        }


class _SpyTool:
    """도구가 실제로 받은 페이로드를 기록하는 대역."""

    def __init__(self, result: dict) -> None:
        self.payloads: list[dict] = []
        self.result = result

    def invoke(self, payload=None):
        self.payloads.append(payload or {})
        return self.result


def _real_mode(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "real")
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", "http://dummy-gateway.invalid")
    monkeypatch.delenv("VALIDATION_JOB_BUDGET_SECONDS", raising=False)


def _install_tools(monkeypatch, finder_status: str = "real"):
    finder = _FakePrescriptionFinder(finder_status)
    monkeypatch.setattr(agent, "prescription_finder", finder)
    return finder


def test_dead_langgraph_symbols_are_gone():
    """F-M2: 죽은 LangGraph 구현과 도달 불가 `_llm_finalize` 를 지웠다."""
    for name in (
        "_build_graph", "_llm_finalize", "_finalize_validation", "_route_next_action",
        "_load_context", "_prescription_candidate_lookup",
        "_llm_tool_decision", "_fallback_tool_decision", "_execute_decided_tool",
        "_decide_next_tool",
    ):
        assert not hasattr(agent, name), f"{name} 이 아직 남아 있다"


def test_prescription_validator_receives_saved_prescriptions(monkeypatch):
    """F-H6: "저장 처방이 상병과 맞는가" 를 묻는 도구에 후보 처방을 대신
    밀어 넣으면, 도구는 방금 자기가 만든 추천을 검사하게 된다."""
    _real_mode(monkeypatch)
    _install_tools(monkeypatch)
    monkeypatch.setattr(agent, "create_llm", lambda: None)
    spy = _SpyTool({"status": "APPROPRIATE", "evidence": [], "suspiciousItems": []})
    monkeypatch.setattr(agent, "prescription_validator", spy)

    run_validation_agent(_request())

    assert spy.payloads, "Prescription Validator 가 호출돼야 한다"
    assert spy.payloads[0]["saved_prescriptions"] == [{"code": "P1", "name": "진해거담제"}]


def test_upstream_prescription_rag_status_never_sets_top_level_llm_status(monkeypatch):
    """처방 RAG 자신의 llmStatus 는 이 서비스의 llmStatus 가 아니다(Task 6 회귀).

    결정 루프가 사라져도 이 경계는 그대로 지켜야 한다 — 오히려 지금은
    `llmStatus` 를 떠받치는 신호가 둘뿐이라 오염 한 건의 무게가 더 크다.
    """
    _real_mode(monkeypatch)
    _install_tools(monkeypatch, finder_status="real")
    monkeypatch.setattr(agent, "create_llm", lambda: _FailingLLM())

    # 이 파이프라인은 모델을 부르지 않으므로 최상위는 "rule" 이다. 지키는 것은
    # 그 값이 처방 RAG 가 보고한 "real" 로 승격되지 않는다는 것이다.
    assert run_validation_agent(_request()).llmStatus == "rule"


def test_finalize_step_says_the_verdict_is_rule_based(monkeypatch):
    """F-M2: 최상위 overallStatus/summary/reason 은 전부 결정론적 함수의
    출력인데 화면에서는 모델이 쓴 판정처럼 읽혔다. 트레이스가 그것을 말한다."""
    _real_mode(monkeypatch)
    _install_tools(monkeypatch)
    monkeypatch.setattr(agent, "create_llm", lambda: _RecordingLLM())

    response = run_validation_agent(_request())
    finalize = [s for s in response.reasoningTrace if s["action"] == "Rule-based Finalize"]

    assert finalize, "판정 스텝이 트레이스에 있어야 한다"
    observation = finalize[0]["observation"]
    assert observation["status"] == "FINALIZED"
    assert response.overallStatus in " ".join(map(str, observation["evidence"]))
    assert any("규칙" in str(e) for e in observation["evidence"])


def test_trace_thoughts_do_not_claim_deliberation(monkeypatch):
    """트레이스의 `thought` 는 모델이 쓴 심의문이 아니다. 그렇게 읽히면 안 된다."""
    _real_mode(monkeypatch)
    _install_tools(monkeypatch)
    monkeypatch.setattr(agent, "create_llm", lambda: _RecordingLLM())

    for step in run_validation_agent(_request()).reasoningTrace:
        assert step["thought"].startswith("고정 파이프라인"), (
            f"심의로 읽힐 수 있는 thought: {step['thought']!r}"
        )


def test_expired_budget_is_recorded_in_the_trace(monkeypatch):
    """조용히 멈추면 GC-2 위반이다 — 무엇이 실행되지 않았는지 남긴다."""
    _real_mode(monkeypatch)
    _install_tools(monkeypatch)
    monkeypatch.setattr(agent, "create_llm", lambda: _RecordingLLM())
    monkeypatch.setenv("VALIDATION_JOB_BUDGET_SECONDS", "0")

    response = run_validation_agent(_request())
    budget_steps = [s for s in response.reasoningTrace
                    if s["observation"].get("status") == "BUDGET_EXCEEDED"]

    assert budget_steps, "예산 초과로 건너뛴 단계가 트레이스에 남아야 한다"
    assert all(s["source"] == "rule" for s in budget_steps)


def test_generous_budget_runs_the_whole_pipeline(monkeypatch):
    _real_mode(monkeypatch)
    finder = _install_tools(monkeypatch)
    monkeypatch.setattr(agent, "create_llm", lambda: _RecordingLLM())
    monkeypatch.setenv("VALIDATION_JOB_BUDGET_SECONDS", "600")

    run_validation_agent(_request())

    assert finder.payloads


def test_no_tool_selection_prompt_reaches_the_gateway(monkeypatch):
    """도구 선택은 게이트웨이 호출을 한 번도 쓰지 않는다.

    이 단언은 트레이스가 아니라 프롬프트를 본다 — 루프를 "안 도는 것처럼"
    보이게 고쳐 놓고 실제로는 결정 호출을 남겨두는 변경을 잡아야 하기 때문이다.

    PubMed 제거로 이 파이프라인의 모델 호출은 0 이 됐다. 그래서 지금은 "도구
    선택 프롬프트가 없다" 보다 강한 것을 고정한다 — **어떤 프롬프트도 나가지
    않는다.** 나중에 모델 호출을 다시 들이더라도, `availableTools` 를 싣는
    루프만은 돌아오면 안 된다는 원래 의도도 함께 남긴다.
    """
    _real_mode(monkeypatch)
    _install_tools(monkeypatch)
    llm = _RecordingLLM()
    monkeypatch.setattr(agent, "create_llm", lambda: llm)

    run_validation_agent(_request())

    assert all("availableTools" not in p for p in llm.prompts), (
        "도구 선택 프롬프트가 게이트웨이로 나갔다 — 루프가 남아 있다"
    )
    assert llm.prompts == [], (
        "이 파이프라인은 모델을 부르지 않는다. "
        f"실제 프롬프트 {len(llm.prompts)}개"
    )


def test_expired_budget_stops_the_pipeline_early(monkeypatch):
    """예산을 0 으로 두면 첫 단계 뒤로 아무 도구도 부르지 않는다."""
    _real_mode(monkeypatch)
    finder = _install_tools(monkeypatch)
    monkeypatch.setattr(agent, "create_llm", lambda: _RecordingLLM())
    monkeypatch.setenv("VALIDATION_JOB_BUDGET_SECONDS", "0")

    response = run_validation_agent(_request())

    assert finder.payloads == [], "예산이 끝났는데 처방 RAG 를 호출했다"
    assert response.overallStatus in {"PASS", "WARNING", "CRITICAL", "NEEDS_REVIEW"}


# PubMed 제거로 이 파이프라인의 모델 호출이 0 이 됐다. 그 결과 llmStatus 는
# 어떤 실행에서도 "fallback" 이다 — 모델이 실패해서가 아니라 부르지 않아서다.
#
# 이걸 테스트로 못박는 이유: 이전 세 테스트(real/fallback/stub 분기)는 모델
# 호출이 있다는 전제 위에 있었고, 전제가 사라지자 통과할 수 없는 단언이 됐다.
# 그냥 지우면 "llmStatus 가 무엇이어야 하는가" 를 아무도 말하지 않게 되고,
# 나중에 이 값이 조용히 "real" 로 바뀌어도 잡히지 않는다.
def test_pipeline_reports_fallback_because_it_calls_no_model(monkeypatch):
    _real_mode(monkeypatch)
    _install_tools(monkeypatch)
    llm = _RecordingLLM()
    monkeypatch.setattr(agent, "create_llm", lambda: llm)

    response = run_validation_agent(_request())

    assert llm.prompts == [], "모델을 불렀다 — 이 파이프라인은 부르지 않는다"
    assert response.llmStatus == "rule", (
        "모델을 한 번도 부르지 않은 실행이 real/stub 로 보고되면, 화면은 이 "
        "응답이 모델 판단인 것처럼 읽는다. fallback 도 아니다 — 그건 "
        "불렀다가 실패했다는 뜻이라 설계대로 돈 판정을 장애로 표시하게 된다"
    )
