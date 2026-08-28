"""상류(Bedrock mantle) 호출과 재시도.

도메인 판단을 하지 않는다. 일시적 실패를 재시도하고, 끝내 실패하면
타입이 있는 에러를 올린다. 저하시킬지 실패시킬지는 서비스가 정한다(spec §6.1).
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, Tuple

import httpx

# 재시도해서 결과가 달라질 수 있는 상태코드만 넣는다.
# 4xx(429 제외)는 요청 자체가 잘못된 것이라 재시도해도 같다.
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})

SleepFn = Callable[[float], Awaitable[None]]


class UpstreamError(Exception):
    """상류 호출이 최종 실패했다."""

    def __init__(self, *, status: int | None, detail: str, attempts: int) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail
        self.attempts = attempts


def _backoff_seconds(attempt: int) -> float:
    """1회차 0.5s, 2회차 1.0s, 3회차 2.0s."""
    return 0.5 * (2 ** (attempt - 1))


async def call_upstream(
    client: httpx.AsyncClient,
    *,
    url: str,
    api_key: str,
    payload: Dict[str, Any],
    max_retries: int,
    sleep: SleepFn,
) -> Tuple[Dict[str, Any], int]:
    """상류를 호출한다.

    Returns:
        (응답 JSON, 총 시도 횟수)

    Raises:
        UpstreamError: 재시도 상한까지 실패했거나 재시도 대상이 아닌 실패.
    """
    # 헤더는 매 시도마다 새로 만든다. 에러 메시지에 절대 싣지 않는다(GC-7).
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    attempts = 0
    last_status: int | None = None
    last_detail = ""

    while True:
        attempts += 1
        try:
            response = await client.post(url, headers=headers, json=payload)
        except httpx.HTTPError as exc:
            last_status = None
            last_detail = f"connection error: {type(exc).__name__}"
        else:
            if response.status_code < 400:
                try:
                    return response.json(), attempts
                except ValueError as exc:
                    # 2xx 인데 본문이 JSON 이 아니다. 재시도해도 같을 가능성이 높고,
                    # 무엇보다 여기서 그냥 터뜨리면 JSONDecodeError 가 타입 없이
                    # 호출자에게 올라가 UpstreamError 만 잡는 쪽이 놓친다.
                    # 계약("실패는 UpstreamError")을 지키기 위해 감싼다.
                    raise UpstreamError(
                        status=response.status_code,
                        detail=(
                            f"upstream returned {response.status_code} "
                            f"with non-JSON body: {type(exc).__name__}"
                        ),
                        attempts=attempts,
                    ) from exc
            last_status = response.status_code
            last_detail = f"upstream returned {response.status_code}: {response.text[:300]}"
            if response.status_code not in RETRYABLE_STATUS:
                raise UpstreamError(status=last_status, detail=last_detail, attempts=attempts)

        if attempts > max_retries:
            raise UpstreamError(status=last_status, detail=last_detail, attempts=attempts)
        await sleep(_backoff_seconds(attempts))
