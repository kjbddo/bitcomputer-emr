"""게이트웨이 설정.

시크릿(API 키)은 로그·에러 메시지에 절대 싣지 않는다(GC-7).

제공자 선택은 여기서 **읽기만** 한다. "어느 제공자가 실제로 호출을 처리했는가"는
설정이 아니라 실행 경로에서 나와야 한다(app/providers/base.py 의 ExecutionFacts).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

# 상류 제공자 이름. 실제 구현 등록은 app/providers/__init__.py 가 소유한다.
PROVIDER_OPENAI = "openai"
PROVIDER_BEDROCK = "bedrock"


@dataclass(frozen=True)
class BedrockSettings:
    """Bedrock 상류 설정.

    OpenAI 호환 경로(`/openai/v1/chat/completions`)에서 Bedrock 이 받는 인증은
    Bedrock API 키(베어러)뿐이다. SigV4 요청 서명은 이 경로에 쓸 수 없다
    (AWS 문서 2026-08-31 확인). 그래서 여기에도 정적 키 필드가 있고,
    OpenAI 키와 똑같이 repr 에서 가린다(GC-7).
    """

    # repr=False 이유는 Settings.api_key 와 같다. 중첩 dataclass 의 repr 은
    # 바깥 repr 에 그대로 펼쳐지므로 여기서 가리지 않으면 바깥도 샌다.
    api_key: str = field(repr=False)
    region: str
    # bedrock-runtime | bedrock-mantle
    endpoint: str
    model: str
    # 비어 있으면 region + endpoint 로 조립한다. 채우면 그것이 이긴다.
    base_url: str


@dataclass(frozen=True)
class Settings:
    upstream_base_url: str
    # repr=False 가 없으면 dataclass 기본 repr 이 키를 그대로 찍는다.
    # 이 객체는 요청·재시도·에러 처리 경로로 넘겨 다니도록 설계됐으므로,
    # 로깅 한 줄이나 트레이스백 하나로 키가 새는 경로가 실재한다(GC-7).
    api_key: str = field(repr=False)
    model: str
    reasoning_effort: str
    timeout_seconds: float
    max_retries: int
    input_price_per_1m: float
    output_price_per_1m: float
    # 설정된 제공자. 실제로 호출을 처리한 제공자와 다를 수 있으며,
    # 계측 레코드의 provider 는 이 값이 아니라 실행 경로에서 나온다.
    provider: str
    bedrock: BedrockSettings


def _load_bedrock() -> BedrockSettings:
    return BedrockSettings(
        api_key=os.environ.get("LLM_BEDROCK_API_KEY", ""),
        # 기본값을 주지 않는다. 계정마다 다르고, 틀린 리전으로 조용히 붙는 것보다
        # 제공자 구성 실패로 드러나는 편이 낫다.
        region=os.environ.get("LLM_BEDROCK_REGION", ""),
        endpoint=os.environ.get("LLM_BEDROCK_ENDPOINT", "bedrock-runtime"),
        # bedrock-runtime 에서 luna 는 In-Region 추론이 없다. 교차 리전 추론
        # 프로파일 ID(us. / global. / in.)를 모델로 지정해야 하며 베어
        # `openai.gpt-5.6-luna` 로는 호출되지 않는다(모델 카드 2026-08-31).
        # bedrock-mantle 로 바꿀 때는 반대로 베어 ID 를 써야 한다.
        model=os.environ.get("LLM_BEDROCK_MODEL", "global.openai.gpt-5.6-luna"),
        base_url=os.environ.get("LLM_BEDROCK_BASE_URL", "").rstrip("/"),
    )


def load_settings() -> Settings:
    return Settings(
        upstream_base_url=os.environ.get(
            "LLM_UPSTREAM_BASE_URL",
            "https://api.openai.com/v1",
        ).rstrip("/"),
        api_key=os.environ.get("LLM_API_KEY", ""),
        model=os.environ.get("LLM_MODEL", "gpt-5.6-luna"),
        reasoning_effort=os.environ.get("LLM_REASONING_EFFORT", "low"),
        # 최종 리뷰 IMPORTANT: 이 값은 1회 시도당 타임아웃이다. 3회 시도(최초
        # 1 + 재시도 2) + backoff(0.5s+1.0s) 의 최악 케이스가 호출자
        # (prescription/certificate 의 LLM_GATEWAY_TIMEOUT_SECONDS=180s, Java
        # read-timeout-ms=180000) 보다 짧아야 재시도 2·3회차가 실제로
        # 관측된다 — 45s 라면 3*45+1.5=136.5s < 180s. 이 값을 올릴 때는
        # infra/.env.example 의 LLM_GATEWAY_TIMEOUT_SECONDS 주석에 적힌
        # 순서를 함께 검토한다.
        timeout_seconds=float(os.environ.get("LLM_TIMEOUT_SECONDS", "45")),
        max_retries=int(os.environ.get("LLM_MAX_RETRIES", "2")),
        # 단가는 변동하므로 하드코딩하지 않는다. spec §7.
        input_price_per_1m=float(os.environ.get("LLM_INPUT_PRICE_PER_1M", "0.20")),
        output_price_per_1m=float(os.environ.get("LLM_OUTPUT_PRICE_PER_1M", "1.20")),
        # LLM_PROVIDER 가 아니다. 그 이름은 호출 서비스가 stub/real 을 고르는 데
        # 이미 쓰고 있고(spec §3.3) 같은 infra/.env 를 공유한다.
        provider=os.environ.get("LLM_UPSTREAM_PROVIDER", PROVIDER_OPENAI),
        bedrock=_load_bedrock(),
    )
