"""ML factory. 환경변수 토글에 따라 mock 또는 torch adapter를 만든다."""
from __future__ import annotations

from typing import NamedTuple, Optional

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

    roi_is_real 도 같은 규칙이다. 예전에는 이 필드가 없었다 - 실 ROI 어댑터가
    없어 USE_TORCH_ROI 가 no-op 이었고 factory 가 항상 MockROIModel 을 돌려줬기
    때문이다. 이제 영상 적응형 어댑터(app.ml.cv_roi_model)가 있으므로 그 이유는
    만료됐고, 어느 쪽이 구성됐는지 기록한다.

    다만 **engine_status 판정에는 여전히 ROI 를 넣지 않는다.** 이유는 두 가지다:

    1. 검색의 기본 경로(globalErrorEmbedding)는 ROI 마스크를 전혀 쓰지 않는다.
       SQUID 와 DenseNet 이 둘 다 실제로 올라온 엔진을 ROI 가 mock 이라는 이유로
       "mock" 으로 표시하면, 실제로 동작 중인 real 엔진을 거짓으로 깎아내린다.
    2. cv_roi_model 은 학습된 모델이 아니라 고전 CV 휴리스틱이다. 이것을 real 의
       필요조건으로 승격시키면 engineStatus 가 뜻하는 바("실제 학습 모델이
       올라왔는가")가 흐려진다.

    대신 roi_status 로 따로 보고한다 - 감추지 않되, 다른 것과 섞지도 않는다.
    """

    anomaly: AnomalyModel
    roi: ROIMaskModel
    embedder: EmbeddingModel
    anomaly_is_real: bool
    embedding_is_real: bool
    roi_is_real: bool = False
    settings_embedding_version: Optional[str] = None

    @property
    def engine_status(self) -> str:
        """실행 중인 추론 엔진이 실제 모델인지 mock 인지.

        anomaly / embedding 어댑터가 *둘 다* 실제로 구성됐을 때만 "real".
        하나라도 mock(토글이 꺼졌거나, 켜졌지만 로드에 실패)이면 "mock".
        이 값이 engineStatus 의 유일한 산출 경로여야 한다.
        """
        return "real" if (self.anomaly_is_real and self.embedding_is_real) else "mock"

    @property
    def roi_status(self) -> str:
        """ROI 마스크가 영상 적응형 분할("cv")인지 고정 타원 mock("mock")인지.

        engine_status 와 달리 별도로 보고된다(위 독스트링 참고). roiStats 와
        ROI별 임베딩의 의미가 이 값에 달려 있다.
        """
        return "cv" if self.roi_is_real else "mock"

    @property
    def mask_version(self) -> str:
        """저장된 ROI 마스크/임베딩이 어느 분할기에서 나왔는지.

        embedding_version 과 같은 규칙이다 - 실제로 구성된 모델이 답한다.
        """
        return getattr(self.roi, "version", "unknown")

    @property
    def embedding_version(self) -> str:
        """저장된 벡터가 어느 인코더에서 나왔는지.

        engine_status 와 같은 규칙이다 — 토글이 아니라 실제로 구성된 모델이
        답한다. 토글이 켜져 있어도 로드에 실패해 mock 으로 fallback 했으면
        mock 의 버전이 기록돼야 한다.

        이 값은 케이스 문서마다 저장되며(case_service), 인코더를 바꿨을 때
        재색인이 필요한지 판단하는 유일한 단서다. 설정 기본값으로 두면 어떤
        모델이 돌든 같은 문자열이 박혀 그 판단이 불가능해진다.

        운영에서 문자열을 손으로 고정해야 하는 경우를 위해 Settings.
        EMBEDDING_VERSION 이 설정돼 있으면 그것이 이긴다. 다만 기본값은
        None 이어야 한다 — 기본값이 있으면 아무도 설정하지 않은 환경에서
        그 값이 모델과 무관하게 기록된다.
        """
        if self.settings_embedding_version:
            return self.settings_embedding_version
        return getattr(self.embedder, "version", "unknown")


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
    roi_is_real = False
    if settings.USE_CV_ROI:
        from app.ml import cv_roi_model

        r = cv_roi_model.build_cv_roi_model()
        if r is not None:
            roi = r
            roi_is_real = True

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
        roi_is_real=roi_is_real,
        settings_embedding_version=settings.EMBEDDING_VERSION,
    )
