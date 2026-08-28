import os

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
    assert all(entry.get("source") == "fallback" for entry in response.reasoningTrace)


def test_trace_entries_always_carry_source(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    response = run_validation_agent(_request())
    for entry in response.reasoningTrace:
        assert "source" in entry, "source 가 없으면 출처를 구분할 수 없다"
