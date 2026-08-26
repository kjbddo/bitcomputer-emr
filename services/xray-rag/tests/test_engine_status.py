from app.config import Settings


def test_mock_when_both_toggles_off(monkeypatch):
    monkeypatch.setenv("USE_TORCH_ANOMALY", "false")
    monkeypatch.setenv("USE_TORCH_EMBEDDING", "false")
    assert Settings().engine_status() == "mock"


def test_mock_when_only_one_toggle_on(monkeypatch):
    monkeypatch.setenv("USE_TORCH_ANOMALY", "true")
    monkeypatch.setenv("USE_TORCH_EMBEDDING", "false")
    assert Settings().engine_status() == "mock"


def test_real_when_both_toggles_on(monkeypatch):
    monkeypatch.setenv("USE_TORCH_ANOMALY", "true")
    monkeypatch.setenv("USE_TORCH_EMBEDDING", "true")
    assert Settings().engine_status() == "real"
