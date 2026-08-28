"""E2E 픽스처.

실행 중인 compose 스택을 대상으로 한다. API_BASE_URL 로 대상을 바꿀 수 있다.
"""
from __future__ import annotations

import os

import httpx
import pytest

BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8080")


PASSWORD = "TestPassw0rd!"
BOOTSTRAP_PASSWORD = os.environ.get("BOOTSTRAP_SUPERUSER_PASSWORD", "")


def _new_client() -> httpx.Client:
    return httpx.Client(base_url=BASE_URL, timeout=60.0, follow_redirects=False)


def _login(client: httpx.Client, username: str, password: str) -> httpx.Response:
    return client.post("/api/user/login", json={"username": username, "password": password})


def admin_client() -> httpx.Client:
    """부트스트랩 SUPER_USER 로 로그인한다.

    공개 가입은 항상 DEFAULT 이므로(Task 9), 역할이 있는 계정은 SUPER_USER 가
    /api/admin/users 로 만들어야 한다.
    """
    assert BOOTSTRAP_PASSWORD, (
        "BOOTSTRAP_SUPERUSER_PASSWORD 가 필요하다. infra/.env 에 설정하고 "
        "spring-boot 를 재기동해야 admin 계정이 시드된다."
    )
    client = _new_client()
    response = _login(client, "admin", BOOTSTRAP_PASSWORD)
    assert response.status_code == 200, f"admin 로그인 실패: {response.text}"
    return client


def login_as(role: str) -> httpx.Client:
    """해당 역할의 계정을 준비하고 로그인한 클라이언트를 만든다."""
    username = f"e2e_{role.lower()}"

    if role == "SUPER_USER":
        return admin_client()

    admin = admin_client()
    admin.post(
        "/api/admin/users",
        headers=csrf_headers(admin),
        json={
            "name": username,
            "deptId": 1,
            "role": role,
            "username": username,
            "password": PASSWORD,
        },
    )  # 이미 있으면 409 — 그대로 진행한다
    admin.close()

    client = _new_client()
    response = _login(client, username, PASSWORD)
    assert response.status_code == 200, f"{role} 로그인 실패: {response.text}"
    assert "access_token" in client.cookies, "로그인 응답에 access_token 쿠키가 없다"
    return client


def csrf_headers(client: httpx.Client) -> dict[str, str]:
    """상태 변경 요청에 필요한 CSRF 헤더를 만든다.

    서버(CookieCsrfTokenRepository + CsrfCookieFilter 조합)는 XSRF-TOKEN 쿠키를
    "실려 들어온" 요청마다 그 자리에서 무효화(Max-Age=0)하고, 쿠키가 없는 요청에
    한해서만 새 토큰을 발급한다 — 사실상 1회용이다. 그래서 뮤테이션 요청을
    연달아 보내면 두 번째 요청부터는 클라이언트가 들고 있는 토큰이 이미 죽어
    있다. 토큰이 없을 때는 가벼운 GET(공개 엔드포인트)으로 새 토큰을 먼저
    받아온 뒤 그 값을 헤더에 실어 보낸다.
    """
    token = client.cookies.get("XSRF-TOKEN")
    if not token:
        client.get("/actuator/health")
        token = client.cookies.get("XSRF-TOKEN")
    return {"X-XSRF-TOKEN": token} if token else {}


@pytest.fixture()
def doctor() -> httpx.Client:
    client = login_as("DOCTOR")
    yield client
    client.close()


@pytest.fixture()
def receptionist() -> httpx.Client:
    client = login_as("RECEPTIONIST")
    yield client
    client.close()


@pytest.fixture()
def super_user() -> httpx.Client:
    client = login_as("SUPER_USER")
    yield client
    client.close()
