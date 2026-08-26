"""서비스가 뜨고 헬스 체크 엔드포인트가 계약대로인지 확인한다."""
import pytest

from app import app as flask_app


@pytest.fixture()
def client():
    flask_app.config.update(TESTING=True)
    return flask_app.test_client()


def test_is_running_returns_200(client):
    assert client.get("/api/ai/is_running").status_code == 200
