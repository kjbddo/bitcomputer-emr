"""ReAct 도구 선택 루프를 걷어낸 뒤의 고정 파이프라인 계약.

배경(아키텍처 리뷰 §5): 도구 선택 루프는 게이트웨이 호출 4회를 쓰고
`_fallback_tool_decision` 의 하드코딩 순서를 거의 그대로 재생산했다.
`_execute_decided_tool` 은 5개 도구 중 3개에서 모델의 `actionInput` 을 통째로
무시하고 페이로드를 state 에서 다시 조립했으므로, 모델이 실제로 결정한 것은
"다음에 어떤 이름을 부를까" 와 PubMed 검색어 문자열뿐이었다. 그중 값을 하는
것은 검색어 하나다 — 한국어 임상 맥락을 영어 질의로 번역하는 일은 15개짜리
`KOREAN_PUBMED_TERMS` 사전이 절대 못 한다.

그래서 남기는 모델 호출은 둘뿐이다: (1) PubMed 질의 생성, (2) 근거 요약.
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

    SUMMARY = "PubMed 초록 기준 대증치료가 보고되었다 (PMID 111)."
    QUERY = "acute cough symptomatic treatment dextromethorphan adults"

    def __init__(self, summary: str | None = None) -> None:
        self.prompts: list[str] = []
        self.summary = summary if summary is not None else self.SUMMARY

    def invoke(self, messages):
        prompt = str(messages[-1].content)
        self.prompts.append(prompt)
        if "PubMed ESearch" in prompt:
            return _Response('{"queries": ["%s"]}' % self.QUERY)
        return _Response(self.summary)


class _FailingLLM:
    def __init__(self) -> None:
        self.calls = 0

    def invoke(self, _messages):
        self.calls += 1
        raise RuntimeError("게이트웨이 도달 불가")


class _FakePubmedLoader:
    """`pubmed_loader` 는 pydantic StructuredTool 이라 인스턴스 속성을 직접
    monkeypatch 할 수 없다. agent 모듈이 바라보는 이름 자체를 바꿔치기한다."""

    def __init__(self) -> None:
        self.queries: list[str] = []

    def invoke(self, payload=None):
        self.queries.append((payload or {}).get("query", ""))
        return {
            "status": "LOADED",
            "evidence": ["PubMed에서 1건의 근거 후보를 조회했습니다."],
            "articles": [{
                "pmid": "111",
                "title": "Cough treatment guideline",
                "source": "Test Journal",
                "pubdate": "2024",
                "abstract": "Cough treatment abstract.",
                "abstractSnippet": "Cough treatment abstract.",
            }],
        }


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
    loader = _FakePubmedLoader()
    finder = _FakePrescriptionFinder(finder_status)
    monkeypatch.setattr(agent, "pubmed_loader", loader)
    monkeypatch.setattr(agent, "prescription_finder", finder)
    return loader, finder


# ---------------------------------------------------------------------------
# 루프가 실제로 사라졌는가
# ---------------------------------------------------------------------------

def test_no_tool_selection_prompt_reaches_the_gateway(monkeypatch):
    """도구 선택은 게이트웨이 호출을 한 번도 쓰지 않는다.

    이 단언은 트레이스가 아니라 프롬프트를 본다 — 루프를 "안 도는 것처럼"
    보이게 고쳐 놓고 실제로는 결정 호출을 남겨두는 변경을 잡아야 하기 때문이다.
    """
    _real_mode(monkeypatch)
    _install_tools(monkeypatch)
    llm = _RecordingLLM()
    monkeypatch.setattr(agent, "create_llm", lambda: llm)

    run_validation_agent(_request())

    assert llm.prompts, "모델 호출이 아예 없으면 이 테스트가 무의미하다"
    assert all("availableTools" not in p for p in llm.prompts), (
        "도구 선택 프롬프트가 게이트웨이로 나갔다 — 루프가 남아 있다"
    )
    assert len(llm.prompts) == 2, (
        "남는 모델 호출은 PubMed 질의 생성과 근거 요약 둘뿐이다. "
        f"실제 프롬프트 {len(llm.prompts)}개"
    )


def test_pipeline_runs_fixed_order_regardless_of_model(monkeypatch):
    """도구 실행 순서는 결정론이다. 모델이 있든 없든 같은 순서가 나온다."""
    _real_mode(monkeypatch)
    _install_tools(monkeypatch)
    monkeypatch.setattr(agent, "create_llm", lambda: _RecordingLLM())
    with_model = [s["action"] for s in run_validation_agent(_request()).reasoningTrace]

    monkeypatch.setattr(agent, "create_llm", lambda: None)
    without_model = [s["action"] for s in run_validation_agent(_request()).reasoningTrace]

    assert with_model == [
        "X-ray Result Loader",
        "Disease Validator",
        "Prescription Validator",
        "Pubmed Loader",
        "Prescription Finder",
        "Rule-based Finalize",
    ]
    assert with_model == without_model, "실행 순서가 모델 가용성에 따라 달라지면 안 된다"


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


# ---------------------------------------------------------------------------
# 남는 모델 호출 (a) PubMed 질의 생성
# ---------------------------------------------------------------------------

def test_pubmed_query_comes_from_the_model_when_available(monkeypatch):
    """모델이 만든 영어 질의가 실제 검색에 쓰여야 한다.

    이 호출을 없애고 `KOREAN_PUBMED_TERMS` 사전 빌더로 되돌리면 실패한다 —
    사전은 "cough treatment" 밖에 만들지 못한다.
    """
    _real_mode(monkeypatch)
    loader, _ = _install_tools(monkeypatch)
    monkeypatch.setattr(agent, "create_llm", lambda: _RecordingLLM())

    response = run_validation_agent(_request())

    assert loader.queries[0] == _RecordingLLM.QUERY
    assert _RecordingLLM.QUERY in response.validation["pubmedQueries"]
    pubmed_steps = [s for s in response.reasoningTrace if s["action"] == "Pubmed Loader"]
    assert pubmed_steps and pubmed_steps[0]["source"] == "llm"


def test_pubmed_query_falls_back_to_builders_and_says_so(monkeypatch):
    """질의 생성이 실패하면 사전 빌더로 떨어지고, 트레이스가 그 사실을 말한다."""
    _real_mode(monkeypatch)
    loader, _ = _install_tools(monkeypatch)
    monkeypatch.setattr(agent, "create_llm", lambda: _FailingLLM())

    response = run_validation_agent(_request())

    assert loader.queries, "폴백 질의라도 검색은 돌아야 한다"
    assert loader.queries[0] != _RecordingLLM.QUERY
    pubmed_steps = [s for s in response.reasoningTrace if s["action"] == "Pubmed Loader"]
    assert pubmed_steps and pubmed_steps[0]["source"] == "fallback"


# ---------------------------------------------------------------------------
# 남는 모델 호출 (b) 근거 요약
# ---------------------------------------------------------------------------

def test_evidence_summary_reaches_the_response(monkeypatch):
    """요약 본문이 응답과 checks[] 양쪽에 실려야 한다."""
    _real_mode(monkeypatch)
    _install_tools(monkeypatch)
    monkeypatch.setattr(agent, "create_llm", lambda: _RecordingLLM())

    response = run_validation_agent(_request())

    summary = response.validation["pubmedEvidenceSummary"]
    assert summary == _RecordingLLM.SUMMARY
    pubmed_checks = [c for c in response.checks if c.get("type") == "PUBMED_EVIDENCE"]
    assert pubmed_checks, "PUBMED_EVIDENCE 체크가 있어야 한다"
    assert summary in pubmed_checks[0]["message"]
    assert "(규칙 기반)" not in pubmed_checks[0]["message"]


def test_evidence_summary_marks_rule_based_composition(monkeypatch):
    _real_mode(monkeypatch)
    _install_tools(monkeypatch)
    monkeypatch.setattr(agent, "create_llm", lambda: _FailingLLM())

    response = run_validation_agent(_request())

    pubmed_checks = [c for c in response.checks if c.get("type") == "PUBMED_EVIDENCE"]
    assert pubmed_checks
    assert "(규칙 기반)" in pubmed_checks[0]["message"]
    assert response.validation["pubmedEvidenceSummary"] in pubmed_checks[0]["message"]


# ---------------------------------------------------------------------------
# (c) llmStatus 도출 — 실제로 실행된 모델 호출에서만 나온다
# ---------------------------------------------------------------------------

def test_llm_status_real_requires_a_successful_model_call(monkeypatch):
    _real_mode(monkeypatch)
    _install_tools(monkeypatch)
    monkeypatch.setattr(agent, "create_llm", lambda: _RecordingLLM())

    assert run_validation_agent(_request()).llmStatus == "real"


def test_llm_status_is_fallback_when_every_model_call_failed(monkeypatch):
    """게이트웨이는 설정돼 있지만 호출이 전부 실패한 경우.

    설정("게이트웨이 URL 이 있다")이 아니라 실행 경로("모델이 무엇을 썼나")를
    본다(GC-5). 이 구분이 무너지면 여기서 "real" 이 나온다.
    """
    _real_mode(monkeypatch)
    _install_tools(monkeypatch)
    llm = _FailingLLM()
    monkeypatch.setattr(agent, "create_llm", lambda: llm)

    response = run_validation_agent(_request())

    assert llm.calls >= 1, "모델 호출을 시도조차 안 했으면 이 테스트가 무의미하다"
    assert response.llmStatus == "fallback"


def test_llm_status_is_stub_in_stub_mode(monkeypatch):
    """stub 모드는 게이트웨이를 부르지 않고, 그 사실을 llmStatus 로 말한다."""
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", "http://dummy-gateway.invalid")
    _install_tools(monkeypatch)
    llm = _FailingLLM()
    monkeypatch.setattr(agent, "create_llm", lambda: llm)

    response = run_validation_agent(_request())

    assert response.llmStatus == "stub"
    assert llm.calls == 0, "stub 모드에서 게이트웨이를 부르면 안 된다"


def test_upstream_prescription_rag_status_never_sets_top_level_llm_status(monkeypatch):
    """처방 RAG 자신의 llmStatus 는 이 서비스의 llmStatus 가 아니다(Task 6 회귀).

    결정 루프가 사라져도 이 경계는 그대로 지켜야 한다 — 오히려 지금은
    `llmStatus` 를 떠받치는 신호가 둘뿐이라 오염 한 건의 무게가 더 크다.
    """
    _real_mode(monkeypatch)
    _install_tools(monkeypatch, finder_status="real")
    monkeypatch.setattr(agent, "create_llm", lambda: _FailingLLM())

    assert run_validation_agent(_request()).llmStatus == "fallback"


# ---------------------------------------------------------------------------
# 트레이스 정직성
# ---------------------------------------------------------------------------

def test_deterministic_steps_are_marked_rule_not_llm(monkeypatch):
    """의사 화면은 스텝별 source 를 "(규칙 기반)" 으로 렌더한다.

    도구 실행이 더 이상 모델의 선택이 아니므로, 그 스텝들이 "llm" 으로 남으면
    화면이 없는 심의를 있다고 말하게 된다.
    """
    _real_mode(monkeypatch)
    _install_tools(monkeypatch)
    monkeypatch.setattr(agent, "create_llm", lambda: _RecordingLLM())

    trace = run_validation_agent(_request()).reasoningTrace
    by_action = {s["action"]: s for s in trace}

    for action in ("X-ray Result Loader", "Disease Validator",
                   "Prescription Validator", "Rule-based Finalize"):
        assert by_action[action]["source"] == "rule", f"{action} 은 규칙이 실행한 스텝이다"
    # 모델이 실제로 문장을 만든 스텝만 "llm" 이다.
    assert by_action["Pubmed Loader"]["source"] == "llm"


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


# ---------------------------------------------------------------------------
# (d) 전역 데드라인 (F-H7)
# ---------------------------------------------------------------------------

def test_expired_budget_stops_the_pipeline_early(monkeypatch):
    """예산을 0 으로 두면 첫 단계 뒤로 아무 도구도 부르지 않는다."""
    _real_mode(monkeypatch)
    loader, finder = _install_tools(monkeypatch)
    monkeypatch.setattr(agent, "create_llm", lambda: _RecordingLLM())
    monkeypatch.setenv("VALIDATION_JOB_BUDGET_SECONDS", "0")

    response = run_validation_agent(_request())

    assert loader.queries == [], "예산이 끝났는데 PubMed 를 조회했다"
    assert finder.payloads == [], "예산이 끝났는데 처방 RAG 를 호출했다"
    assert response.overallStatus in {"PASS", "WARNING", "CRITICAL", "NEEDS_REVIEW"}


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
    loader, finder = _install_tools(monkeypatch)
    monkeypatch.setattr(agent, "create_llm", lambda: _RecordingLLM())
    monkeypatch.setenv("VALIDATION_JOB_BUDGET_SECONDS", "600")

    run_validation_agent(_request())

    assert loader.queries and finder.payloads
