from app.config import Settings, load_settings


def _settings(api_key: str = "super-secret-key") -> Settings:
    return Settings(
        upstream_base_url="https://upstream.test/v1",
        api_key=api_key,
        model="gpt-5.6-luna",
        reasoning_effort="low",
        timeout_seconds=120.0,
        max_retries=2,
        input_price_per_1m=0.20,
        output_price_per_1m=1.20,
    )


# 이 객체는 요청·재시도·에러 처리 경로로 넘겨 다닌다. 로깅 한 줄이나
# 트레이스백 하나로 키가 새면 안 된다(GC-7).
def test_api_key_absent_from_repr():
    assert "super-secret-key" not in repr(_settings())


def test_api_key_absent_from_str():
    assert "super-secret-key" not in str(_settings())


def test_other_fields_still_visible_in_repr():
    """키만 가린다. 나머지는 디버깅에 필요하므로 보여야 한다."""
    text = repr(_settings())
    assert "gpt-5.6-luna" in text
    assert "upstream.test" in text


def test_settings_is_frozen():
    settings = _settings()
    try:
        settings.api_key = "changed"  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("frozen dataclass 여야 한다")


def test_load_settings_reads_environment(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "custom-model")
    monkeypatch.setenv("LLM_MAX_RETRIES", "5")
    settings = load_settings()
    assert settings.model == "custom-model"
    assert settings.max_retries == 5


# 이 기본값은 전체 타임아웃 사다리의 기준점이다. 45초 x 3회 시도 + 백오프
# 1.5초 = 136.5초 로, 가장 빡빡한 호출자(180초)보다 짧아야 재시도 2·3회차를
# 호출자가 관측할 수 있다. 여기를 올리면 사다리가 뒤집힌다.
def test_default_timeout_keeps_retry_ladder_under_caller_budget(monkeypatch):
    monkeypatch.delenv("LLM_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("LLM_MAX_RETRIES", raising=False)
    settings = load_settings()

    assert settings.timeout_seconds == 45.0
    total = settings.timeout_seconds * (1 + settings.max_retries) + 0.5 + 1.0
    assert total < 180.0, f"게이트웨이 총 예산 {total}s 가 호출자 180s 를 넘는다"


# 상류 제공자는 조용히 바뀌면 안 된다. 기본값만 바꿔도 전체 시스템이
# 다른 회사의 API 를 치게 되는데, 지금까지는 그걸 잡는 테스트가 없었다.
# (2026-08-28 Bedrock -> OpenAI 직접 호출로 전환하면서 발견)
def test_default_upstream_is_openai(monkeypatch):
    monkeypatch.delenv("LLM_UPSTREAM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    settings = load_settings()

    assert settings.upstream_base_url == "https://api.openai.com/v1"
    assert settings.model == "gpt-5.6-luna"


# 단가는 변동하므로 하드코딩하지 않는다는 것이 설계였다(spec §7).
# 기본값이 실제 공개 단가와 어긋나면 비용 보고가 조용히 틀린다.
def test_default_prices_match_published_rates(monkeypatch):
    monkeypatch.delenv("LLM_INPUT_PRICE_PER_1M", raising=False)
    monkeypatch.delenv("LLM_OUTPUT_PRICE_PER_1M", raising=False)
    settings = load_settings()

    assert settings.input_price_per_1m == 0.20
    assert settings.output_price_per_1m == 1.20
