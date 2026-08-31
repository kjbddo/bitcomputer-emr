"""Case 등록 / inference 워크플로우 orchestrator."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from app.config import Settings
from app.db.repositories import CaseRepository
from app.domain.findings import derive_finding_tags
from app.domain.scoring import is_supported_disease_tag
from app.models.schemas import (
    CaseRegisterMetadata,
    InferenceResponse,
    NotableFinding,
    PredictedDisease,
    Quality,
    ROIStats,
    SimilarCase,
)
from app.services.agent_service import AgentService
from app.services.embedding_service import EmbeddingService
from app.services.error_map_service import compute_error_map, compute_roi_stats
from app.services.heatmap_service import save_heatmap
from app.services.preprocessing_service import preprocess
from app.services.reasoning_service import ReasoningService
from app.services.reconstruction_service import ReconstructionService
from app.services.roi_mask_service import ROIMaskService
from app.services.similarity_service import SimilarityService
from app.services.storage_service import LocalStorage
from app.utils.id_utils import new_case_key, safe_doc_key
from app.utils.image_utils import save_array_as_png
from app.utils.time_utils import utc_now_iso


class CaseService:
    def __init__(
        self,
        settings: Settings,
        repo: CaseRepository,
        recon: ReconstructionService,
        roi: ROIMaskService,
        embedder: EmbeddingService,
        similarity: SimilarityService,
        reasoning: ReasoningService,
        agent: AgentService,
        storage_images: LocalStorage,
        storage_recon: LocalStorage,
        storage_heatmap: LocalStorage,
        engine_status: str = "mock",
        # 실제로 구성된 임베딩 모델의 식별자(factory.BuildResult.embedding_version).
        # 설정값이 아니다 — 어떤 인코더가 이 벡터를 만들었는지가 기록돼야
        # 나중에 재색인이 필요한지 판단할 수 있다.
        embedding_version: str = "unknown",
        # 실제로 구성된 ROI 분할기의 식별자(factory.BuildResult.mask_version).
        # maskVersion 과는 별개로 저장한다 - maskVersion 은 "어떤 케이스끼리
        # 비교해도 되는가"를 정하는 운영 키(환경변수로 고정)이고, 이 값은 "그
        # 마스크가 실제로 무엇이 만든 것인가"라는 출처다. 둘을 하나로 합치면
        # 분할기를 바꿔 재시드한 뒤 예전 벡터와 섞였는지 사후에 알 수 없다.
        roi_mask_version: str = "unknown",
        # 실제로 구성된 ROI 분할기(factory.BuildResult.roi_status): pspnet/cv/mock.
        # roi_mask_version 이 "무엇이 만들었나"라면 이쪽은 "어느 등급으로
        # 내려갔나"다. 기본값은 engine_status 와 같은 이유로 "mock" 이다.
        roi_status: str = "mock",
    ) -> None:
        self.settings = settings
        self.repo = repo
        self.recon = recon
        self.roi = roi
        self.embedder = embedder
        self.similarity = similarity
        self.reasoning = reasoning
        self.agent = agent
        self.s_images = storage_images
        self.s_recon = storage_recon
        self.s_heatmap = storage_heatmap
        # 실제로 구성된 모델을 근거로 호출자(dependencies.py)가 계산해 넘긴 값.
        # 알 수 없거나 넘어오지 않은 경우 기본값은 항상 "mock" (fail-safe).
        self.engine_status = engine_status
        self.embedding_version = embedding_version
        self.roi_mask_version = roi_mask_version
        self.roi_status = roi_status

    # ---------- 등록 ----------
    def register_case(
        self,
        image_bytes: bytes,
        original_filename: str,
        disease_tags: List[str],
        finding_tags: Optional[List[str]],
        metadata: CaseRegisterMetadata,
        case_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """케이스를 등록한다.

        `case_key` 를 주면 그 키로 등록한다 - 같은 키가 이미 있으면 덮어쓴다.
        적재 스크립트가 원본 경로에서 유도한 키를 넘겨 재실행을 멱등하게 만드는
        용도다(app.utils.id_utils.case_key_for_source). 주지 않으면 예전처럼
        무작위 키를 만든다.

        덮어쓸 때는 기존 간선을 먼저 끊는다. 간선 키가 case_key 에서 유도되므로
        같은 태그는 덮어써지지만, 없어진 태그의 간선은 그대로 남기 때문이다.
        """
        replacing = case_key is not None and self.repo.get_case(case_key) is not None
        case_key = case_key or new_case_key()
        ext = Path(original_filename or ".png").suffix.lower() or ".png"

        # 1) 원본 저장
        img_path = self.s_images.resolve(f"{case_key}{ext}")
        img_path.write_bytes(image_bytes)

        # 2) workflow
        image = preprocess(image_bytes, self.settings.IMAGE_SIZE)
        recon = self.recon.reconstruct(image)
        recon_path = self.s_recon.resolve(f"{case_key}_recon.png")
        save_array_as_png(recon, recon_path)

        error_map = compute_error_map(image, recon)
        masks = self.roi.generate(image)
        roi_stats = compute_roi_stats(error_map, masks, self.settings)

        embeddings = self.embedder.embed_all(error_map, masks)

        # 3) heatmap 저장
        heatmap_path = self.s_heatmap.resolve(f"{case_key}_heatmap.png")
        save_heatmap(error_map, heatmap_path, original=image, alpha=0.55)

        # 4) finding tag 자동 도출 + 입력 finding 병합
        disease_tags = [d for d in disease_tags if is_supported_disease_tag(d)]
        auto_findings = derive_finding_tags(roi_stats)
        merged_findings = list(dict.fromkeys((finding_tags or []) + auto_findings))

        # 5) ArangoDB document 작성
        doc = {
            "_key": case_key,
            "imagePath": str(img_path),
            "reconPath": str(recon_path),
            "heatmapPath": str(heatmap_path),
            "view": metadata.view or "PA",
            "modelVersion": metadata.modelVersion or self.settings.MODEL_VERSION,
            "maskVersion": metadata.maskVersion or self.settings.MASK_VERSION,
            "roiMaskVersion": self.roi_mask_version,
            "embeddingVersion": self.embedding_version,
            "globalErrorEmbedding": embeddings["global"].tolist(),
            "leftLungErrorEmbedding": embeddings["left_lung"].tolist(),
            "rightLungErrorEmbedding": embeddings["right_lung"].tolist(),
            "heartErrorEmbedding": embeddings["heart"].tolist(),
            "roiStats": {k: _stats_to_dict(v) for k, v in roi_stats.items()},
            "diseaseTags": disease_tags,
            "findingTags": merged_findings,
            "quality": Quality().model_dump(),
            "createdAt": utc_now_iso(),
        }
        # 환자/메타 부가 필드(있으면 함께 저장)
        for k in ("patientAge", "sex", "source"):
            v = getattr(metadata, k, None)
            if v is not None:
                doc[k] = v

        if replacing:
            # 덮어쓰기다. 낡은 간선을 먼저 끊지 않으면 이번 등록에서 사라진
            # 태그가 그래프에 계속 매달려 있게 된다.
            self.repo.delete_case_edges(case_key)

        self.repo.insert_case(doc)
        # edges
        for d in disease_tags:
            self.repo.add_case_disease(case_key, safe_doc_key(d))
        for f in merged_findings:
            self.repo.add_case_finding(case_key, safe_doc_key(f))
        for roi_name, stats in roi_stats.items():
            if stats.severity in ("medium", "high"):
                self.repo.add_case_roi_anomaly(
                    case_key,
                    roi_name,
                    mean_error=stats.meanError,
                    p95_error=stats.p95Error,
                    severity=stats.severity,
                )
        # 호출자가 새로 만들어진 것과 덮어쓴 것을 구별할 수 있어야 한다 -
        # 적재 스크립트의 요약이 이 값으로 "몇 건이 갱신됐나"를 센다.
        return {"caseId": case_key, "status": "replaced" if replacing else "created"}

    # ---------- inference ----------
    def infer(
        self,
        image_bytes: bytes,
        view: Optional[str],
        model_version: Optional[str],
        mask_version: Optional[str],
        top_k: int,
    ) -> InferenceResponse:
        image = preprocess(image_bytes, self.settings.IMAGE_SIZE)
        recon = self.recon.reconstruct(image)
        error_map = compute_error_map(image, recon)
        masks = self.roi.generate(image)
        roi_stats = compute_roi_stats(error_map, masks, self.settings)
        embeddings = self.embedder.embed_all(error_map, masks)

        # 임시 heatmap(저장 후 path 반환). 영구 저장은 register와 분리.
        tmp_key = new_case_key()
        heatmap_path = self.s_heatmap.resolve(f"query_{tmp_key}_heatmap.png")
        save_heatmap(error_map, heatmap_path, original=image, alpha=0.55)
        heatmap_url = self._storage_url(heatmap_path)

        # ROI severity dict
        roi_severity = {k: v.severity for k, v in roi_stats.items()}
        similar_cases = self.similarity.search_combined(
            embeddings,
            view=view,
            model_version=model_version or self.settings.MODEL_VERSION,
            mask_version=mask_version or self.settings.MASK_VERSION,
            top_k=top_k,
            roi_severity=roi_severity,
        )

        # query case 자동 finding (참고용)
        query_findings = derive_finding_tags(roi_stats)

        reasoning_out = self.reasoning.reason(
            similar_cases=similar_cases,
            current_roi_stats=roi_stats,
            quality=Quality(),
            view=view,
            model_version=model_version,
        )

        explanation = self.agent.explain(
            diseases=reasoning_out["predictedDiseases"],
            notable_findings=reasoning_out["notableFindings"],
            similar_cases=similar_cases,
            roi_stats=roi_stats,
            uncertainty=reasoning_out["uncertainty"],
            graph_evidence=reasoning_out["graphEvidence"],
        )

        return InferenceResponse(
            queryCase={
                "heatmapPath": heatmap_url,
                "roiStats": {k: _stats_to_dict(v) for k, v in roi_stats.items()},
                "autoFindings": query_findings,
                "view": view or "PA",
                "modelVersion": model_version or self.settings.MODEL_VERSION,
                "maskVersion": mask_version or self.settings.MASK_VERSION,
                # maskVersion 은 환경변수로 고정된 비교 키이고, 이쪽은 이 질의의
                # 마스크를 실제로 만든 분할기다. 저장된 케이스 문서
                # (doc["roiMaskVersion"])와 같은 값이어야 질의와 코퍼스가 같은
                # 해부 기준 위에서 비교된다 - 다르면 재시드가 필요하다는 뜻이다.
                "roiMaskVersion": self.roi_mask_version,
            },
            predictedDiseases=reasoning_out["predictedDiseases"],
            notableFindings=reasoning_out["notableFindings"],
            similarCases=similar_cases,
            uncertainty=reasoning_out["uncertainty"],
            explanation=explanation,
            heatmapPath=heatmap_url,
            warning=self.settings.SAFETY_NOTICE,
            engineStatus=self.engine_status,
            roiStatus=self.roi_status,
        )

    def _storage_url(self, path: Path) -> str:
        rel = path.resolve().relative_to(self.settings.STORAGE_DIR.resolve())
        return "/storage/" + rel.as_posix()


def _stats_to_dict(s: ROIStats) -> Dict[str, Any]:
    return s.model_dump()
