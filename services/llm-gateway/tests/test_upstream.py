import httpx
import pytest

from app.providers.base import UpstreamRequest
from app.upstream import UpstreamError, call_upstream

URL = "https://upstream.test/v1/chat/completions"
PAYLOAD = {"model": "m", "messages": []}


def _request(api_key: str = "k", url: str = URL) -> UpstreamRequest:
    """제공자가 조립해 넘겨주는 것과 같은 모양.

    call_upstream 은 상류가 어디인지·어떻게 인증하는지 모른다. 이 객체를
    그대로 보낼 뿐이다.
    """
    return UpstreamRequest(
        provider="openai",
        provider_configured="openai",
        url=url,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        body=PAYLOAD,
        auth_mode="bearer:openai_api_key",
    )


async def _noop_sleep(_seconds: float) -> None:
    return None


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_success_first_attempt():
    def handler(_request):
        return httpx.Response(200, json={"ok": True})

    async with _client(handler) as client:
        body, attempts = await call_upstream(
            client, request=_request(), max_retries=2, sleep=_noop_sleep
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
            client, request=_request(), max_retries=2, sleep=_noop_sleep
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
            client, request=_request(), max_retries=2, sleep=_noop_sleep
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
                client, request=_request(), max_retries=2, sleep=_noop_sleep
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
                client, request=_request(), max_retries=2, sleep=_noop_sleep
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
            client, request=_request(), max_retries=2, sleep=_noop_sleep
        )
    assert attempts == 2


async def test_api_key_not_in_error_detail():
    def handler(_request):
        return httpx.Response(401, text="unauthorized")

    async with _client(handler) as client:
        with pytest.raises(UpstreamError) as exc:
            await call_upstream(
                client,
                request=_request(api_key="super-secret-key"),
                max_retries=0,
                sleep=_noop_sleep,
            )
    assert "super-secret-key" not in exc.value.detail


async def test_non_json_2xx_body_becomes_upstream_error():
    """계약상 실패는 전부 UpstreamError 여야 한다.

    JSONDecodeError 가 그대로 올라가면 UpstreamError 만 잡는 호출자가 놓친다.
    """
    def handler(_request):
        return httpx.Response(200, text="not json at all")

    async with _client(handler) as client:
        with pytest.raises(UpstreamError) as exc:
            await call_upstream(
                client, request=_request(), max_retries=2, sleep=_noop_sleep
            )
    assert exc.value.status == 200
    assert exc.value.attempts == 1, "본문이 깨진 것은 재시도로 낫지 않는다"


async def test_non_json_2xx_error_does_not_leak_key():
    def handler(_request):
        return httpx.Response(200, text="not json")

    async with _client(handler) as client:
        with pytest.raises(UpstreamError) as exc:
            await call_upstream(
                client,
                request=_request(api_key="super-secret-key"),
                max_retries=0,
                sleep=_noop_sleep,
            )
    assert "super-secret-key" not in exc.value.detail


def test_backoff_progression():
    """0.5 / 1.0 / 2.0. 공식이 바뀌면 어떤 테스트도 안 잡던 구간이었다."""
    from app.upstream import _backoff_seconds

    assert _backoff_seconds(1) == 0.5
    assert _backoff_seconds(2) == 1.0
    assert _backoff_seconds(3) == 2.0


# call_upstream 이 제공자가 만든 헤더·URL·본문을 그대로 보내는지.
# 여기서 헤더를 다시 조립하기 시작하면 인증이 두 곳에 살게 된다.
async def test_request_is_sent_verbatim():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = request.read().decode()
        return httpx.Response(200, json={"ok": True})

    request = UpstreamRequest(
        provider="bedrock",
        provider_configured="bedrock",
        url="https://bedrock-runtime.us-west-2.amazonaws.com/openai/v1/chat/completions",
        headers={"Authorization": "Bearer bedrock-key", "Content-Type": "application/json"},
        body={"model": "global.openai.gpt-5.6-luna", "messages": []},
        auth_mode="bearer:bedrock_api_key",
    )
    async with _client(handler) as client:
        await call_upstream(client, request=request, max_retries=0, sleep=_noop_sleep)

    assert seen["url"] == request.url
    assert seen["auth"] == "Bearer bedrock-key"
    assert "global.openai.gpt-5.6-luna" in seen["body"]


# GC-7: UpstreamRequest 는 자격증명을 들고 다닌다. repr 로 새면 안 된다.
def test_request_repr_does_not_leak_headers():
    request = UpstreamRequest(
        provider="openai",
        provider_configured="openai",
        url=URL,
        headers={"Authorization": "Bearer super-secret-key"},
        body=PAYLOAD,
        auth_mode="bearer:openai_api_key",
    )
    assert "super-secret-key" not in repr(request)
