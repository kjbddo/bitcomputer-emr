from app.config import Settings, load_settings


def _settings(api_key: str = "super-secret-key") -> Settings:
    return Settings(
        upstream_base_url="https://upstream.test/v1",
        api_key=api_key,
        model="openai.gpt-5.6-luna",
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
    assert "openai.gpt-5.6-luna" in text
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
