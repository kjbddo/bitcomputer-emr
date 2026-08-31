"""게이트웨이 클라이언트와, 이 실행에서 모델이 실제로 무엇을 썼는지의 장부.

이 서비스가 게이트웨이를 부르는 자리는 **둘뿐**이다(아키텍처 리뷰 §5 권고 2):

1. PubMed 질의 생성 — 한국어 임상 맥락을 영어 검색어로 번역한다.
2. PubMed 근거 요약 — 초록을 의료진 검토용 문장으로 줄인다.

도구 선택 루프(옛 `_decide_next_tool`)는 제거됐다. 그 루프가 결정하던 것은
"다음에 어떤 도구 이름을 부를까" 뿐이었고, 실제 실행 순서는 도메인이 정한
고정 순서였다.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

from langchain_openai import ChatOpenAI

logger = logging.getLogger("validation_agent.gateway")

# 이 실행에서 모델이 무엇을 썼는지의 값 공간.
#   "llm"      모델이 실제로 문장을 만들었다
#   "stub"     LLM_PROVIDER=stub — 게이트웨이를 부르지 않았다
#   "fallback" 모델을 시도했으나(또는 시도할 수 없어) 결정론적 대체물을 썼다
ModelCallSource = str


class ModelCallLedger:
    """`llmStatus` 가 근거로 삼는 유일한 장부.

    **여기에 기록할 수 있는 것은 응답 본문의 문장을 만드는 모델 호출뿐이다.**
    상류 서비스가 보고한 출처(`recommendationLlmStatus`)나 도구 실행 결과를
    여기에 밀어넣으면, 이 서비스가 모델을 쓰지 않았는데도 `llmStatus="real"`
    이 나가는 Task 6 결함이 재발한다. 그 값들은 트레이스 스텝의 `source` 와
    관측값 안에만 남긴다.

    옛 구현은 "도구 이름을 고른 결정"을 여기에 넣었다. 그 결정들이 사라진
    지금, 장부가 세는 것은 처음으로 "모델이 이 응답에 무엇을 썼는가" 다.
    """

    def __init__(self) -> None:
        self._calls: List[Dict[str, str]] = []

    def record(self, call: str, source: ModelCallSource) -> ModelCallSource:
        self._calls.append({"call": call, "source": source})
        return source

    @property
    def sources(self) -> List[ModelCallSource]:
        return [entry["source"] for entry in self._calls]

    @property
    def calls(self) -> List[Dict[str, str]]:
        return list(self._calls)


def resolve_llm_status(sources: List[ModelCallSource]) -> str:
    """실행 경로에서 llmStatus 를 도출한다(spec §6.2, GC-3, GC-5).

    설정("게이트웨이 URL 이 있다")이 아니라 **이번 실행에서 실제로 성사된 모델
    호출**만 본다. 시도했지만 전부 실패했으면 "fallback" 이다 — 게이트웨이가
    설정돼 있다는 사실은 아무것도 증명하지 않는다.

    호출이 하나도 기록되지 않은 경우(예: 전역 예산이 첫 단계에서 이미 소진)도
    "fallback" 으로 fail-closed 한다. 없는 것을 있는 것처럼 보이게 하지 않는다.
    """
    if not sources:
        return "fallback"
    if all(s == "stub" for s in sources):
        return "stub"
    if any(s == "llm" for s in sources):
        return "real"
    return "fallback"


def create_llm() -> Optional[ChatOpenAI]:
    """게이트웨이를 통해 LLM 에 붙는다.

    자격증명은 게이트웨이가 갖는다. 이 서비스는 base_url 만 안다(spec §3.1).

    timeout/max_retries 를 명시하지 않으면 langchain-openai 가 내부 openai SDK
    에 timeout=None(무한대) 을 넘긴다 — SDK 기본값 600s 를 오히려 무력화한다.
    이 서비스는 RabbitMQ 컨슈머가 prefetch_count=1 로 도는 구조라
    (rabbit_worker.py), 이 호출이 걸리면 뒤에 오는 모든 환자 작업이 대기한다.
    max_retries=0 도 timeout 만큼 중요하다 — 재시도는 게이트웨이가 소유한다
    (spec §6.1). SDK가 자체적으로 재시도하면 게이트웨이의 backoff 안에 SDK의
    backoff 가 중첩돼 상류 429 상황에서 호출 수가 곱으로 불어난다.
    """
    base_url = os.environ.get("LLM_GATEWAY_BASE_URL")
    if not base_url:
        return None
    # temperature 를 넘기지 않는다 — luna 계약이며 게이트웨이가 어차피 제거한다(spec §5).
    return ChatOpenAI(
        model=os.environ.get("LLM_MODEL", "openai.gpt-5.6-luna"),
        base_url=base_url,
        api_key="unused-gateway-handles-auth",
        default_headers={"X-LLM-Caller": "validation-agent"},
        timeout=float(os.environ.get("VALIDATION_LLM_TIMEOUT_SECONDS", "180")),
        max_retries=0,
    )


def parse_json_object(raw: str) -> Optional[Dict[str, Any]]:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start:end + 1]
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None
