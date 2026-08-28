"""게이트웨이 설정.

시크릿(API 키)은 로그·에러 메시지에 절대 싣지 않는다(GC-7).
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    upstream_base_url: str
    api_key: str
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
            "https://bedrock-mantle.us-west-2.api.aws/openai/v1",
        ).rstrip("/"),
        api_key=os.environ.get("LLM_API_KEY", ""),
        model=os.environ.get("LLM_MODEL", "openai.gpt-5.6-luna"),
        reasoning_effort=os.environ.get("LLM_REASONING_EFFORT", "low"),
        timeout_seconds=float(os.environ.get("LLM_TIMEOUT_SECONDS", "120")),
        max_retries=int(os.environ.get("LLM_MAX_RETRIES", "2")),
        # 단가는 변동하므로 하드코딩하지 않는다. spec §7.
        input_price_per_1m=float(os.environ.get("LLM_INPUT_PRICE_PER_1M", "0.20")),
        output_price_per_1m=float(os.environ.get("LLM_OUTPUT_PRICE_PER_1M", "1.20")),
    )
