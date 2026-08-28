"""게이트웨이 설정.

시크릿(API 키)은 로그·에러 메시지에 절대 싣지 않는다(GC-7).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


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
    )
