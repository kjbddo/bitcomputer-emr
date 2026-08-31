"""계측 레코드 조립.

구조화 로그로 내보내 CloudWatch Logs 에서 집계한다(spec §7).
설정 객체를 받지만 단가만 읽는다 — API 키는 레코드에 절대 넣지 않는다(GC-7).

**provider 는 설정에서 오지 않는다.** ExecutionFacts 로만 들어오며, 그 사실은
요청을 실제로 만든 제공자 객체에서 도출된다(app/providers/base.facts_for).
이 모듈이 settings.provider 를 읽는 순간, 설정만 바꾸고 호출은 다른 데로 나가는
상태를 로그가 감추게 된다 — llmStatus·engineStatus·embeddingVersion 에서 이미
세 번 겪은 결함이다.

usage 필드 이름도 이 모듈이 모른다. 어느 필드를 읽는지는 제공자가 알고
(Provider.read_usage), 여기는 그 결과를 정수로 만드는 일만 한다.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.config import Settings
from app.providers.base import ExecutionFacts, RawUsage


def _coerce_token_count(value: Any) -> int:
    """토큰 수를 정수로. 해석 불가면 0.

    이 함수는 LLM 호출이 이미 성공한 뒤 응답 경로에서 불린다. 상류가 이상한
    usage 를 주었다고 여기서 예외를 던지면, 멀쩡히 받아온 응답이 계측 때문에
    실패한다 — 관측이 본 기능을 깨뜨리는 셈이다. 그래서 삼키고 0으로 둔다.

    음수는 0 으로 눌러 비용 계산이 음수가 되는 것을 막는다.
    """
    try:
        count = int(value or 0)
    except (TypeError, ValueError):
        return 0
    return max(0, count)


def build_record(
    *,
    model: str,
    caller: str,
    usage: RawUsage,
    latency_ms: int,
    attempts: int,
    outcome: str,
    param_notes: List[str],
    settings: Settings,
    execution: ExecutionFacts,
    upstream_status: Optional[int] = None,
    failure_detail: Optional[str] = None,
) -> Dict[str, Any]:
    """요청 한 건의 계측 레코드를 만든다.

    outcome 은 "success" / "success_after_retry" / "failed" 중 하나다.

    provider 는 실제로 요청을 만든 제공자, providerConfigured 는 설정이 요구한
    이름이다. 정상 경로에서는 같고, 어긋난 것 자체가 봐야 할 신호다.

    upstreamStatus 는 실패의 성격을 가른다 — Bedrock API 키 만료는 401/403 으로
    나타나므로 이 값이 없으면 만료를 일반 장애와 구별할 수 없다.

    failure_detail 은 upstreamStatus 가 없을 때 남는 유일한 단서다. 상류에
    닿지도 못한 실패(DNS, 연결 거부, 타임아웃)는 status 가 None 이라, 이것이
    없으면 레코드가 "실패했다"고만 말하고 왜인지는 말하지 않는다 — 운영자가
    타임아웃과 네트워크 단절을 구별할 방법이 사라진다. 상류 본문은 여기 싣지
    않는다(GC-7): 예외 타입과 상태 코드까지만이고, 본문은 upstream.py 에서
    이미 300자로 잘려 온다.
    """
    input_tokens = _coerce_token_count(usage.input_raw)
    output_tokens = _coerce_token_count(usage.output_raw)

    cost = (
        input_tokens / 1_000_000 * settings.input_price_per_1m
        + output_tokens / 1_000_000 * settings.output_price_per_1m
    )

    return {
        "provider": execution.provider,
        "providerConfigured": execution.provider_configured,
        "upstreamHost": execution.upstream_host,
        "authMode": execution.auth_mode,
        "model": model,
        "caller": caller,
        "inputTokens": input_tokens,
        "outputTokens": output_tokens,
        "latencyMs": latency_ms,
        "attempts": attempts,
        "outcome": outcome,
        "upstreamStatus": upstream_status,
        "failureDetail": failure_detail,
        "paramNotes": param_notes,
        "estimatedCostUsd": round(cost, 6),
    }
