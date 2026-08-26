"""LLM provider 선택 (ValidationAgent).

stub 은 결정론적 도구 선택 순서를 돌려준다. CI 에서 OpenAI 호출 없이
ReAct 루프를 통과시키기 위한 것이며, 임상적 의미는 없다.
"""
from __future__ import annotations

import os
from typing import Any, Dict

STUB_SEQUENCE = [
    "X-ray Result Loader",
    "Disease Validator",
    "Prescription Validator",
    "FINALIZE",
]


def resolve_provider() -> str:
    value = (os.environ.get("LLM_PROVIDER") or "real").strip().lower()
    return "stub" if value == "stub" else "real"


def stub_tool_decision(iteration: int) -> Dict[str, Any]:
    """iteration 은 1부터 시작한다."""
    index = max(0, iteration - 1)
    action = STUB_SEQUENCE[index] if index < len(STUB_SEQUENCE) else "FINALIZE"
    return {
        "thought": f"STUB 결정 {iteration}: {action}",
        "action": action,
        "actionInput": {},
    }
