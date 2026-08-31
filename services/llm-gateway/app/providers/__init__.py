"""제공자 등록소.

`build_provider` 는 설정이 잘못되면 던진다. `resolve_provider` 는 던지지 않고
UnresolvedProvider 를 돌려준다 — 기동을 막지 않되, **다른 제공자로 대신 붙지도
않는다.** 모르는 이름을 openai 로 떨어뜨리면 로그에는 설정값이 찍히고 호출은
다른 곳으로 나가는, 이 저장소가 세 번 겪은 결함이 그대로 재현된다.
"""
from __future__ import annotations

from typing import Callable, Dict

from app.config import PROVIDER_BEDROCK, PROVIDER_OPENAI, Settings
from app.providers.base import (
    Provider,
    ProviderConfigError,
    UnresolvedProvider,
)
from app.providers.bedrock import BedrockProvider
from app.providers.openai import OpenAIProvider

# 새 제공자는 여기에 등록한다. 네이티브 표면(Converse 등)도 같은 자리에 들어온다.
REGISTRY: Dict[str, Callable[..., Provider]] = {
    PROVIDER_OPENAI: OpenAIProvider,
    PROVIDER_BEDROCK: BedrockProvider,
}


def build_provider(settings: Settings) -> Provider:
    """설정대로 제공자를 만든다. 못 만들면 ProviderConfigError."""
    factory = REGISTRY.get(settings.provider)
    if factory is None:
        raise ProviderConfigError(
            f"LLM_UPSTREAM_PROVIDER={settings.provider!r} 는 알 수 없다. "
            f"가능한 값: {', '.join(sorted(REGISTRY))}"
        )
    return factory(settings, configured_name=settings.provider)


def resolve_provider(settings: Settings) -> Provider:
    """기동용. 실패해도 던지지 않지만 그 사실을 감추지도 않는다."""
    try:
        return build_provider(settings)
    except ProviderConfigError as exc:
        # str(exc) 에는 설정 이름과 리전만 들어간다. 자격증명은 넣지 않는다(GC-7).
        return UnresolvedProvider(configured_name=settings.provider, reason=str(exc))


__all__ = [
    "REGISTRY",
    "build_provider",
    "resolve_provider",
    "Provider",
    "ProviderConfigError",
    "UnresolvedProvider",
]
