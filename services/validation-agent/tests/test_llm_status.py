import os

from app import agent
from app.agent import run_validation_agent
from app.models import ValidationAgentRequest


def _request() -> ValidationAgentRequest:
    return ValidationAgentRequest(
        historyId=1,
        symptoms="기침",
        savedDiseases=[{"code": "J00", "name": "감기"}],
        savedPrescriptions=[],
    )


def test_stub_provider_reports_stub(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    response = run_validation_agent(_request())
    assert response.llmStatus == "stub"


def test_no_gateway_configured_reports_fallback(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "real")
    monkeypatch.delenv("LLM_GATEWAY_BASE_URL", raising=False)
    response = run_validation_agent(_request())
    assert response.llmStatus == "fallback"


def test_fallback_trace_entries_are_marked(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "real")
    monkeypatch.delenv("LLM_GATEWAY_BASE_URL", raising=False)
    response = run_validation_agent(_request())
    assert response.reasoningTrace, "트레이스가 비어 있으면 이 테스트가 무의미하다"
    # 폴백으로 결정된 스텝은 트레이스만 보고 구분 가능해야 한다(spec §6.3).
    # "rule" 은 결정 루프 지원 없이 항상 실행되는 규칙 기반 후처리 전용 값이며
    # (리뷰 finding 2), 게이트웨이가 없는 이 시나리오에서는 "llm" 이 단 하나도
    # 나오지 않아야 한다는 것이 실제로 의미 있는 신호다.
    assert all(e["source"] in {"fallback", "rule"} for e in response.reasoningTrace)
    assert "llm" not in {e["source"] for e in response.reasoningTrace}  # 실제 신호


def test_trace_entries_always_carry_source(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    response = run_validation_agent(_request())
    for entry in response.reasoningTrace:
        assert "source" in entry, "source 가 없으면 출처를 구분할 수 없다"


def _sequenced_llm_decision(sequence):
    """`_llm_tool_decision` 을 대신할 결정론적 대역. 게이트웨이 네트워크 호출 없이
    "이번 반복은 LLM 이 실제로 결정했다" 는 상황을 재현한다."""
    remaining = iter(sequence)

    def fake(state, reasoning_trace, pubmed_queries, iteration):
        return next(remaining, None)

    return fake


def test_llm_decision_reports_real_and_marks_trace_llm(monkeypatch):
    # "real" 경로에는 이 태스크 이전까지 실패할 수 있는 테스트가 없었다(리뷰 finding 3).
    # M1(agent.py:261, "_source"="llm" -> "fallback")과 M2(agent.py:222,
    # "source": source -> "source": "fallback") 모두 이 테스트로 잡혀야 한다.
    monkeypatch.setenv("LLM_PROVIDER", "real")
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", "http://dummy-gateway.invalid")
    # 결정 자체는 대역으로 통제하고, 보조 호출(쿼리 생성/요약)은 항상 폴백하도록
    # 고정해 이 테스트가 실제 네트워크에 의존하지 않게 한다.
    monkeypatch.setattr(agent, "_create_llm", lambda: None)
    monkeypatch.setattr(
        agent,
        "_llm_tool_decision",
        _sequenced_llm_decision([
            {"thought": "x-ray 로드", "action": "X-ray Result Loader", "actionInput": {}},
            {"thought": "상병 검증", "action": "Disease Validator", "actionInput": {}},
            {"thought": "처방 검증", "action": "Prescription Validator", "actionInput": {}},
            {"thought": "종료", "action": "FINALIZE", "actionInput": {}},
        ]),
    )

    response = run_validation_agent(_request())

    assert response.llmStatus == "real"
    disease_entries = [e for e in response.reasoningTrace if e["action"] == "Disease Validator"]
    assert disease_entries, "Disease Validator 스텝이 트레이스에 있어야 한다"
    assert all(e["source"] == "llm" for e in disease_entries)


def test_mixed_llm_and_fallback_decisions_produce_mixed_trace(monkeypatch):
    # LLM 이 한 반복에서는 성공하고 이후에는 실패(None)하는 경우, 트레이스는
    # 반복별로 실제 출처를 구분해서 보여줘야 한다.
    monkeypatch.setenv("LLM_PROVIDER", "real")
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", "http://dummy-gateway.invalid")
    monkeypatch.setattr(agent, "_create_llm", lambda: None)

    calls = {"n": 0}

    def fake_llm_tool_decision(state, reasoning_trace, pubmed_queries, iteration):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"thought": "x-ray 로드", "action": "X-ray Result Loader", "actionInput": {}}
        return None  # 이후 반복은 LLM 결정 실패 -> 휴리스틱 폴백으로 떨어져야 한다

    monkeypatch.setattr(agent, "_llm_tool_decision", fake_llm_tool_decision)

    response = run_validation_agent(_request())

    sources = {e["source"] for e in response.reasoningTrace}
    assert "llm" in sources, "첫 반복의 llm 소스가 트레이스에 남아야 한다"
    assert "fallback" in sources, "이후 반복의 폴백 소스도 트레이스에 남아야 한다"


def test_llm_decisions_with_failed_auxiliary_calls_do_not_mark_pubmed_as_llm(monkeypatch):
    # 리뷰 finding 1 커버리지: 도구 선택은 전부 LLM 이 했지만(all decisions "llm"),
    # 보조 호출(PubMed 쿼리 생성/요약)은 실패하는 시나리오. 이전에는
    # Pubmed Loader 트레이스 항목이 "이 스텝을 촉발한 결정"의 출처를 그대로
    # 물려받아 "llm" 로 찍혔다 — 실제로 쓰인 검색어는 하드코딩된 사전에서
    # 나왔는데도. llmStatus 자체는 (브리프가 지정한, 이번 태스크에서 건드리지
    # 않는) "결정 하나라도 llm 이면 real" 낙관 규칙 때문에 "real" 로 남을 수
    # 있다 — 그래서 이 테스트는 최상위 llmStatus 가 아니라, 실제로 거짓을 말할
    # 수 있었던 세부 신호(Pubmed Loader 트레이스의 source)를 검증한다.
    monkeypatch.setenv("LLM_PROVIDER", "real")
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", "http://dummy-gateway.invalid")
    monkeypatch.setattr(agent, "_create_llm", lambda: None)  # 보조 호출은 전부 실패/폴백
    monkeypatch.setattr(
        agent,
        "_llm_tool_decision",
        _sequenced_llm_decision([
            {"thought": "x-ray 로드", "action": "X-ray Result Loader", "actionInput": {}},
            {"thought": "상병 검증", "action": "Disease Validator", "actionInput": {}},
            {"thought": "처방 검증", "action": "Prescription Validator", "actionInput": {}},
            {"thought": "문헌 근거 확보", "action": "Pubmed Loader", "actionInput": {}},
        ]),
    )

    response = run_validation_agent(_request())

    pubmed_entries = [e for e in response.reasoningTrace if e["action"] == "Pubmed Loader"]
    assert pubmed_entries, "Pubmed Loader 스텝이 트레이스에 있어야 한다"
    assert all(e["source"] != "llm" for e in pubmed_entries), (
        "쿼리 생성이 실패해 하드코딩된 사전으로 대체됐다면, "
        "이 스텝을 촉발한 결정이 llm 이었더라도 llm 이라고 주장하면 안 된다"
    )
