"""ROI 어댑터가 factory 에서 정직하게 배선되는지 확인한다.

anomaly / embedding 은 이미 "토글은 시도일 뿐, 실제로 구성됐는지는 결과로만 안다"
규칙을 지킨다(test_engine_status.py). ROI 만 예외였다 - 실 어댑터가 없어
USE_TORCH_ROI 가 no-op 이었고 factory 는 항상 MockROIModel 을 돌려줬다.

이제 실 어댑터(classical CV)가 생겼으므로 같은 규칙이 적용돼야 한다:
  - 토글이 켜졌고 빌더가 성공하면 roi_is_real=True, roi_status="cv"
  - 토글이 켜졌지만 빌더가 None 을 돌려주면 mock 으로 fallback 하되 그 사실을 감추지 않는다
  - 토글이 꺼져 있으면 빌더를 아예 부르지 않는다

engine_status 는 의도적으로 그대로 둔다 - 이유는 factory.BuildResult 독스트링 참고.
"""
from app.config import Settings
from app.ml.cv_roi_model import CVSegmentationROIModel
from app.ml.factory import build_models
from app.ml.mock_roi_model import MockROIModel


class _FakePSPNet:
    """PSPNet 어댑터 대역. factory 는 version 만 읽는다."""

    version = "pspnet_chestxdet_v1"

    def generate_masks(self, image):  # pragma: no cover - 호출되지 않는다
        raise NotImplementedError


def test_cv_roi_used_when_toggle_on_and_builder_succeeds(monkeypatch):
    monkeypatch.setattr(Settings, "USE_PSPNET_ROI", False)
    monkeypatch.setattr(Settings, "USE_CV_ROI", True)
    result = build_models(Settings())

    assert isinstance(result.roi, CVSegmentationROIModel)
    assert result.roi_is_real is True
    assert result.roi_status == "cv"
    assert result.mask_version == "cv_lung_heart_v1"


def test_falls_back_to_mock_when_builder_fails_despite_toggle(monkeypatch):
    monkeypatch.setattr(Settings, "USE_PSPNET_ROI", False)
    monkeypatch.setattr(Settings, "USE_CV_ROI", True)
    monkeypatch.setattr("app.ml.cv_roi_model.build_cv_roi_model", lambda: None)

    result = build_models(Settings())

    assert isinstance(result.roi, MockROIModel)
    assert result.roi_is_real is False
    assert result.roi_status == "mock"
    assert result.mask_version == "mock_ellipse_mask_v1"


def test_builder_not_attempted_when_toggle_off(monkeypatch):
    monkeypatch.setattr(Settings, "USE_PSPNET_ROI", False)
    monkeypatch.setattr(Settings, "USE_CV_ROI", False)

    def _fail():
        raise AssertionError("USE_CV_ROI=false 인데 CV ROI 빌더가 호출됐다")

    monkeypatch.setattr("app.ml.cv_roi_model.build_cv_roi_model", _fail)

    result = build_models(Settings())

    assert isinstance(result.roi, MockROIModel)
    assert result.roi_is_real is False
    assert result.roi_status == "mock"


def test_engine_status_still_ignores_roi(monkeypatch):
    """ROI fallback 이 anomaly/embedding 이 진짜인 엔진을 mock 으로 뒤집지 않는다.

    globalErrorEmbedding 경로는 ROI 를 전혀 쓰지 않는다. ROI 가 mock 이라고
    engineStatus 를 mock 으로 내리면 실제로 동작 중인 real 엔진을 거짓으로
    깎아내리게 된다. 대신 roi_status 로 따로 보고한다.
    """
    monkeypatch.setattr(Settings, "USE_TORCH_ANOMALY", True)
    monkeypatch.setattr(Settings, "USE_TORCH_EMBEDDING", True)
    monkeypatch.setattr(Settings, "USE_PSPNET_ROI", False)
    monkeypatch.setattr(Settings, "USE_CV_ROI", False)
    monkeypatch.setattr(
        "app.ml.torch_anomaly_model.build_torch_anomaly_model", lambda model_dir: object()
    )
    monkeypatch.setattr(
        "app.ml.torch_embedding_model.build_torch_embedding_model",
        lambda dim, image_size: object(),
    )

    result = build_models(Settings())

    assert result.roi_is_real is False
    assert result.engine_status == "real"


# ---------- 세 어댑터의 우선순위: pspnet > cv > mock ----------
#
# 왜 이 순서인가.
#
#   pspnet : ChestX-Det 로 학습된 해부학 분할 모델이다. 셋 중 유일하게 폐/심장
#            /종격동을 "배운" 것이고, 나머지 둘은 그것을 흉내 낸 휴리스틱이다.
#            가중치(273MB)가 있어야 하므로 항상 쓸 수 있지는 않다.
#   cv     : 외부 파일이 필요 없고 영상에 실제로 적응한다. pspnet 을 못 올린
#            환경에서 고정 타원보다 낫다(EVALUATION.md §9).
#   mock   : 입력과 무관한 고정 타원. 마지막 수단이다.
#
# 가용성이 정확히 이 순서의 역순이므로, "가장 좋은 것부터 시도하고 실패하면
# 다음으로 내려간다"가 성립한다. 내려갔다는 사실은 roi_status 로 드러난다.

def test_pspnet_wins_when_available(monkeypatch):
    monkeypatch.setattr(Settings, "USE_PSPNET_ROI", True)
    monkeypatch.setattr(Settings, "USE_CV_ROI", True)

    sentinel = _FakePSPNet()
    monkeypatch.setattr(
        "app.ml.pspnet_roi_model.build_pspnet_roi_model",
        lambda cache_dir=None, allow_download=False: sentinel,
    )

    def _cv_should_not_be_used():
        raise AssertionError("pspnet 이 올라왔는데 cv 빌더가 호출됐다")

    monkeypatch.setattr("app.ml.cv_roi_model.build_cv_roi_model", _cv_should_not_be_used)

    result = build_models(Settings())

    assert result.roi is sentinel
    assert result.roi_is_real is True
    assert result.roi_status == "pspnet"
    assert result.mask_version == "pspnet_chestxdet_v1"


def test_falls_through_to_cv_not_mock_when_pspnet_unavailable(monkeypatch):
    """가중치가 없는 환경(컨테이너)에서 mock 까지 떨어지면 안 된다.

    이 테스트가 빨개지는 방향은 둘이다 - pspnet 실패를 mock 으로 받거나,
    pspnet 을 아예 시도하지 않고 cv 로 가버리거나. 후자는
    test_pspnet_wins_when_available 이 잡는다.
    """
    monkeypatch.setattr(Settings, "USE_PSPNET_ROI", True)
    monkeypatch.setattr(Settings, "USE_CV_ROI", True)
    monkeypatch.setattr(
        "app.ml.pspnet_roi_model.build_pspnet_roi_model",
        lambda cache_dir=None, allow_download=False: None,
    )

    result = build_models(Settings())

    assert isinstance(result.roi, CVSegmentationROIModel)
    assert result.roi_is_real is True
    assert result.roi_status == "cv"
    assert result.mask_version == "cv_lung_heart_v1"


def test_falls_all_the_way_to_mock_when_both_unavailable(monkeypatch):
    monkeypatch.setattr(Settings, "USE_PSPNET_ROI", True)
    monkeypatch.setattr(Settings, "USE_CV_ROI", True)
    monkeypatch.setattr(
        "app.ml.pspnet_roi_model.build_pspnet_roi_model",
        lambda cache_dir=None, allow_download=False: None,
    )
    monkeypatch.setattr("app.ml.cv_roi_model.build_cv_roi_model", lambda: None)

    result = build_models(Settings())

    assert isinstance(result.roi, MockROIModel)
    assert result.roi_is_real is False
    assert result.roi_status == "mock"


def test_pspnet_builder_not_attempted_when_toggle_off(monkeypatch):
    monkeypatch.setattr(Settings, "USE_PSPNET_ROI", False)
    monkeypatch.setattr(Settings, "USE_CV_ROI", True)

    def _fail(**kwargs):
        raise AssertionError("USE_PSPNET_ROI=false 인데 pspnet 빌더가 호출됐다")

    monkeypatch.setattr("app.ml.pspnet_roi_model.build_pspnet_roi_model", _fail)

    result = build_models(Settings())

    assert isinstance(result.roi, CVSegmentationROIModel)
    assert result.roi_status == "cv"


def test_engine_status_still_ignores_pspnet(monkeypatch):
    """ROI 어댑터가 셋으로 늘어도 engine_status 는 여전히 ROI 를 보지 않는다."""
    monkeypatch.setattr(Settings, "USE_TORCH_ANOMALY", True)
    monkeypatch.setattr(Settings, "USE_TORCH_EMBEDDING", True)
    monkeypatch.setattr(Settings, "USE_PSPNET_ROI", True)
    monkeypatch.setattr(Settings, "USE_CV_ROI", False)
    monkeypatch.setattr(
        "app.ml.pspnet_roi_model.build_pspnet_roi_model",
        lambda cache_dir=None, allow_download=False: _FakePSPNet(),
    )
    monkeypatch.setattr(
        "app.ml.torch_anomaly_model.build_torch_anomaly_model", lambda model_dir: object()
    )
    monkeypatch.setattr(
        "app.ml.torch_embedding_model.build_torch_embedding_model",
        lambda dim, image_size: object(),
    )

    result = build_models(Settings())

    assert result.roi_status == "pspnet"
    assert result.engine_status == "real"
