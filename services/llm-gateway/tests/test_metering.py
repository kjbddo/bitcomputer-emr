from app.config import Settings
from app.metering import build_record

SETTINGS = Settings(
    upstream_base_url="https://upstream.test/v1",
    api_key="secret",
    model="openai.gpt-5.6-luna",
    reasoning_effort="low",
    timeout_seconds=120.0,
    max_retries=2,
    input_price_per_1m=0.20,
    output_price_per_1m=1.20,
)


def test_record_contains_required_fields():
    record = build_record(
        model="openai.gpt-5.6-luna",
        caller="validation-agent",
        usage={"prompt_tokens": 1000, "completion_tokens": 500},
        latency_ms=1234,
        attempts=1,
        outcome="success",
        param_notes=["dropped:temperature"],
        settings=SETTINGS,
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
        usage={"prompt_tokens": 1_000_000, "completion_tokens": 1_000_000},
        latency_ms=1,
        attempts=1,
        outcome="success",
        param_notes=[],
        settings=SETTINGS,
    )
    # 입력 1M × $0.20 + 출력 1M × $1.20
    assert record["estimatedCostUsd"] == 1.40


def test_missing_usage_yields_zero_tokens_not_crash():
    record = build_record(
        model="m", caller="c", usage=None, latency_ms=1, attempts=1,
        outcome="failed", param_notes=[], settings=SETTINGS,
    )
    assert record["inputTokens"] == 0
    assert record["outputTokens"] == 0
    assert record["estimatedCostUsd"] == 0.0


def test_api_key_never_appears_in_record():
    record = build_record(
        model="m", caller="c", usage={"prompt_tokens": 1, "completion_tokens": 1},
        latency_ms=1, attempts=1, outcome="success", param_notes=[], settings=SETTINGS,
    )
    assert "secret" not in str(record)
