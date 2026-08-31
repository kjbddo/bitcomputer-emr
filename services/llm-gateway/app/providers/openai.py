"""OpenAI 직접 호출 제공자.

상류는 `https://api.openai.com/v1` 이고 인증은 정적 베어러 키다.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from app.config import Settings
from app.params import normalize_openai_params
from app.providers.base import Provider, RawUsage, UpstreamRequest

AUTH_MODE = "bearer:openai_api_key"


class OpenAIProvider(Provider):
    name = "openai"

    def __init__(self, settings: Settings, *, configured_name: str) -> None:
        super().__init__(configured_name=configured_name)
        self._base_url = settings.upstream_base_url.rstrip("/")
        self._api_key = settings.api_key
        self._default_reasoning_effort = settings.reasoning_effort

    def normalize_params(self, payload: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
        return normalize_openai_params(
            payload, default_reasoning_effort=self._default_reasoning_effort
        )

    def build_request(self, payload: Dict[str, Any]) -> UpstreamRequest:
        # 헤더와 auth_mode 를 한 함수에서 만든다. 따로 두면 헤더는 A 로 만들고
        # 보고는 B 로 하는 어긋남이 생길 수 있다.
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        return UpstreamRequest(
            provider=self.name,
            provider_configured=self.configured_name,
            url=f"{self._base_url}/chat/completions",
            headers=headers,
            body=payload,
            auth_mode=AUTH_MODE,
        )

    def read_usage(self, body: Dict[str, Any]) -> RawUsage:
        usage = body.get("usage") or {}
        return RawUsage(
            input_raw=usage.get("prompt_tokens"),
            output_raw=usage.get("completion_tokens"),
        )
