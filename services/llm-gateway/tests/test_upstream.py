import httpx
import pytest

from app.upstream import UpstreamError, call_upstream

URL = "https://upstream.test/v1/chat/completions"
PAYLOAD = {"model": "m", "messages": []}


async def _noop_sleep(_seconds: float) -> None:
    return None


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_success_first_attempt():
    def handler(_request):
        return httpx.Response(200, json={"ok": True})

    async with _client(handler) as client:
        body, attempts = await call_upstream(
            client, url=URL, api_key="k", payload=PAYLOAD, max_retries=2, sleep=_noop_sleep
        )
    assert body == {"ok": True}
    assert attempts == 1


async def test_retries_on_429_then_succeeds():
    calls = {"n": 0}

    def handler(_request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, text="slow down")
        return httpx.Response(200, json={"ok": True})

    async with _client(handler) as client:
        body, attempts = await call_upstream(
            client, url=URL, api_key="k", payload=PAYLOAD, max_retries=2, sleep=_noop_sleep
        )
    assert body == {"ok": True}
    assert attempts == 2


async def test_retries_on_503_then_succeeds():
    calls = {"n": 0}

    def handler(_request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503, text="unavailable")
        return httpx.Response(200, json={"ok": True})

    async with _client(handler) as client:
        _, attempts = await call_upstream(
            client, url=URL, api_key="k", payload=PAYLOAD, max_retries=2, sleep=_noop_sleep
        )
    assert attempts == 2


async def test_does_not_retry_on_400():
    calls = {"n": 0}

    def handler(_request):
        calls["n"] += 1
        return httpx.Response(400, text="bad request")

    async with _client(handler) as client:
        with pytest.raises(UpstreamError) as exc:
            await call_upstream(
                client, url=URL, api_key="k", payload=PAYLOAD, max_retries=2, sleep=_noop_sleep
            )
    assert calls["n"] == 1, "4xx 는 재시도 대상이 아니다"
    assert exc.value.status == 400
    assert exc.value.attempts == 1


async def test_gives_up_after_max_retries():
    calls = {"n": 0}

    def handler(_request):
        calls["n"] += 1
        return httpx.Response(500, text="boom")

    async with _client(handler) as client:
        with pytest.raises(UpstreamError) as exc:
            await call_upstream(
                client, url=URL, api_key="k", payload=PAYLOAD, max_retries=2, sleep=_noop_sleep
            )
    assert calls["n"] == 3, "최초 1회 + 재시도 2회"
    assert exc.value.attempts == 3


async def test_connection_error_is_retried():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ConnectError("boom", request=request)
        return httpx.Response(200, json={"ok": True})

    async with _client(handler) as client:
        _, attempts = await call_upstream(
            client, url=URL, api_key="k", payload=PAYLOAD, max_retries=2, sleep=_noop_sleep
        )
    assert attempts == 2


async def test_api_key_not_in_error_detail():
    def handler(_request):
        return httpx.Response(401, text="unauthorized")

    async with _client(handler) as client:
        with pytest.raises(UpstreamError) as exc:
            await call_upstream(
                client,
                url=URL,
                api_key="super-secret-key",
                payload=PAYLOAD,
                max_retries=0,
                sleep=_noop_sleep,
            )
    assert "super-secret-key" not in exc.value.detail
