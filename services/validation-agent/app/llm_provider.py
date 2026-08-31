"""LLM provider 선택 (ValidationAgent).

`stub` 은 게이트웨이를 한 번도 부르지 않는 경로다. 이 서비스가 모델을 쓰는
자리는 현재 없고(gateway.py 참조), stub 모드에서는
그 둘이 규칙 기반 대체물로 대체되며 `llmStatus` 가 "stub" 이 된다.

옛 `stub_tool_decision(iteration)` 은 ReAct 도구 선택 루프에 결정론적 순서를
먹이기 위한 것이었다. 루프를 제거하면서 함께 삭제했다 — 실행 순서는 이제
`agent.py` 의 고정 파이프라인이고, provider 와 무관하게 같다.
"""
from __future__ import annotations

import os


def resolve_provider() -> str:
    value = (os.environ.get("LLM_PROVIDER") or "real").strip().lower()
    return "stub" if value == "stub" else "real"
