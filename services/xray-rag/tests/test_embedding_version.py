"""embeddingVersion 은 설정이 아니라 실제로 만들어진 임베딩 모델에서 나와야 한다.

`app/ml/factory.py` 는 engineStatus 에 대해 이미 이 원칙을 문서화하고 있다 —
"USE_TORCH_* 는 시도 토글일 뿐, 판정은 실제로 구성된 모델을 근거로 한다".
그런데 embeddingVersion 은 그 원칙 밖에 있었다: `Settings.EMBEDDING_VERSION`
기본값 문자열("mock_pca_v1")이 어떤 모델이 벡터를 만들었는지와 무관하게 모든
케이스 문서에 그대로 박혔다(case_service.py 의 doc["embeddingVersion"]).

이게 왜 문제인가: 벡터 저장소에서 이 필드는 "저장된 벡터가 어느 인코더에서
나왔는가"를 답하는 유일한 단서다. 인코더를 바꾸면 기존 벡터와 새 질의 벡터는
비교 불가능해지므로 재색인이 필요한데, 그 판단을 이 필드로 한다. 값이 실제
모델과 무관하면 재색인이 필요한 순간을 알아낼 방법이 없다.

DenseNet121 벡터에 "mock_pca_v1" 이 찍히는 것은 검사하지 않은 것을 검사했다고
말하는 것과 같은 부류의 결함이다.
"""
import numpy as np

from app.config import Settings
from app.ml.factory import build_models
from app.ml.mock_embedding_model import MockEmbeddingModel


def _fake_torch_embedder(dim: int):
    """실제 가중치 없이 torch 임베더 자리를 채운다."""

    class _Fake:
        def __init__(self) -> None:
            self.dim = dim
            self.version = "densenet121_imagenet_1024"

        def embed(self, error_map: np.ndarray) -> np.ndarray:
            return np.zeros(self.dim, dtype=np.float32)

    return _Fake()


def test_mock_embedder_reports_its_own_version():
    """mock 은 스스로를 mock 이라고 말한다."""
    m = MockEmbeddingModel(dim=1024)
    assert m.version == "mock_pca_v1"


def test_build_result_exposes_version_of_the_model_actually_built():
    """토글이 아니라 구성 결과에서 버전이 나온다."""
    settings = Settings()
    result = build_models(settings)
    # 기본 설정(USE_TORCH_EMBEDDING=false)에서는 mock 이 구성된다.
    assert result.embedding_is_real is False
    assert result.embedding_version == "mock_pca_v1"


def test_version_follows_the_real_model_when_torch_embedder_is_built(monkeypatch):
    """torch 임베더가 실제로 구성되면 버전도 그것을 따라간다."""
    monkeypatch.setattr(Settings, "USE_TORCH_EMBEDDING", True)
    monkeypatch.setattr(
        "app.ml.torch_embedding_model.build_torch_embedding_model",
        lambda dim, image_size: _fake_torch_embedder(dim),
    )

    result = build_models(Settings())

    assert result.embedding_is_real is True
    assert result.embedding_version == "densenet121_imagenet_1024"


def test_failed_torch_load_reports_mock_version_not_torch(monkeypatch):
    """토글이 켜져 있어도 로드에 실패했으면 mock 버전이어야 한다.

    engineStatus 와 같은 이유다 — 토글은 의도이고, 기록해야 할 것은 결과다.
    """
    monkeypatch.setattr(Settings, "USE_TORCH_EMBEDDING", True)
    monkeypatch.setattr(
        "app.ml.torch_embedding_model.build_torch_embedding_model",
        lambda dim, image_size: None,
    )

    result = build_models(Settings())

    assert result.embedding_is_real is False
    assert result.embedding_version == "mock_pca_v1"


def test_env_override_still_wins_when_explicitly_set(monkeypatch):
    """운영에서 버전 문자열을 손으로 고정해야 하는 경우를 막지 않는다.

    다만 기본값이 있어서는 안 된다 — 기본값이 있으면 아무도 설정하지 않은
    환경에서 그 값이 모델과 무관하게 기록된다. 그게 이 결함의 원인이었다.
    """
    monkeypatch.setattr(Settings, "EMBEDDING_VERSION", "pinned_v9")
    result = build_models(Settings())
    assert result.embedding_version == "pinned_v9"
