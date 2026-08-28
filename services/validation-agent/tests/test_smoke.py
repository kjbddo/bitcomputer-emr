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
from app.llm_provider import resolve_provider, stub_tool_decision

client = TestClient(app)


def test_health_returns_200():
    assert client.get("/health").status_code == 200


def test_openapi_exposes_run_endpoint():
    schema = client.get("/openapi.json").json()
    assert "/api/agent/validation/run" in schema["paths"]


def test_stub_provider_selected_by_env(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    assert resolve_provider() == "stub"


def test_stub_decision_terminates_with_finalize():
    assert stub_tool_decision(99)["action"] == "FINALIZE"
