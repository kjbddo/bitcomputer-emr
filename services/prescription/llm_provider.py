"""LLM provider 선택.

stub 은 결정론적 고정 응답을 돌려준다. CI 와 grounding 평가에서 LLM 출력을
고정하기 위한 것이며, 임상적 의미는 없다.
"""
from __future__ import annotations

import json
import os
from typing import Any

STUB_MARKER = "STUB: 고정 응답이며 임상 근거가 없습니다."


def resolve_provider() -> str:
    value = (os.environ.get("LLM_PROVIDER") or "real").strip().lower()
    return "stub" if value == "stub" else "real"


def _row_name(row: Any) -> str:
    if not isinstance(row, dict):
        return ""
    for key in ("처방명", "prescription_name", "name"):
        value = row.get(key)
        if value:
            return str(value)
    return ""


def _row_code(row: Any) -> str:
    if not isinstance(row, dict):
        return ""
    for key in ("처방코드", "prescription_code", "code"):
        value = row.get(key)
        if value:
            return str(value)
    return ""


def stub_prescription_response(top_rx: Any) -> str:
    """parse_prescriptions_llm_response 가 파싱 가능한 JSON 문자열을 만든다."""
    rows = top_rx if isinstance(top_rx, list) else []
    picked = [r for r in rows if _row_name(r) or _row_code(r)][:3]

    items = []
    for rank in (1, 2, 3):
        row = picked[rank - 1] if rank <= len(picked) else None
        items.append({
            "rank": rank,
            "name": _row_name(row) or "데이터 부족: top_rx 비어 있음",
            "prescription_code": _row_code(row) or "미기재",
            "dosage": "미기재",
            "reason": STUB_MARKER,
        })
    return json.dumps({"prescriptions": items}, ensure_ascii=False)
