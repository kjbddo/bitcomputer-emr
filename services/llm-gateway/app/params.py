"""파라미터 계약 정규화 — **제공자마다 다르다.**

한 제공자의 규칙을 다른 제공자에 복사해 오지 않는다. 아래 두 규칙 집합은
근거가 서로 다르며, 근거의 강도도 다르다.

게이트웨이가 아는 것은 파라미터 이름뿐이며 값의 의미는 모른다(GC-1).
드롭·변환은 반드시 기록으로 남긴다(GC-2).
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

# OpenAI 직접 호출에서 luna 가 받지 않는(또는 무시하는) 것으로 판단해 제거하는
# 파라미터. 근거와 미확인 사항은 spec §5.1 참조.
#
# 이것은 **OpenAI 경로 한정 규칙이다.** Bedrock 의 OpenAI 호환 경로에서 luna 가
# 같은 필드를 거부하는지는 확인된 바 없고, AWS 문서의 OpenAI 모델 예제는 오히려
# temperature·top_p 를 보낸다. 확인되지 않은 것을 근거로 값을 버리면 조용한
# 손실이 되므로 Bedrock 규칙에는 넣지 않았다.
DROPPED_PARAMS = ("temperature", "top_p")


def _rename_max_tokens(result: Dict[str, Any], notes: List[str]) -> None:
    """max_tokens -> max_completion_tokens.

    양쪽 제공자 모두에 적용한다. OpenAI 문서(luna)와 AWS 문서(Bedrock 의 OpenAI
    호환 요청 본문·배치 입력) 가 모두 max_completion_tokens 를 쓴다.
    """
    if "max_tokens" not in result:
        return
    if "max_completion_tokens" in result:
        result.pop("max_tokens")
        notes.append("dropped:max_tokens(max_completion_tokens already set)")
    else:
        result["max_completion_tokens"] = result.pop("max_tokens")
        notes.append("renamed:max_tokens->max_completion_tokens")


def normalize_openai_params(
    payload: Dict[str, Any], *, default_reasoning_effort: str
) -> Tuple[Dict[str, Any], List[str]]:
    """OpenAI 직접 호출용 luna 계약.

    입력 payload 는 변형하지 않는다.

    Returns:
        (정규화된 본문, 무엇을 드롭·변환했는지의 기록)
    """
    # 얕은 복사다. 지금은 최상위 키만 읽고 쓰므로 충분하지만,
    # 나중에 messages 나 response_format 같은 중첩 구조를 건드리게 되면
    # 이 복사는 호출자의 입력을 더 이상 보호하지 못한다.
    result = dict(payload)
    notes: List[str] = []

    for key in DROPPED_PARAMS:
        if key in result:
            result.pop(key)
            notes.append(f"dropped:{key}")

    _rename_max_tokens(result, notes)

    if "reasoning_effort" not in result:
        result["reasoning_effort"] = default_reasoning_effort
        notes.append(f"injected:reasoning_effort={default_reasoning_effort}")

    return result, notes


def normalize_bedrock_params(
    payload: Dict[str, Any], *, model_id: str
) -> Tuple[Dict[str, Any], List[str]]:
    """Bedrock 의 OpenAI 호환 경로용 계약.

    OpenAI 쪽보다 **하는 일이 적다.** 확인된 것만 한다:

    - `max_tokens` -> `max_completion_tokens`: AWS 문서의 OpenAI 호환 요청
      예제가 전부 max_completion_tokens 를 쓴다.
    - 모델 ID 치환: 호출 서비스는 OpenAI 모델 ID(`gpt-5.6-luna`)를 보내는데
      Bedrock 에서 그 ID 는 유효하지 않다. bedrock-runtime 에서 luna 는
      교차 리전 추론 프로파일 ID(`us.` / `global.` / `in.`) 전용이고,
      bedrock-mantle 에서는 베어 ID(`openai.gpt-5.6-luna`)다. 호출자를 고치지
      않고 제공자를 바꾸려면 이 치환이 게이트웨이 안에 있어야 한다.

    하지 **않는** 것과 그 이유:

    - `temperature`·`top_p` 드롭: Bedrock 에서 luna 가 이 필드를 거부하는지
      확인되지 않았다. 실측 전까지는 통과시킨다(§10 미확인 항목).
    - `reasoning_effort` 주입: 같은 이유. 호출자가 보내면 그대로 간다.

    입력 payload 는 변형하지 않는다.
    """
    result = dict(payload)
    notes: List[str] = []

    _rename_max_tokens(result, notes)

    incoming_model = result.get("model")
    if incoming_model != model_id:
        result["model"] = model_id
        notes.append(f"mapped:model={incoming_model}->{model_id}")

    return result, notes
