"""engineStatus 판정 테스트.

USE_TORCH_ANOMALY / USE_TORCH_EMBEDDING 는 "시도" 토글일 뿐이다. 실제 판정은
app.ml.factory.build_models() 가 실제로 torch 어댑터를 구성했는지(결과)에
근거해야 한다 - 토글이 true 여도 로드가 실패하면(가중치 누락 등) mock 으로
fallback 하고 engineStatus 는 "mock" 이어야 한다.

torch_anomaly_model.build_torch_anomaly_model() / torch_embedding_model.
build_torch_embedding_model() 을 monkeypatch 해서 실제 가중치 없이도
성공/실패 두 경로를 모두 시뮬레이션한다.

주의: Settings.USE_TORCH_ANOMALY / USE_TORCH_EMBEDDING 은 클래스 속성으로
import 시점에 한 번 os.environ 을 읽어 고정된다(Settings() 인스턴스를 새로
만들어도 os.environ 을 다시 읽지 않는다). 따라서 monkeypatch.setenv 가 아니라
Settings 클래스 속성 자체를 monkeypatch.setattr 로 덮어써야 토글을 흉내낼 수
있다.
"""
from app.config import Settings
from app.ml.factory import build_models


def test_real_when_both_torch_builders_succeed(monkeypatch):
    monkeypatch.setattr(Settings, "USE_TORCH_ANOMALY", True)
    monkeypatch.setattr(Settings, "USE_TORCH_EMBEDDING", True)
    monkeypatch.setattr(
        "app.ml.torch_anomaly_model.build_torch_anomaly_model",
        lambda model_dir: object(),
    )
    monkeypatch.setattr(
        "app.ml.torch_embedding_model.build_torch_embedding_model",
        lambda dim, image_size: object(),
    )

    result = build_models(Settings())

    assert result.anomaly_is_real is True
    assert result.embedding_is_real is True
    assert result.engine_status == "real"


def test_mock_when_anomaly_builder_fails_despite_toggle(monkeypatch):
    monkeypatch.setattr(Settings, "USE_TORCH_ANOMALY", True)
    monkeypatch.setattr(Settings, "USE_TORCH_EMBEDDING", True)
    # anomaly 어댑터 로드 실패(가중치 누락 등) 시뮬레이션: None 반환.
    monkeypatch.setattr(
        "app.ml.torch_anomaly_model.build_torch_anomaly_model",
        lambda model_dir: None,
    )
    monkeypatch.setattr(
        "app.ml.torch_embedding_model.build_torch_embedding_model",
        lambda dim, image_size: object(),
    )

    result = build_models(Settings())

    assert result.anomaly_is_real is False
    assert result.embedding_is_real is True
    assert result.engine_status == "mock"


def test_mock_when_embedding_builder_fails_despite_toggle(monkeypatch):
    monkeypatch.setattr(Settings, "USE_TORCH_ANOMALY", True)
    monkeypatch.setattr(Settings, "USE_TORCH_EMBEDDING", True)
    monkeypatch.setattr(
        "app.ml.torch_anomaly_model.build_torch_anomaly_model",
        lambda model_dir: object(),
    )
    # embedding 어댑터 로드 실패 시뮬레이션: None 반환.
    monkeypatch.setattr(
        "app.ml.torch_embedding_model.build_torch_embedding_model",
        lambda dim, image_size: None,
    )

    result = build_models(Settings())

    assert result.anomaly_is_real is True
    assert result.embedding_is_real is False
    assert result.engine_status == "mock"


def test_mock_when_both_toggles_off_and_torch_builders_not_attempted(monkeypatch):
    monkeypatch.setattr(Settings, "USE_TORCH_ANOMALY", False)
    monkeypatch.setattr(Settings, "USE_TORCH_EMBEDDING", False)

    def _fail_anomaly(model_dir):
        raise AssertionError("USE_TORCH_ANOMALY=false 인데 torch anomaly 빌더가 호출됐다")

    def _fail_embedding(dim, image_size):
        raise AssertionError("USE_TORCH_EMBEDDING=false 인데 torch embedding 빌더가 호출됐다")

    monkeypatch.setattr("app.ml.torch_anomaly_model.build_torch_anomaly_model", _fail_anomaly)
    monkeypatch.setattr("app.ml.torch_embedding_model.build_torch_embedding_model", _fail_embedding)

    result = build_models(Settings())

    assert result.anomaly_is_real is False
    assert result.embedding_is_real is False
    assert result.engine_status == "mock"
