"""서비스가 뜨고 헬스 응답이 계약대로인지 확인한다.

app.main 은 import 시점에 env_check.require_env(["ARANGO_PASSWORD"]) 를 호출한다.
smoke test 는 실제 ArangoDB 연결 없이 앱 기동/스키마만 확인하므로, import 전에
더미 값을 채워 넣는다.
"""
import os

os.environ.setdefault("ARANGO_PASSWORD", "test-only-not-used")

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_200():
    response = client.get("/health")
    assert response.status_code == 200


def test_health_body_is_json_object():
    body = client.get("/health").json()
    assert isinstance(body, dict)


def test_openapi_exposes_infer_endpoint():
    schema = client.get("/openapi.json").json()
    assert "/infer" in schema["paths"]


def test_infer_response_schema_declares_engine_status():
    schema = client.get("/openapi.json").json()
    properties = schema["components"]["schemas"]["InferenceResponse"]["properties"]
    assert "engineStatus" in properties
