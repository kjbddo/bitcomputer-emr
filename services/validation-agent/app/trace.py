"""트레이스 항목의 shape 과, `source` 가 무엇을 뜻하는지의 규칙.

`reasoningTrace` 는 의사 화면에 렌더된다(`apps/web/src/components/Diagnosis.tsx`
가 `action` + 스텝별 출처 표시 + `observation` 을 "검증 이유" 목록으로 잇는다).
그래서 이 파일의 규칙은 UI 문구의 진위를 직접 결정한다 — 여기서 한 칸만
관대해지면 화면이 없는 심의를 있다고 말한다.

`agent.py` 에서 떼어냈다. 파이프라인 순서(무엇을 언제 실행하나)와 트레이스
정직성 규칙(그 실행을 어떻게 기록하나)은 서로 다른 이유로 바뀐다.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

# 고정 파이프라인의 단계 수. `thought` 가 이 숫자를 그대로 쓴다 — "3/6" 은
# 읽는 사람에게 이 스텝이 선택의 결과가 아니라 정해진 순서의 한 칸임을 알려준다.
PIPELINE_STEPS = 6


def thought(index: int, description: str) -> str:
    """트레이스의 `thought`.

    모델이 쓴 심의문이 아니다. 옛 루프의 `thought` 는 "... 확인하기 위해
    Prescription Validator를 호출합니다" 처럼 1인칭 심의로 읽혔고, 실제
    페이로드와 모순되기까지 했다(F-H6 라이브 트레이스: 모델은 저장 처방을
    검사한다고 말했고 코드는 후보 처방을 넘겼다). 지금은 항상 실행되는 단계를
    그대로 진술한다 — 없는 심의를 있다고 말하지 않는다.
    """
    return f"고정 파이프라인 {index}/{PIPELINE_STEPS}: {description}"


def trace_step(
    trace: List[Dict[str, Any]],
    action: str,
    step_thought: str,
    action_input: Dict[str, Any],
    observation: Any,
    source: str,
) -> None:
    """트레이스 항목 하나. shape 은 응답 계약이다(models.py 참조).

    `source` 값 공간과 그 의미(ReAct 루프 제거 후):
    - "rule"     고정 파이프라인이 실행했고 내용도 결정론적이다.
    - "llm"      이 스텝이 실제로 쓴 내용을 이 서비스의 모델이 만들었다
                 (지금 이 값을 가지는 스텝은 없다).
    - "stub"     LLM_PROVIDER=stub 경로이거나, 실어온 상류 데이터가 스텁에서 왔다.
    - "fallback" 모델을 시도했으나 실패해 결정론적 대체물을 썼다.
    """
    trace.append({
        "thought": step_thought,
        "action": action,
        "actionInput": action_input,
        "observation": observation,
        "source": source,
    })


def invoke_tool(
    trace: List[Dict[str, Any]],
    action: str,
    step_thought: str,
    payload: Dict[str, Any],
    tool_obj: Any,
    source: str = "rule",
) -> Dict[str, Any]:
    """도구를 부르고 관측값을 트레이스에 남긴다. 예외도 관측값이다(GC-2)."""
    try:
        observation = tool_obj.invoke(payload)
    except Exception as exc:  # noqa: BLE001
        observation = {"status": "FAILED", "evidence": [str(exc)]}
    trace_step(trace, action, step_thought, payload, observation, source)
    return observation if isinstance(observation, dict) else {"status": "UNKNOWN", "raw": observation}


def downgrade_by_payload_source(source: str, payload_status: Optional[str]) -> str:
    """스텝의 페이로드 출처가 상류 스텁/실패면 강등한다. 승격은 절대 하지 않는다.

    Prescription Finder 스텝은 이제 항상 규칙이 예약한다(source="rule"). 그래도
    이 강등이 필요한 이유는, 그 스텝이 실어오는 **데이터가 어디서 왔는지** 가
    "규칙이 이 단계를 실행했다" 와 다른 사실이기 때문이다. 처방 RAG 가 스텁으로
    돌고 있으면 화면은 그 스텝을 "규칙 기반" 이 아니라 "(스텁)" 으로 읽어야
    한다 — 라이브에서 실제로 관측된 상태다(F-H3).

    반대 방향은 절대 없다: 상류가 "real" 이라고 보고했다고 해서 이 스텝이
    "llm" 이 되지는 않는다. 이 서비스의 모델이 이 스텝에 아무것도 쓰지 않았다.
    """
    if payload_status == "stub":
        return "stub"
    if payload_status == "real":
        return source
    # None(예외로 키 자체가 없음) / "fallback" / 그 밖의 값 -> fail-closed.
    return "fallback"
