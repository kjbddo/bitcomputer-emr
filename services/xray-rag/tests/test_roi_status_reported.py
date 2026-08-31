"""roiStatus 는 계산만 되고 응답에 없었다.

`app/ml/factory.py` 의 BuildResult 는 engine_status 와 roi_status 를 일부러
분리해서 계산한다 — ROI 는 검색 기본 경로(globalErrorEmbedding)에 쓰이지 않아서
mock 으로 내려가도 엔진 자체는 real 일 수 있고, 그 둘을 한 값에 섞으면 어느 쪽이
내려간 것인지 알 수 없어지기 때문이다.

그런데 그렇게 갈라 놓은 roi_status 가 `dependencies.py` 의 컨테이너 속성까지만
가고 응답에는 실리지 않았다. 결과가 이랬다:

- 응답의 `queryCase.maskVersion` 은 환경변수로 고정된 값(MASK_VERSION)이라
  분할기를 무엇으로 바꾸든 그대로였다
- 실제 출처인 `roiMaskVersion` 은 저장된 케이스 문서에만 있고 질의 쪽에는 없었다
- `roiStatus` 는 어디에도 없었다

즉 **PSPNet 이 실제로 떴는지, 가중치가 없어 cv 로 내려갔는지, 고정 타원(mock)까지
떨어졌는지를 응답만 보고는 알 수 없었다.** roiStats 와 ROI별 임베딩의 의미가 전부
그 값에 달려 있는데도 그랬다. B0 이 세운 원칙("출처는 설정이 아니라 실행 경로에서
유도해 보고한다")에서 이 축만 보고 단계가 빠져 있던 셈이다.

여기서 고정하는 것은 두 가지다: 값이 응답에 실린다는 것, 그리고 그 값이 설정이
아니라 실제로 구성된 분할기를 따라간다는 것.
"""
import numpy as np
import pytest

from app.models.schemas import InferenceResponse
from app.services.case_service import CaseService


def _minimal_response(**overrides) -> InferenceResponse:
    """스키마 기본값만 확인하기 위한 최소 응답."""
    payload = dict(
        queryCase={},
        predictedDiseases=[],
        notableFindings=[],
        similarCases=[],
        uncertainty={"level": "high", "reasons": []},
        explanation={},
        warning="",
    )
    payload.update(overrides)
    return InferenceResponse(**payload)


def test_roi_status_defaults_to_mock_when_absent():
    """넘어오지 않았으면 가장 약한 것으로 읽는다(fail-safe).

    engineStatus 와 같은 규칙이다. 빠졌을 때 "pspnet" 이나 빈 문자열로 읽으면,
    값을 못 받은 것과 실제로 분할기가 떴는지를 구별할 수 없다.
    """
    assert _minimal_response().roiStatus == "mock"


def test_roi_status_is_separate_from_engine_status():
    """두 축을 한 값으로 합치지 않는다.

    ROI 가 mock 으로 내려가도 SQUID·DenseNet 이 둘 다 실제로 올라왔으면
    engineStatus 는 real 이다. 이 조합이 표현 가능해야 한다.
    """
    r = _minimal_response(engineStatus="real", roiStatus="mock")
    assert (r.engineStatus, r.roiStatus) == ("real", "mock")


@pytest.mark.parametrize("status", ["pspnet", "cv", "mock"])
def test_inference_response_carries_the_configured_roi_status(status):
    """세 등급이 그대로 실린다."""
    assert _minimal_response(roiStatus=status).roiStatus == status


def _service(**overrides) -> CaseService:
    """응답 조립에 필요한 것만 넘긴 CaseService.

    추론을 돌리지 않고 provenance 배선만 확인하므로 협력자는 None 으로 둔다 —
    이 테스트가 보는 경로는 생성자가 받은 값을 응답에 싣는 부분뿐이다.
    """
    from app.config import Settings

    kwargs = dict(
        settings=Settings(),
        repo=None,
        recon=None,
        roi=None,
        embedder=None,
        similarity=None,
        reasoning=None,
        agent=None,
        storage_images=None,
        storage_recon=None,
        storage_heatmap=None,
    )
    kwargs.update(overrides)
    return CaseService(**kwargs)


def test_case_service_defaults_roi_status_to_mock():
    """호출자가 안 넘기면 mock 이다 — engine_status 와 같은 fail-safe."""
    assert _service().roi_status == "mock"


def test_case_service_keeps_roi_status_and_mask_version_apart():
    """두 필드는 서로 다른 질문에 답하므로 합치지 않는다.

    roi_status 는 "어느 등급으로 내려갔나"(pspnet/cv/mock)이고,
    roi_mask_version 은 "그 마스크를 만든 것의 식별자"다. 분할기를 바꾼 뒤
    저장된 벡터와 질의 벡터가 같은 해부 기준 위에 있는지는 후자로 판단한다.
    """
    svc = _service(roi_status="cv", roi_mask_version="cv_lung_heart_v1")
    assert svc.roi_status == "cv"
    assert svc.roi_mask_version == "cv_lung_heart_v1"


def _fake_xray_bytes(seed: int = 0) -> bytes:
    import io

    from PIL import Image

    rng = np.random.default_rng(seed)
    arr = rng.integers(0, 255, size=(256, 256), dtype=np.uint8)
    arr[100:140, 130:170] = 240
    img = Image.fromarray(arr, mode="L")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _real_service(**overrides) -> CaseService:
    """mock 모델 + fake 저장소로 실제 infer() 를 돌릴 수 있는 서비스."""
    from app.config import get_settings
    from app.ml.factory import build_models
    from app.services.agent_service import AgentService
    from app.services.embedding_service import EmbeddingService
    from app.services.reasoning_service import ReasoningService
    from app.services.reconstruction_service import ReconstructionService
    from app.services.roi_mask_service import ROIMaskService
    from app.services.similarity_service import SimilarityService
    from app.services.storage_service import LocalStorage

    from tests.fakes import _FakeRepo

    s = get_settings()
    repo = _FakeRepo()
    build_result = build_models(s)
    kwargs = dict(
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
    )
    kwargs.update(overrides)
    return CaseService(**kwargs)


def test_infer_response_carries_the_services_roi_status():
    """실제 infer() 를 태워, 조립된 응답에 값이 실리는지 본다.

    스키마에 필드가 있고 서비스가 속성을 들고 있어도, 응답을 만드는 자리에서
    넘겨주지 않으면 roiStatus 는 언제나 기본값 "mock" 이 된다 - 필드는 있는데
    실행 경로와 무관한, 없는 것보다 나쁜 상태다. 그 한 줄을 여기서 고정한다.

    구성된 것과 다른 값("pspnet")을 일부러 주입한다. 배선이 끊기면 기본값
    "mock" 이 나오므로 그 차이로 잡힌다.
    """
    svc = _real_service(roi_status="pspnet", roi_mask_version="pspnet_chestxdet_v1")
    res = svc.infer(
        image_bytes=_fake_xray_bytes(seed=7),
        view=None,
        model_version=None,
        mask_version=None,
        top_k=3,
    )

    assert res.roiStatus == "pspnet"


def test_infer_response_reports_the_query_masks_own_provenance():
    """queryCase 는 고정된 비교 키와 실제 출처를 둘 다 낸다.

    maskVersion 은 환경변수로 고정된 값이라 분할기를 바꿔도 그대로다. 그것만
    보고는 이 질의의 마스크가 무엇에서 나왔는지 알 수 없고, 저장된 코퍼스와
    같은 해부 기준 위에 있는지도 판단할 수 없다. 저장 문서가 이미 남기고 있는
    roiMaskVersion 을 질의 쪽에도 낸다.
    """
    svc = _real_service(roi_status="cv", roi_mask_version="cv_lung_heart_v1")
    res = svc.infer(
        image_bytes=_fake_xray_bytes(seed=7),
        view=None,
        model_version=None,
        mask_version=None,
        top_k=3,
    )

    query_case = res.queryCase
    assert query_case["roiMaskVersion"] == "cv_lung_heart_v1"
    # 둘은 서로 다른 질문에 답하므로 한쪽이 다른 쪽을 대신하지 않는다.
    assert query_case["maskVersion"] != query_case["roiMaskVersion"]


def test_dependencies_pass_roi_status_from_the_model_actually_built(monkeypatch):
    """컨테이너는 토글이 아니라 build_result 를 근거로 값을 넘긴다.

    이 배선이 끊기면 roiStatus 는 조용히 기본값 "mock" 으로 남는다 — 응답에
    필드는 있는데 언제나 mock 이라, 없는 것보다 나쁜 상태가 된다.
    """
    import inspect

    from app.api import dependencies

    src = inspect.getsource(dependencies.ServiceContainer.__init__)
    assert "roi_status=self.roi_status" in src, (
        "ServiceContainer 가 CaseService 에 roi_status 를 넘기지 않는다 - "
        "응답의 roiStatus 가 실행 경로와 무관해진다"
    )
    assert "self.roi_status: str = build_result.roi_status" in src, (
        "roi_status 가 build_result 가 아닌 곳에서 나온다 - 설정값이 출처를 "
        "가장하게 된다"
    )
