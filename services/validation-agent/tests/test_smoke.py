"""서비스가 뜨고 헬스 응답이 계약대로인지, stub LLM 경로가 동작하는지 확인한다.

app.main 은 LLM_PROVIDER != "stub" 이면 import 시점에 LLM_GATEWAY_BASE_URL 을 요구하고,
startup 이벤트에서 RabbitMQ 워커를 백그라운드로 띄운다. smoke test 는 외부 연결
없이 앱 기동만 확인하므로 import 전에 stub 모드로 고정하고 RabbitMQ 는 끈다.
"""
import os

os.environ["LLM_PROVIDER"] = "stub"
os.environ.setdefault("VALIDATION_RABBITMQ_ENABLED", "false")

from fastapi.testclient import TestClient

from app.main import app
from app.llm_provider import resolve_provider

client = TestClient(app)


def test_health_returns_200():
    assert client.get("/health").status_code == 200


def test_openapi_exposes_run_endpoint():
    schema = client.get("/openapi.json").json()
    assert "/api/agent/validation/run" in schema["paths"]


def test_stub_provider_selected_by_env(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    assert resolve_provider() == "stub"


def test_stub_provider_never_calls_the_gateway(monkeypatch):
    """stub 모드는 게이트웨이를 부르지 않는다.

    옛 `stub_tool_decision` 은 ReAct 루프에 결정론적 도구 순서를 먹였다. 루프가
    사라진 지금 stub 이 지켜야 하는 계약은 "모델 호출이 0회" 하나다 — 실행
    순서는 provider 와 무관하게 고정 파이프라인이다.
    """
    import app.agent as agent
    from app.models import ValidationAgentRequest

    calls = {"n": 0}

    def exploding_llm():
        calls["n"] += 1
        raise AssertionError("stub 모드에서 게이트웨이 클라이언트를 만들면 안 된다")

    monkeypatch.setenv("LLM_PROVIDER", "stub")
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", "http://dummy-gateway.invalid")
    monkeypatch.setattr(agent, "create_llm", exploding_llm)
    monkeypatch.setattr(agent, "pubmed_loader", _NoResultPubmedLoader())
    monkeypatch.setattr(agent, "prescription_finder", _NoCandidateFinder())

    response = agent.run_validation_agent(ValidationAgentRequest(historyId=1, symptoms="기침"))

    assert calls["n"] == 0
    assert response.llmStatus == "stub"


class _NoResultPubmedLoader:
    def invoke(self, payload=None):
        return {"status": "NO_RESULT", "evidence": ["PubMed 검색 결과 없음"], "articles": []}


class _NoCandidateFinder:
    def invoke(self, payload=None):
        return {
            "status": "LOADED",
            "evidence": [],
            "candidatePrescriptions": [],
            "recommendationLlmStatus": "stub",
            "recommendationVerification": None,
        }
