"""제공자 이음매의 계약.

게이트웨이 바깥 표면은 OpenAI 모양으로 고정돼 있다(spec §4). 상류가 무엇이든
호출 서비스는 `POST /v1/chat/completions` 하나만 안다. 그 사이의 차이 —
엔드포인트 모양, 인증, 파라미터 규칙, usage 필드 이름 — 를 흡수하는 자리가
여기다.

**이음매를 넓게 잡은 이유.** 지금 두 구현은 모두 OpenAI 호환 HTTP 라
`parse_response` 가 항등이고 `build_request` 가 URL·헤더만 다르다. 그러나
나중에 Bedrock Converse 같은 네이티브 표면을 붙이려면 요청·응답을 실제로
번역해야 한다. 그때 새 표면이 들어올 자리가 `build_request`/`parse_response`
두 메서드이며, 다른 코드는 손대지 않는다. 번역 자체는 지금 만들지 않는다.

**GC-7.** `UpstreamRequest.headers` 는 자격증명을 들고 있다. 이 객체는 절대
로그·에러·계측에 들어가지 않는다. 계측이 보는 것은 `ExecutionFacts` 뿐이며,
그 안에는 호스트 이름과 인증 '방식' 만 있고 값은 없다.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Tuple
from urllib.parse import urlsplit


class ProviderConfigError(Exception):
    """설정만으로는 제공자를 만들 수 없다."""


class ProviderUnavailable(Exception):
    """제공자가 해석되지 않아 요청을 만들 수 없다."""


@dataclass(frozen=True)
class UpstreamRequest:
    """실제로 상류에 보낼 것.

    이 객체가 곧 '무엇이 실행됐는가' 의 근거다. 계측의 provider 는 설정이
    아니라 이 객체를 만든 제공자에서 나온다.
    """

    provider: str
    provider_configured: str
    url: str
    # 자격증명을 담는다. repr=False — 트레이스백 한 줄로 새는 경로를 막는다(GC-7).
    headers: Mapping[str, str] = field(repr=False)
    body: Dict[str, Any]
    auth_mode: str


@dataclass(frozen=True)
class RawUsage:
    """상류 응답에서 읽어낸 토큰 수의 원본 값.

    정수 변환·음수 클램프는 계측이 한 곳에서 한다(metering._coerce_token_count).
    여기서는 '어느 필드를 읽는가' 만 제공자별로 다르다.
    """

    input_raw: Any = None
    output_raw: Any = None


@dataclass(frozen=True)
class ExecutionFacts:
    """계측이 볼 수 있는 유일한 실행 사실.

    provider 는 '설정된 제공자' 가 아니라 '요청을 만든 제공자' 다. 이 프로젝트가
    llmStatus·engineStatus·embeddingVersion 에서 세 번 틀린 규칙 —
    결과를 어떻게 만들었는지는 설정이 아니라 실행 경로에서 나와야 한다 — 이
    적용되는 자리다.
    """

    provider: str
    provider_configured: str
    upstream_host: str
    auth_mode: str


def facts_for(provider: "Provider", request: Optional[UpstreamRequest]) -> ExecutionFacts:
    """실행 사실을 만든다. 유일한 도출 경로다.

    request 가 있으면 **그 요청에서만** 읽는다 — 설정을 참조하지 않는다.
    request 가 None 인 것은 상류로 나간 요청이 아예 없었다는 뜻이며(제공자
    미해석 등), 그때는 제공자 자신의 정체만 보고한다.
    """
    if request is None:
        return ExecutionFacts(
            provider=provider.name,
            provider_configured=provider.configured_name,
            upstream_host="",
            auth_mode="none",
        )
    return ExecutionFacts(
        provider=request.provider,
        provider_configured=request.provider_configured,
        upstream_host=urlsplit(request.url).netloc,
        auth_mode=request.auth_mode,
    )


class Provider(ABC):
    """상류 하나를 다루는 방법.

    name 은 실제로 호출을 수행하는 구현의 이름이고, configured_name 은 설정이
    요구한 이름이다. 정상 경로에서는 같고, 어긋나면 그 자체가 보고 대상이다.
    """

    name: str = "unknown"

    def __init__(self, *, configured_name: str) -> None:
        self.configured_name = configured_name

    @abstractmethod
    def normalize_params(self, payload: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
        """이 제공자의 파라미터 계약에 맞춘다. 입력은 변형하지 않는다."""

    @abstractmethod
    def build_request(self, payload: Dict[str, Any]) -> UpstreamRequest:
        """보낼 요청을 조립한다. URL·인증 헤더·본문이 여기서 정해진다."""

    @abstractmethod
    def read_usage(self, body: Dict[str, Any]) -> RawUsage:
        """응답에서 토큰 수를 꺼낸다. 필드 이름이 제공자마다 다를 수 있다."""

    def parse_response(self, body: Dict[str, Any]) -> Dict[str, Any]:
        """상류 응답을 OpenAI chat completion 모양으로 만든다.

        OpenAI 호환 상류에서는 항등이다. 네이티브 표면(Converse 등)을 붙일 때
        실제 번역이 들어오는 자리이며, 그때도 호출자가 보는 모양은 안 바뀐다.
        """
        return body


class UnresolvedProvider(Provider):
    """설정된 제공자를 만들 수 없었다.

    **다른 제공자로 대신 붙지 않는다.** bedrock 설정이 깨졌다고 OpenAI 로
    떨어지면 요금이 다른 회사로 나가고 로그는 그것을 모른다. 대신 모든 요청을
    실패시키되, 계측에는 `provider=unresolved` 와 설정된 이름이 함께 남는다.
    """

    name = "unresolved"

    def __init__(self, *, configured_name: str, reason: str) -> None:
        super().__init__(configured_name=configured_name)
        # 이 문자열은 에러 응답·로그로 나간다. 자격증명을 넣지 않는다(GC-7).
        self.reason = reason

    def normalize_params(self, payload: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
        return dict(payload), [f"provider_unresolved:{self.configured_name}"]

    def build_request(self, payload: Dict[str, Any]) -> UpstreamRequest:
        raise ProviderUnavailable(self.reason)

    def read_usage(self, body: Dict[str, Any]) -> RawUsage:
        return RawUsage()
