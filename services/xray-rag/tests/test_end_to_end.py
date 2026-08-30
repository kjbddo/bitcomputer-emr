"""mock 모델 + fake ArangoDB로 케이스 등록 + inference 흐름 통합 테스트."""
from __future__ import annotations

import io

import numpy as np
from PIL import Image

from app.config import get_settings
from app.ml.factory import build_models
from app.services.agent_service import AgentService
from app.services.case_service import CaseService
from app.services.embedding_service import EmbeddingService
from app.services.reasoning_service import ReasoningService
from app.services.reconstruction_service import ReconstructionService
from app.services.roi_mask_service import ROIMaskService
from app.services.similarity_service import SimilarityService
from app.services.storage_service import LocalStorage

from tests.fakes import _FakeRepo


def _make_fake_xray_bytes(seed: int = 0) -> bytes:
    rng = np.random.default_rng(seed)
    arr = rng.integers(0, 255, size=(256, 256), dtype=np.uint8)
    # 중심부에 밝은 패치(병변 흉내)
    arr[100:140, 130:170] = 240
    img = Image.fromarray(arr, mode="L")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _build_service():
    s = get_settings()
    repo = _FakeRepo()
    build_result = build_models(s)
    return CaseService(
        settings=s,
        repo=repo,
        recon=ReconstructionService(build_result.anomaly),
        roi=ROIMaskService(build_result.roi),
        embedder=EmbeddingService(build_result.embedder),
        similarity=SimilarityService(repo),
        reasoning=ReasoningService(repo, s),
        agent=AgentService(s),
        storage_images=LocalStorage(s.images_dir),
        storage_recon=LocalStorage(s.recon_dir),
        storage_heatmap=LocalStorage(s.heatmap_dir),
        engine_status=build_result.engine_status,
        embedding_version=build_result.embedding_version,
    ), repo


def test_register_then_infer_returns_predicted_disease():
    svc, repo = _build_service()

    # 3개 case 등록(같은 disease)
    for i in range(3):
        svc.register_case(
            image_bytes=_make_fake_xray_bytes(seed=i),
            original_filename=f"a{i}.png",
            disease_tags=["pneumonia"],
            finding_tags=None,
            metadata=__import__("app.models.schemas", fromlist=["CaseRegisterMetadata"]).CaseRegisterMetadata(),
        )

    # 비슷한 패치를 가진 새 이미지로 inference
    res = svc.infer(
        image_bytes=_make_fake_xray_bytes(seed=42),
        view=None,
        model_version=None,
        mask_version=None,
        top_k=3,
    )

    assert "queryCase" in res.model_dump()
    assert res.predictedDiseases, "predictedDiseases should not be empty"
    # mock embedding이 결정론적이라 등록한 disease가 후보에 떠야 함
    assert any(d.disease == "pneumonia" for d in res.predictedDiseases)
    assert res.warning  # safety notice
    assert res.uncertainty.level in ("low", "medium", "high")


def test_stored_case_records_the_version_of_the_encoder_that_made_the_vectors():
    """케이스 문서의 embeddingVersion 은 실제 인코더에서 와야 한다.

    예전에는 이 필드가 `settings.EMBEDDING_VERSION`(기본값 "mock_pca_v1")에서
    바로 왔다. 어떤 모델이 돌든 같은 문자열이 박혀, 저장된 벡터가 어느
    인코더에서 나왔는지 알 수 없었다 — 인코더를 바꿨을 때 재색인이 필요한지
    판단하는 유일한 단서인데도 그렇다.

    factory 쪽만 검사하면 이 회귀를 못 잡는다. 실제로 저장되는 문서를 본다.
    """
    from app.config import Settings

    from app.models.schemas import CaseRegisterMetadata

    svc, repo = _build_service()
    svc.register_case(
        image_bytes=_make_fake_xray_bytes(seed=0),
        original_filename="v.png",
        disease_tags=["pneumonia"],
        finding_tags=None,
        metadata=CaseRegisterMetadata(),
    )

    assert repo.cases, "케이스가 저장돼야 이 테스트가 의미가 있다"
    stored = list(repo.cases.values())[-1]["embeddingVersion"]

    build_result = build_models(get_settings())
    assert stored == build_result.embedding_version
    # 설정에서 온 값이 아니라 모델이 답한 값이다.
    assert stored == getattr(build_result.embedder, "version")
    assert Settings.EMBEDDING_VERSION is None, (
        "EMBEDDING_VERSION 에 기본값이 생기면 모델과 무관한 값이 다시 박힌다"
    )

