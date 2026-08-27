"""ML factory. 환경변수 토글에 따라 mock 또는 torch adapter를 만든다."""
from __future__ import annotations

from typing import NamedTuple

from app.config import Settings
from app.ml.base import AnomalyModel, EmbeddingModel, ROIMaskModel
from app.ml.mock_anomaly_model import MockAnomalyModel
from app.ml.mock_embedding_model import MockEmbeddingModel
from app.ml.mock_roi_model import MockROIModel


class BuildResult(NamedTuple):
    """build_models() 의 결과.

    USE_TORCH_ANOMALY / USE_TORCH_EMBEDDING 토글은 "torch 어댑터를 시도하라"는
    요청일 뿐, 실제로 구성됐다는 보장이 아니다(가중치 누락, import 실패 등으로
    torch_anomaly_model.build_torch_anomaly_model() / torch_embedding_model.
    build_torch_embedding_model() 이 None 을 반환하면 factory 는 조용히 mock으로
    fallback 한다). anomaly_is_real / embedding_is_real 은 그 "결과"를 담아,
    engineStatus 가 토글이 아니라 실제로 만들어진 모델을 근거로 판정되도록 한다.

    roi_is_real 필드는 없다: 실제 ROI 어댑터(HybridGNet 등)가 아직 구현되지
    않아 USE_TORCH_ROI 는 no-op 이고 factory 는 항상 MockROIModel 을 반환한다.
    따라서 ROI 는 engineStatus 판정에서 제외한다.
    """

    anomaly: AnomalyModel
    roi: ROIMaskModel
    embedder: EmbeddingModel
    anomaly_is_real: bool
    embedding_is_real: bool

    @property
    def engine_status(self) -> str:
        """실행 중인 추론 엔진이 실제 모델인지 mock 인지.

        anomaly / embedding 어댑터가 *둘 다* 실제로 구성됐을 때만 "real".
        하나라도 mock(토글이 꺼졌거나, 켜졌지만 로드에 실패)이면 "mock".
        이 값이 engineStatus 의 유일한 산출 경로여야 한다.
        """
        return "real" if (self.anomaly_is_real and self.embedding_is_real) else "mock"


def build_models(settings: Settings) -> BuildResult:
    anomaly: AnomalyModel = MockAnomalyModel()
    anomaly_is_real = False
    if settings.USE_TORCH_ANOMALY:
        from app.ml.torch_anomaly_model import build_torch_anomaly_model

        m = build_torch_anomaly_model(settings.SQUID_MODEL_DIR)
        if m is not None:
            anomaly = m
            anomaly_is_real = True

    roi: ROIMaskModel = MockROIModel()
    # 실제 ROI(HybridGNet 등)는 향후 어댑터 추가 위치. 그때까지는 항상 mock.

    embedder: EmbeddingModel = MockEmbeddingModel(dim=settings.EMBEDDING_DIM)
    embedding_is_real = False
    if settings.USE_TORCH_EMBEDDING:
        from app.ml.torch_embedding_model import build_torch_embedding_model

        e = build_torch_embedding_model(dim=settings.EMBEDDING_DIM, image_size=settings.IMAGE_SIZE)
        if e is not None:
            embedder = e
            embedding_is_real = True

    return BuildResult(
        anomaly=anomaly,
        roi=roi,
        embedder=embedder,
        anomaly_is_real=anomaly_is_real,
        embedding_is_real=embedding_is_real,
    )
