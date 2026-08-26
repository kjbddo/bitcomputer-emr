"""서비스가 뜨고 헬스/스키마 응답이 계약대로인지 확인한다.

prescription_api 는 import 시점에 env_check.require_env(["ARANGO_PASSWORD", ...])
를 호출하고, LLM_PROVIDER != "stub" 이면 GOOGLE_API_KEY 도 요구한다. smoke test 는
실제 Arango/Gemini 연결 없이 앱 기동/스키마만 확인하므로, import 전에 stub 모드로
고정한다.
"""
import os

os.environ.setdefault("ARANGO_PASSWORD", "test-only-not-used")
os.environ["LLM_PROVIDER"] = "stub"
os.environ.pop("GOOGLE_API_KEY", None)

from fastapi.testclient import TestClient

from prescription_api import app

client = TestClient(app)


def test_health_returns_200():
    assert client.get("/health").status_code == 200


def test_openapi_exposes_recommend_endpoint():
    schema = client.get("/openapi.json").json()
    assert "/api/agent/prescription/recommend" in schema["paths"]


def test_recommend_response_schema_declares_engine_status():
    schema = client.get("/openapi.json").json()
    properties = schema["components"]["schemas"]["PrescriptionRecommendResponse"]["properties"]
    assert "engineStatus" in properties
