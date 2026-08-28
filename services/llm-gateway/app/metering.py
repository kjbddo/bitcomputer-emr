"""계측 레코드 조립.

구조화 로그로 내보내 CloudWatch Logs 에서 집계한다(spec §7).
설정 객체를 받지만 단가만 읽는다 — API 키는 레코드에 절대 넣지 않는다(GC-7).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.config import Settings


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
    input_tokens = int(usage.get("prompt_tokens") or 0)
    output_tokens = int(usage.get("completion_tokens") or 0)

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
