"""계측 레코드 조립.

구조화 로그로 내보내 CloudWatch Logs 에서 집계한다(spec §7).
설정 객체를 받지만 단가만 읽는다 — API 키는 레코드에 절대 넣지 않는다(GC-7).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.config import Settings


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
    usage: Optional[Dict[str, Any]],
    latency_ms: int,
    attempts: int,
    outcome: str,
    param_notes: List[str],
    settings: Settings,
) -> Dict[str, Any]:
    """요청 한 건의 계측 레코드를 만든다.

    outcome 은 "success" / "success_after_retry" / "failed" 중 하나다.
    """
    usage = usage or {}
    input_tokens = _coerce_token_count(usage.get("prompt_tokens"))
    output_tokens = _coerce_token_count(usage.get("completion_tokens"))

    cost = (
        input_tokens / 1_000_000 * settings.input_price_per_1m
        + output_tokens / 1_000_000 * settings.output_price_per_1m
    )

    return {
        "model": model,
        "caller": caller,
        "inputTokens": input_tokens,
        "outputTokens": output_tokens,
        "latencyMs": latency_ms,
        "attempts": attempts,
        "outcome": outcome,
        "paramNotes": param_notes,
        "estimatedCostUsd": round(cost, 6),
    }
