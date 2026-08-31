"""테스트용 Settings 조립기.

Settings 는 기본값 없는 frozen dataclass 다 — 기본값이 두 군데(load_settings 와
dataclass) 에 살면 조용히 갈라지기 때문이다. 그래서 테스트가 전 필드를 채워야
하고, 그 반복을 여기로 모은다.
"""
from app.config import BedrockSettings, Settings


def make_bedrock_settings(**overrides) -> BedrockSettings:
    values = dict(
        api_key="bedrock-secret",
        region="us-west-2",
        endpoint="bedrock-runtime",
        model="global.openai.gpt-5.6-luna",
        base_url="",
    )
    values.update(overrides)
    return BedrockSettings(**values)


def make_settings(**overrides) -> Settings:
    bedrock = overrides.pop("bedrock", None)
    values = dict(
        upstream_base_url="https://upstream.test/v1",
        api_key="super-secret-key",
        model="gpt-5.6-luna",
        reasoning_effort="low",
        timeout_seconds=120.0,
        max_retries=2,
        input_price_per_1m=0.20,
        output_price_per_1m=1.20,
        provider="openai",
        bedrock=bedrock if bedrock is not None else make_bedrock_settings(),
    )
    values.update(overrides)
    return Settings(**values)
