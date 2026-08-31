"""FastAPI DI helpers. 싱글턴 컨테이너 패턴."""
from __future__ import annotations

from functools import lru_cache

from app.config import Settings, get_settings
from app.db.arango_client import get_db
from app.db.repositories import CaseRepository
from app.ml.factory import build_models
from app.services.agent_service import AgentService
from app.services.case_service import CaseService
from app.services.embedding_service import EmbeddingService
from app.services.reasoning_service import ReasoningService
from app.services.reconstruction_service import ReconstructionService
from app.services.roi_mask_service import ROIMaskService
from app.services.similarity_service import SimilarityService
from app.services.storage_service import LocalStorage


class ServiceContainer:
    def __init__(self) -> None:
        self.settings: Settings = get_settings()
        self.db = get_db(self.settings)
        self.repo = CaseRepository(self.db, self.settings)

        build_result = build_models(self.settings)
        self.recon = ReconstructionService(build_result.anomaly)
        self.roi = ROIMaskService(build_result.roi)
        self.embedder = EmbeddingService(build_result.embedder)
        # 실제로 구성된 모델(build_result)을 근거로 판정. 토글 값을 직접 읽지 않는다.
        self.engine_status: str = build_result.engine_status
        self.embedding_version: str = build_result.embedding_version
        # ROI 는 engine_status 에 섞지 않고 따로 보고한다(factory.BuildResult 참고).
        self.roi_status: str = build_result.roi_status
        self.roi_mask_version: str = build_result.mask_version

        self.similarity = SimilarityService(self.repo)
        self.reasoning = ReasoningService(self.repo, self.settings)
        self.agent = AgentService(self.settings)

        self.s_images = LocalStorage(self.settings.images_dir)
        self.s_recon = LocalStorage(self.settings.recon_dir)
        self.s_heatmap = LocalStorage(self.settings.heatmap_dir)

        self.case_service = CaseService(
            settings=self.settings,
            repo=self.repo,
            recon=self.recon,
            roi=self.roi,
            embedder=self.embedder,
            similarity=self.similarity,
            reasoning=self.reasoning,
            agent=self.agent,
            storage_images=self.s_images,
            storage_recon=self.s_recon,
            storage_heatmap=self.s_heatmap,
            engine_status=self.engine_status,
            embedding_version=self.embedding_version,
            roi_status=self.roi_status,
            roi_mask_version=self.roi_mask_version,
        )


@lru_cache(maxsize=1)
def get_container() -> ServiceContainer:
    return ServiceContainer()
