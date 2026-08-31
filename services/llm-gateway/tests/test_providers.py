"""제공자 이음매(seam).

여기서 고정하는 성질은 두 가지다.
1. 한 제공자의 규칙이 다른 제공자에 조용히 적용되지 않는다.
2. "어느 제공자가 처리했는가"는 설정이 아니라 실제로 만들어진 요청에서 나온다.
"""
import pytest

from app.providers import build_provider, resolve_provider
from app.providers.base import (
    ExecutionFacts,
    Provider,
    ProviderConfigError,
    ProviderUnavailable,
    facts_for,
)
from factories import make_bedrock_settings, make_settings


# ── 등록과 해석 ────────────────────────────────────────────────────

def test_openai_provider_is_selected_by_default():
    assert build_provider(make_settings()).name == "openai"


def test_bedrock_provider_is_selected_by_configuration():
    settings = make_settings(provider="bedrock")
    assert build_provider(settings).name == "bedrock"


def test_unknown_provider_is_a_configuration_error():
    with pytest.raises(ProviderConfigError):
        build_provider(make_settings(provider="anthropic"))


# 모르는 이름을 openai 로 조용히 떨어뜨리면, 로그에는 anthropic 이 찍히고
# 실제 호출은 OpenAI 로 나가는 바로 그 결함이 된다.
def test_unknown_provider_does_not_silently_become_openai():
    provider = resolve_provider(make_settings(provider="anthropic"))
    assert provider.name != "openai"
    assert provider.name == "unresolved"
    assert provider.configured_name == "anthropic"


def test_resolve_never_raises_but_marks_unresolved():
    settings = make_settings(
        provider="bedrock", bedrock=make_bedrock_settings(region="", base_url="")
    )
    provider = resolve_provider(settings)
    assert provider.name == "unresolved"
    assert provider.configured_name == "bedrock"
    with pytest.raises(ProviderUnavailable):
        provider.build_request({"model": "m", "messages": []})


def test_unresolved_reason_does_not_leak_secrets():
    settings = make_settings(
        provider="bedrock",
        api_key="openai-super-secret",
        bedrock=make_bedrock_settings(api_key="bedrock-super-secret", region=""),
    )
    provider = resolve_provider(settings)
    assert "bedrock-super-secret" not in provider.reason
    assert "openai-super-secret" not in provider.reason
    assert provider.reason  # 이유 자체는 있어야 한다


# ── 엔드포인트 모양 ────────────────────────────────────────────────

def test_openai_url_is_base_plus_chat_completions():
    provider = build_provider(make_settings(upstream_base_url="https://api.openai.com/v1"))
    request = provider.build_request({"model": "m", "messages": []})
    assert request.url == "https://api.openai.com/v1/chat/completions"


# bedrock-runtime 의 OpenAI 호환 표면은 /openai/v1 경로다 (AWS 문서 2026-08-31).
def test_bedrock_runtime_url_is_derived_from_region():
    settings = make_settings(
        provider="bedrock",
        bedrock=make_bedrock_settings(region="us-west-2", endpoint="bedrock-runtime"),
    )
    request = build_provider(settings).build_request({"model": "m", "messages": []})
    assert request.url == (
        "https://bedrock-runtime.us-west-2.amazonaws.com/openai/v1/chat/completions"
    )


def test_bedrock_mantle_url_uses_api_aws_host():
    settings = make_settings(
        provider="bedrock",
        bedrock=make_bedrock_settings(region="us-east-1", endpoint="bedrock-mantle"),
    )
    request = build_provider(settings).build_request({"model": "m", "messages": []})
    assert request.url == (
        "https://bedrock-mantle.us-east-1.api.aws/openai/v1/chat/completions"
    )


def test_bedrock_base_url_override_wins():
    settings = make_settings(
        provider="bedrock",
        bedrock=make_bedrock_settings(base_url="https://proxy.internal/openai/v1"),
    )
    request = build_provider(settings).build_request({"model": "m", "messages": []})
    assert request.url == "https://proxy.internal/openai/v1/chat/completions"


def test_bedrock_without_region_or_base_url_is_a_configuration_error():
    settings = make_settings(
        provider="bedrock", bedrock=make_bedrock_settings(region="", base_url="")
    )
    with pytest.raises(ProviderConfigError):
        build_provider(settings)


def test_bedrock_unknown_endpoint_is_a_configuration_error():
    settings = make_settings(
        provider="bedrock", bedrock=make_bedrock_settings(endpoint="bedrock-something")
    )
    with pytest.raises(ProviderConfigError):
        build_provider(settings)


# bedrock 은 OpenAI 의 상류 URL 을 절대 쓰지 않는다. 이 두 값이 섞이면
# "bedrock 으로 설정했는데 OpenAI 로 나간" 상태가 된다.
def test_bedrock_ignores_openai_base_url():
    settings = make_settings(
        provider="bedrock",
        upstream_base_url="https://api.openai.com/v1",
        bedrock=make_bedrock_settings(region="us-west-2"),
    )
    request = build_provider(settings).build_request({"model": "m", "messages": []})
    assert "api.openai.com" not in request.url


# ── 인증 ───────────────────────────────────────────────────────────

def test_openai_auth_uses_openai_key():
    provider = build_provider(make_settings(api_key="openai-key"))
    request = provider.build_request({"model": "m", "messages": []})
    assert request.headers["Authorization"] == "Bearer openai-key"
    assert request.auth_mode == "bearer:openai_api_key"


# Bedrock 의 OpenAI 호환 경로는 Bedrock API 키(베어러)만 받는다. SigV4 요청
# 서명은 이 경로에 쓸 수 없다(AWS 문서 2026-08-31). 그래서 헤더 모양은 같지만
# 자격증명 출처가 다르며, 그 출처를 틀리면 여기서 잡혀야 한다.
def test_bedrock_auth_uses_bedrock_key_not_openai_key():
    settings = make_settings(
        provider="bedrock",
        api_key="openai-key",
        bedrock=make_bedrock_settings(api_key="bedrock-key", region="us-west-2"),
    )
    request = build_provider(settings).build_request({"model": "m", "messages": []})
    assert request.headers["Authorization"] == "Bearer bedrock-key"
    assert "openai-key" not in str(request.headers)
    assert request.auth_mode == "bearer:bedrock_api_key"


def test_auth_mode_is_reported_per_provider():
    openai_mode = build_provider(make_settings()).build_request(
        {"model": "m", "messages": []}
    ).auth_mode
    bedrock_mode = build_provider(
        make_settings(provider="bedrock", bedrock=make_bedrock_settings(region="us-west-2"))
    ).build_request({"model": "m", "messages": []}).auth_mode
    assert openai_mode != bedrock_mode


# ── 파라미터 규칙 ──────────────────────────────────────────────────

def test_openai_rules_drop_temperature_and_inject_reasoning_effort():
    provider = build_provider(make_settings())
    result, notes = provider.normalize_params({"model": "m", "messages": [], "temperature": 0.7})
    assert "temperature" not in result
    assert result["reasoning_effort"] == "low"
    assert "dropped:temperature" in notes


# Bedrock 의 OpenAI 호환 경로에서 luna 가 temperature 를 거부하는지는
# **확인되지 않았다.** AWS 문서의 OpenAI 모델 예제는 오히려 temperature·top_p 를
# 보낸다. 확인되지 않은 것을 근거로 값을 버리면 조용한 손실이 된다 —
# OpenAI 쪽 규칙을 여기에 복사해 오면 이 테스트가 잡는다.
def test_bedrock_rules_do_not_drop_temperature():
    settings = make_settings(
        provider="bedrock", bedrock=make_bedrock_settings(region="us-west-2")
    )
    result, notes = build_provider(settings).normalize_params(
        {"model": "m", "messages": [], "temperature": 0.7, "top_p": 0.9}
    )
    assert result["temperature"] == 0.7
    assert result["top_p"] == 0.9
    assert not any(n.startswith("dropped:temperature") for n in notes)


def test_bedrock_rules_do_not_inject_reasoning_effort():
    settings = make_settings(
        provider="bedrock", bedrock=make_bedrock_settings(region="us-west-2")
    )
    result, notes = build_provider(settings).normalize_params({"model": "m", "messages": []})
    assert "reasoning_effort" not in result
    assert not any(n.startswith("injected:reasoning_effort") for n in notes)


# 반대 방향. Bedrock 규칙(모델 ID 치환)이 OpenAI 쪽에 새면 여기서 잡힌다.
def test_openai_rules_do_not_rewrite_the_model():
    provider = build_provider(make_settings())
    result, notes = provider.normalize_params({"model": "gpt-5.6-luna", "messages": []})
    assert result["model"] == "gpt-5.6-luna"
    assert not any(n.startswith("mapped:model") for n in notes)


# 호출 서비스는 OpenAI 모델 ID 를 보낸다. Bedrock 에서 그 ID 는 유효하지 않다
# (bedrock-runtime 에서 luna 는 교차 리전 프로파일 ID 전용). 호출자를 고치지
# 않고 제공자를 바꾸려면 이 치환이 이음매 안에 있어야 한다.
def test_bedrock_maps_the_model_id_and_records_it():
    settings = make_settings(
        provider="bedrock",
        bedrock=make_bedrock_settings(region="us-west-2", model="global.openai.gpt-5.6-luna"),
    )
    result, notes = build_provider(settings).normalize_params(
        {"model": "gpt-5.6-luna", "messages": []}
    )
    assert result["model"] == "global.openai.gpt-5.6-luna"
    assert "mapped:model=gpt-5.6-luna->global.openai.gpt-5.6-luna" in notes


def test_both_providers_rename_max_tokens():
    """max_completion_tokens 는 양쪽 문서가 모두 쓰는 이름이다."""
    for settings in (
        make_settings(),
        make_settings(provider="bedrock", bedrock=make_bedrock_settings(region="us-west-2")),
    ):
        result, notes = build_provider(settings).normalize_params(
            {"model": "m", "messages": [], "max_tokens": 512}
        )
        assert result["max_completion_tokens"] == 512
        assert "max_tokens" not in result


# ── usage 필드 이름 ────────────────────────────────────────────────

def test_openai_reads_prompt_and_completion_tokens():
    provider = build_provider(make_settings())
    usage = provider.read_usage({"usage": {"prompt_tokens": 10, "completion_tokens": 5}})
    assert (usage.input_raw, usage.output_raw) == (10, 5)


def test_bedrock_reads_prompt_and_completion_tokens():
    """Bedrock 의 OpenAI 호환 응답은 OpenAI chat completion 객체를 따른다."""
    settings = make_settings(
        provider="bedrock", bedrock=make_bedrock_settings(region="us-west-2")
    )
    usage = build_provider(settings).read_usage(
        {"usage": {"prompt_tokens": 10, "completion_tokens": 5}}
    )
    assert (usage.input_raw, usage.output_raw) == (10, 5)


def test_missing_usage_is_not_an_error():
    provider = build_provider(make_settings())
    usage = provider.read_usage({"choices": []})
    assert (usage.input_raw, usage.output_raw) == (None, None)


# ── 네이티브 번역 자리 ─────────────────────────────────────────────

# 지금은 양쪽 다 OpenAI 모양이라 parse_response 가 항등이다. 이 자리가 있어야
# 나중에 Converse 같은 네이티브 표면을 같은 이음매로 붙일 수 있다.
def test_parse_response_is_part_of_the_seam():
    for name in ("normalize_params", "build_request", "parse_response", "read_usage"):
        assert callable(getattr(Provider, name, None)), name


def test_parse_response_passes_openai_shape_through():
    body = {"choices": [{"message": {"content": "hi"}}]}
    assert build_provider(make_settings()).parse_response(body) == body


# ── 실행 사실 ──────────────────────────────────────────────────────

def test_facts_come_from_the_request_that_was_built():
    settings = make_settings(
        provider="bedrock", bedrock=make_bedrock_settings(region="us-west-2")
    )
    provider = build_provider(settings)
    request = provider.build_request({"model": "m", "messages": []})
    facts = facts_for(provider, request)

    assert isinstance(facts, ExecutionFacts)
    assert facts.provider == "bedrock"
    assert facts.upstream_host == "bedrock-runtime.us-west-2.amazonaws.com"
    assert facts.auth_mode == "bearer:bedrock_api_key"


def test_facts_for_unresolved_provider_report_unresolved():
    provider = resolve_provider(make_settings(provider="nope"))
    facts = facts_for(provider, None)
    assert facts.provider == "unresolved"
    assert facts.provider_configured == "nope"
    assert facts.upstream_host == ""


def test_facts_never_carry_credentials():
    settings = make_settings(
        provider="bedrock",
        api_key="openai-super-secret",
        bedrock=make_bedrock_settings(api_key="bedrock-super-secret", region="us-west-2"),
    )
    provider = build_provider(settings)
    facts = facts_for(provider, provider.build_request({"model": "m", "messages": []}))
    text = repr(facts)
    assert "bedrock-super-secret" not in text
    assert "openai-super-secret" not in text
