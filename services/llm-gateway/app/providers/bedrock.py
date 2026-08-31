"""Amazon Bedrock 제공자 (OpenAI 호환 경로).

**인증 입장.** 이 경로에서 SigV4 요청 서명은 선택지가 아니다. AWS 문서가
명시한다 — OpenAI Chat Completions API 를 쓰면 Bedrock API 키로만 인증할 수
있다(2026-08-31 확인). 엔드포인트 자체는 SigV4 를 지원하지만 그것은 AWS SDK 로
부르는 네이티브 오퍼레이션(InvokeModel/Converse) 이야기이고, `/openai/v1`
경로는 SDK 를 거치지 않는다.

그래서 "키가 만료된다" 는 걱정은 SigV4 로 해소되지 않는다. 실제 선택지는
어떤 종류의 Bedrock API 키를 쓰느냐다:

- 장기 키: 만료일을 1일~무기한으로 설정. AWS 는 탐색용으로만 권장한다.
- 단기 키: 최대 12시간. 그 자체가 SigV4 로 서명된 자격증명이고 AWS 가
  프로덕션용으로 권장한다. 즉 만료 문제의 해답은 "서명" 이 아니라
  "짧은 수명 + 갱신" 이다.

이 구현은 헤더를 만드는 자리를 `_credential()` 하나로 좁혀 둔다. 단기 키
갱신기(boto3 로 12시간마다 새 키를 발급)를 나중에 붙일 때 바꿀 곳이 그 한
군데이며, 지금 boto3/botocore 의존을 들이지 않는다. 어느 쪽이 실제로 쓰였는지는
계측의 authMode 로 관측된다.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from app.config import Settings
from app.params import normalize_bedrock_params
from app.providers.base import (
    Provider,
    ProviderConfigError,
    RawUsage,
    UpstreamRequest,
)

AUTH_MODE = "bearer:bedrock_api_key"

# 엔드포인트별 OpenAI 호환 기본 URL 틀.
# - bedrock-runtime: 교차 리전 추론(us./global./in. 프로파일)을 쓸 수 있고
#   AWS 가 신규 애플리케이션에 권장하는 표면이다.
# - bedrock-mantle: 서버사이드 툴 호출·비동기 추론이 필요할 때. luna 는 이
#   엔드포인트에서 `/openai/v1` 로 서빙된다(모델 카드 각주).
ENDPOINT_TEMPLATES = {
    "bedrock-runtime": "https://bedrock-runtime.{region}.amazonaws.com/openai/v1",
    "bedrock-mantle": "https://bedrock-mantle.{region}.api.aws/openai/v1",
}


def _resolve_base_url(settings: Settings) -> str:
    bedrock = settings.bedrock
    if bedrock.base_url:
        return bedrock.base_url.rstrip("/")

    template = ENDPOINT_TEMPLATES.get(bedrock.endpoint)
    if template is None:
        raise ProviderConfigError(
            f"LLM_BEDROCK_ENDPOINT={bedrock.endpoint!r} 는 알 수 없다. "
            f"가능한 값: {', '.join(sorted(ENDPOINT_TEMPLATES))}"
        )
    if not bedrock.region:
        raise ProviderConfigError(
            "LLM_BEDROCK_REGION 이 비어 있다. LLM_BEDROCK_BASE_URL 로 "
            "직접 지정하거나 리전을 설정한다."
        )
    return template.format(region=bedrock.region)


class BedrockProvider(Provider):
    name = "bedrock"

    def __init__(self, settings: Settings, *, configured_name: str) -> None:
        super().__init__(configured_name=configured_name)
        # OpenAI 쪽 upstream_base_url 은 여기서 절대 읽지 않는다. 읽으면
        # "bedrock 으로 설정했는데 OpenAI 로 나가는" 경로가 생긴다.
        self._base_url = _resolve_base_url(settings)
        self._api_key = settings.bedrock.api_key
        self._model_id = settings.bedrock.model

    def normalize_params(self, payload: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
        return normalize_bedrock_params(payload, model_id=self._model_id)

    def _credential(self) -> Tuple[str, str]:
        """(헤더 값, 인증 방식). 단기 키 갱신을 붙일 때 바꿀 유일한 자리."""
        return f"Bearer {self._api_key}", AUTH_MODE

    def build_request(self, payload: Dict[str, Any]) -> UpstreamRequest:
        authorization, auth_mode = self._credential()
        headers = {
            "Authorization": authorization,
            "Content-Type": "application/json",
        }
        return UpstreamRequest(
            provider=self.name,
            provider_configured=self.configured_name,
            url=f"{self._base_url}/chat/completions",
            headers=headers,
            body=payload,
            auth_mode=auth_mode,
        )

    def read_usage(self, body: Dict[str, Any]) -> RawUsage:
        # Bedrock 의 OpenAI 호환 응답은 OpenAI chat completion 객체를 따르므로
        # 필드 이름이 같다. 그래도 제공자별 구현으로 두는 이유는, 네이티브
        # 표면(Converse 의 usage.inputTokens/outputTokens)을 붙일 때 고칠 자리가
        # 계측이 아니라 여기여야 하기 때문이다.
        usage = body.get("usage") or {}
        return RawUsage(
            input_raw=usage.get("prompt_tokens"),
            output_raw=usage.get("completion_tokens"),
        )
