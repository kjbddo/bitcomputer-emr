import app.metering as metering_module
from app.config import Settings
from app.metering import build_record
from app.providers.base import ExecutionFacts, RawUsage
from factories import make_settings

SETTINGS = make_settings(api_key="secret")

EXECUTION = ExecutionFacts(
    provider="openai",
    provider_configured="openai",
    upstream_host="api.openai.com",
    auth_mode="bearer:openai_api_key",
)


def test_record_contains_required_fields():
    record = build_record(
        model="gpt-5.6-luna",
        caller="validation-agent",
        usage=RawUsage(1000, 500),
        latency_ms=1234,
        attempts=1,
        outcome="success",
        param_notes=["dropped:temperature"],
        settings=SETTINGS, execution=EXECUTION,
    )
    for key in (
        "model", "caller", "inputTokens", "outputTokens",
        "latencyMs", "attempts", "outcome", "paramNotes", "estimatedCostUsd",
    ):
        assert key in record, key


def test_cost_is_computed_from_tokens_and_price():
    record = build_record(
        model="m",
        caller="c",
        usage=RawUsage(1_000_000, 1_000_000),
        latency_ms=1,
        attempts=1,
        outcome="success",
        param_notes=[],
        settings=SETTINGS, execution=EXECUTION,
    )
    # 입력 1M × $0.20 + 출력 1M × $1.20
    assert record["estimatedCostUsd"] == 1.40


def test_missing_usage_yields_zero_tokens_not_crash():
    record = build_record(
        model="m", caller="c", usage=RawUsage(), latency_ms=1, attempts=1,
        outcome="failed", param_notes=[], settings=SETTINGS, execution=EXECUTION,
    )
    assert record["inputTokens"] == 0
    assert record["outputTokens"] == 0
    assert record["estimatedCostUsd"] == 0.0


def test_api_key_never_appears_in_record():
    record = build_record(
        model="m", caller="c", usage=RawUsage(1, 1),
        latency_ms=1, attempts=1, outcome="success", param_notes=[], settings=SETTINGS, execution=EXECUTION,
    )
    assert "secret" not in str(record)


# GC-7 구조 고정.
#
# 기존 "secret" 부재 단언은 이 회귀를 못 잡는다 — Settings.api_key 가 repr=False 라
# record["settings"] = settings 를 해도 str(record) 에 키가 안 나온다. 즉 그 테스트는
# 상류의 repr=False 를 검증할 뿐이다. 레코드가 애초에 객체를 안 들고 있다는 구조를 고정한다.
def test_record_holds_only_json_primitives():
    record = build_record(
        model="m", caller="c", usage=RawUsage(1, 1),
        latency_ms=1, attempts=1, outcome="success", param_notes=["dropped:temperature"],
        settings=SETTINGS, execution=EXECUTION,
    )
    for key, value in record.items():
        # None 허용: upstreamStatus 는 성공 시 null 이다. JSON 으로는 여전히
        # 원시값이며, 객체가 실려 들어오는 것을 막는다는 이 테스트의 목적은
        # 그대로다.
        assert isinstance(value, (str, int, float, list, type(None))), f"{key} 가 원시값이 아니다"
        if isinstance(value, list):
            assert all(isinstance(item, str) for item in value), f"{key} 에 비문자열 항목"


def test_record_does_not_carry_settings_object():
    record = build_record(
        model="m", caller="c", usage=RawUsage(), latency_ms=1, attempts=1,
        outcome="failed", param_notes=[], settings=SETTINGS, execution=EXECUTION,
    )
    assert "settings" not in record
    assert not any(isinstance(v, Settings) for v in record.values())


def test_small_request_cost_survives_rounding():
    """6자리 반올림이 실제로 일한다. round(cost, 2) 였다면 0.0 으로 뭉개진다."""
    record = build_record(
        model="m", caller="c", usage=RawUsage(1200, 300),
        latency_ms=1, attempts=1, outcome="success", param_notes=[], settings=SETTINGS, execution=EXECUTION,
    )
    assert record["estimatedCostUsd"] > 0.0


def test_malformed_token_value_does_not_crash():
    """상류가 이상한 usage 를 줘도 계측이 응답을 깨뜨리면 안 된다."""
    record = build_record(
        model="m", caller="c", usage=RawUsage("unknown", None),
        latency_ms=1, attempts=1, outcome="success", param_notes=[], settings=SETTINGS, execution=EXECUTION,
    )
    assert record["inputTokens"] == 0
    assert record["outputTokens"] == 0


def test_negative_token_count_clamped():
    record = build_record(
        model="m", caller="c", usage=RawUsage(-5, -5),
        latency_ms=1, attempts=1, outcome="success", param_notes=[], settings=SETTINGS, execution=EXECUTION,
    )
    assert record["inputTokens"] == 0
    assert record["estimatedCostUsd"] >= 0.0


# ── 어느 제공자가 실제로 처리했는가 ────────────────────────────────
#
# 이 저장소가 llmStatus·engineStatus·embeddingVersion 에서 세 번 틀린 규칙이다.
# 결과를 어떻게 만들었는지는 **설정이 아니라 실행 경로**에서 나와야 한다.

def test_record_reports_the_provider_that_ran():
    record = build_record(
        model="m", caller="c", usage=RawUsage(1, 1), latency_ms=1, attempts=1,
        outcome="success", param_notes=[], settings=SETTINGS,
        execution=ExecutionFacts(
            provider="bedrock",
            provider_configured="bedrock",
            upstream_host="bedrock-runtime.us-west-2.amazonaws.com",
            auth_mode="bearer:bedrock_api_key",
        ),
    )
    assert record["provider"] == "bedrock"
    assert record["upstreamHost"] == "bedrock-runtime.us-west-2.amazonaws.com"
    assert record["authMode"] == "bearer:bedrock_api_key"


# 설정은 bedrock 인데 실제로 돈 것은 openai 인 상황. 레코드는 실행 쪽을 말해야
# 한다. settings.provider 를 그대로 찍는 구현이면 여기서 잡힌다.
def test_record_does_not_echo_configured_provider():
    settings = make_settings(provider="bedrock")
    record = build_record(
        model="m", caller="c", usage=RawUsage(), latency_ms=1, attempts=1,
        outcome="success", param_notes=[], settings=settings,
        execution=ExecutionFacts(
            provider="openai",
            provider_configured="bedrock",
            upstream_host="api.openai.com",
            auth_mode="bearer:openai_api_key",
        ),
    )
    assert record["provider"] == "openai"
    assert record["providerConfigured"] == "bedrock"


def test_record_reports_unresolved_provider_as_unresolved():
    settings = make_settings(provider="bedrock")
    record = build_record(
        model="m", caller="c", usage=RawUsage(), latency_ms=1, attempts=0,
        outcome="failed", param_notes=[], settings=settings,
        execution=ExecutionFacts(
            provider="unresolved",
            provider_configured="bedrock",
            upstream_host="",
            auth_mode="none",
        ),
    )
    assert record["provider"] == "unresolved"
    assert record["provider"] != settings.provider


# 상류 상태코드는 실패의 성격을 가른다. Bedrock API 키 만료는 401/403 으로
# 나타나며, 그 구분이 레코드에 없으면 만료를 일반 장애와 구별할 수 없다.
def test_failed_record_carries_upstream_status():
    record = build_record(
        model="m", caller="c", usage=RawUsage(), latency_ms=1, attempts=1,
        outcome="failed", param_notes=[], settings=SETTINGS,
        execution=EXECUTION, upstream_status=403,
    )
    assert record["upstreamStatus"] == 403


def test_successful_record_has_null_upstream_status():
    record = build_record(
        model="m", caller="c", usage=RawUsage(1, 1), latency_ms=1, attempts=1,
        outcome="success", param_notes=[], settings=SETTINGS, execution=EXECUTION,
    )
    assert record["upstreamStatus"] is None


# 상류에 닿지도 못한 실패는 upstreamStatus 가 None 이다. 그때 failureDetail 이
# 없으면 레코드가 "실패했다"고만 말하고 왜인지는 말하지 않는다 — 라이브에서
# prescription-api 호출이 절반씩 실패하는데 원인이 타임아웃인지 네트워크 단절인지
# 로그만 보고는 가릴 수 없었다.
def test_failed_record_carries_the_reason_when_there_is_no_upstream_status():
    record = build_record(
        model="m", caller="c", usage=RawUsage(), latency_ms=1, attempts=3,
        outcome="failed", param_notes=[], settings=SETTINGS,
        execution=EXECUTION, upstream_status=None,
        failure_detail="connection error: ReadTimeout",
    )
    assert record["upstreamStatus"] is None
    assert record["failureDetail"] == "connection error: ReadTimeout"


def test_successful_record_has_no_failure_detail():
    """성공 레코드에 실패 사유 자리가 채워져 있으면 검색이 오염된다."""
    record = build_record(
        model="m", caller="c", usage=RawUsage(1, 1), latency_ms=1, attempts=1,
        outcome="success", param_notes=[], settings=SETTINGS, execution=EXECUTION,
    )
    assert record["failureDetail"] is None


def test_failure_detail_is_always_present_as_a_key():
    """키 자체는 항상 있어야 로그를 필드로 훑을 수 있다."""
    record = build_record(
        model="m", caller="c", usage=RawUsage(), latency_ms=1, attempts=1,
        outcome="failed", param_notes=[], settings=SETTINGS,
        execution=EXECUTION, upstream_status=500,
    )
    assert "failureDetail" in record


# 계측은 usage 필드 이름을 몰라야 한다. 그 지식은 제공자에 있다.
def test_metering_module_does_not_name_usage_fields():
    import pathlib

    source = pathlib.Path(metering_module.__file__).read_text(encoding="utf-8")
    assert "prompt_tokens" not in source
    assert "completion_tokens" not in source
