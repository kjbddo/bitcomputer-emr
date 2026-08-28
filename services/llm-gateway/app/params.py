"""luna 파라미터 계약 정규화.

gpt-5.6-luna 는 이전 세대와 받는 파라미터가 다르다. 서비스(LangChain 등)가
관습적으로 보내는 필드를 여기서 한 번에 맞춘다.

게이트웨이가 아는 것은 파라미터 이름뿐이며 값의 의미는 모른다(GC-1).
드롭·변환은 반드시 기록으로 남긴다(GC-2).
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

# luna 가 받지 않는(또는 무시하는) 것으로 판단해 제거하는 파라미터.
# 근거와 미확인 사항은 spec §5.1 참조.
DROPPED_PARAMS = ("temperature", "top_p")


def normalize_params(
    payload: Dict[str, Any], *, default_reasoning_effort: str
) -> Tuple[Dict[str, Any], List[str]]:
    """요청 본문을 luna 계약에 맞게 정규화한다.

    입력 payload 는 변형하지 않는다.

    Returns:
        (정규화된 본문, 무엇을 드롭·변환했는지의 기록)
    """
    result = dict(payload)
    notes: List[str] = []

    for key in DROPPED_PARAMS:
        if key in result:
            result.pop(key)
            notes.append(f"dropped:{key}")

    if "max_tokens" in result:
        if "max_completion_tokens" in result:
            result.pop("max_tokens")
            notes.append("dropped:max_tokens(max_completion_tokens already set)")
        else:
            result["max_completion_tokens"] = result.pop("max_tokens")
            notes.append("renamed:max_tokens->max_completion_tokens")

    if "reasoning_effort" not in result:
        result["reasoning_effort"] = default_reasoning_effort
        notes.append(f"injected:reasoning_effort={default_reasoning_effort}")

    return result, notes
