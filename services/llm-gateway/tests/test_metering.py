from app.config import Settings
from app.metering import build_record

SETTINGS = Settings(
    upstream_base_url="https://upstream.test/v1",
    api_key="secret",
    model="gpt-5.6-luna",
    reasoning_effort="low",
    timeout_seconds=120.0,
    max_retries=2,
    input_price_per_1m=0.20,
    output_price_per_1m=1.20,
)


def test_record_contains_required_fields():
    record = build_record(
        model="gpt-5.6-luna",
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


# GC-7 구조 고정.
#
# 기존 "secret" 부재 단언은 이 회귀를 못 잡는다 — Settings.api_key 가 repr=False 라
# record["settings"] = settings 를 해도 str(record) 에 키가 안 나온다. 즉 그 테스트는
# 상류의 repr=False 를 검증할 뿐이다. 레코드가 애초에 객체를 안 들고 있다는 구조를 고정한다.
def test_record_holds_only_json_primitives():
    record = build_record(
        model="m", caller="c", usage={"prompt_tokens": 1, "completion_tokens": 1},
        latency_ms=1, attempts=1, outcome="success", param_notes=["dropped:temperature"],
        settings=SETTINGS,
    )
    for key, value in record.items():
        assert isinstance(value, (str, int, float, list)), f"{key} 가 원시값이 아니다"
        if isinstance(value, list):
            assert all(isinstance(item, str) for item in value), f"{key} 에 비문자열 항목"


def test_record_does_not_carry_settings_object():
    record = build_record(
        model="m", caller="c", usage=None, latency_ms=1, attempts=1,
        outcome="failed", param_notes=[], settings=SETTINGS,
    )
    assert "settings" not in record
    assert not any(isinstance(v, Settings) for v in record.values())


def test_small_request_cost_survives_rounding():
    """6자리 반올림이 실제로 일한다. round(cost, 2) 였다면 0.0 으로 뭉개진다."""
    record = build_record(
        model="m", caller="c", usage={"prompt_tokens": 1200, "completion_tokens": 300},
        latency_ms=1, attempts=1, outcome="success", param_notes=[], settings=SETTINGS,
    )
    assert record["estimatedCostUsd"] > 0.0


def test_malformed_token_value_does_not_crash():
    """상류가 이상한 usage 를 줘도 계측이 응답을 깨뜨리면 안 된다."""
    record = build_record(
        model="m", caller="c", usage={"prompt_tokens": "unknown", "completion_tokens": None},
        latency_ms=1, attempts=1, outcome="success", param_notes=[], settings=SETTINGS,
    )
    assert record["inputTokens"] == 0
    assert record["outputTokens"] == 0


def test_negative_token_count_clamped():
    record = build_record(
        model="m", caller="c", usage={"prompt_tokens": -5, "completion_tokens": -5},
        latency_ms=1, attempts=1, outcome="success", param_notes=[], settings=SETTINGS,
    )
    assert record["inputTokens"] == 0
    assert record["estimatedCostUsd"] >= 0.0
