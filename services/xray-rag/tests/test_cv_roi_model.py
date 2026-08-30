"""app.ml.cv_roi_model - 영상 적응형(classical CV) 폐/심장 ROI 분할 테스트.

배경: 기존 MockROIModel 은 `cy=0.55h, rx=0.42w` 처럼 **고정 비율 타원**을 그린다.
어떤 영상이 들어와도 같은 마스크가 나온다. ROI별 임베딩이 해부학적으로 어긋난
픽셀 위에서 계산되면 공간 신호가 잡음이 된다(EVALUATION.md §8.4).

분할 품질 자체는 단위 테스트로 고정할 수 없다. 대신 **고정 타원이면 반드시
깨지는 성질**만 못 박는다.

  1) 영상 적응성: 폐 위치가 다른 두 영상은 다른 마스크를 만들어야 한다.
  2) 국소화: 실제로 어두운 폐 영역 위에 마스크가 얹혀야 한다.
  3) 결정성: 같은 입력은 항상 같은 마스크.
  4) 배타성: heart 는 폐와, left 는 right 와 겹치지 않는다.
  5) fallback 가시성: 분할이 실패해 mock 타원으로 되돌아가면 **조용히** 하지 않는다.
"""
from __future__ import annotations

import logging

import numpy as np
import pytest

from app.ml.cv_roi_model import CVSegmentationROIModel, build_cv_roi_model
from app.ml.mock_roi_model import MockROIModel

EXPECTED_KEYS = {
    "full_lung",
    "left_lung",
    "right_lung",
    "heart",
    "upper_left_lung",
    "lower_left_lung",
    "upper_right_lung",
    "lower_right_lung",
    "pleural_region",
    "mediastinum",
}


def _phantom(
    size: int = 256,
    *,
    lung_top: float = 0.20,
    lung_bottom: float = 0.70,
    left_x: tuple = (0.12, 0.40),
    right_x: tuple = (0.58, 0.86),
) -> np.ndarray:
    """흉부 X-ray 를 아주 거칠게 흉내낸 결정론적 팬텀.

    - 배경/연부조직: 중간 밝기
    - 폐야: 어두운 두 사각형(위치를 파라미터로 옮길 수 있다)
    - 종격동/척추: 가운데 밝은 세로 띠
    - 횡격막 아래: 밝은 복부
    난수를 쓰지 않는다 - 결정성 테스트가 팬텀 자체의 흔들림을 보지 않도록.
    """
    img = np.full((size, size), 0.60, dtype=np.float32)
    img[:, int(0.44 * size) : int(0.56 * size)] = 0.88
    y0, y1 = int(lung_top * size), int(lung_bottom * size)
    for x0, x1 in (left_x, right_x):
        img[y0:y1, int(x0 * size) : int(x1 * size)] = 0.16
    img[y1:, :] = 0.86
    yy, xx = np.mgrid[0:size, 0:size]
    img = img + 0.02 * np.sin(yy / 3.0) * np.cos(xx / 5.0)
    return np.clip(img, 0.0, 1.0).astype(np.float32)


def _rect_mask(size: int, y: tuple, x: tuple) -> np.ndarray:
    m = np.zeros((size, size), dtype=bool)
    m[int(y[0] * size) : int(y[1] * size), int(x[0] * size) : int(x[1] * size)] = True
    return m


def _iou(a: np.ndarray, b: np.ndarray) -> float:
    a = a.astype(bool)
    b = b.astype(bool)
    union = float((a | b).sum())
    return float((a & b).sum()) / union if union else 0.0


# ---------- 1) 영상 적응성 ----------
def test_masks_differ_when_lung_position_differs():
    """고정 타원이면 두 영상의 마스크가 완전히 같아진다 - 그때 이 테스트가 깨진다."""
    model = CVSegmentationROIModel()
    a = model.generate_masks(_phantom(left_x=(0.10, 0.34), right_x=(0.62, 0.88)))
    b = model.generate_masks(_phantom(left_x=(0.18, 0.42), right_x=(0.54, 0.80)))

    assert not np.array_equal(a["left_lung"], b["left_lung"])
    assert _iou(a["left_lung"], b["left_lung"]) < 0.90

    def cx(m):
        xs = np.nonzero(m)[1]
        return float(xs.mean())

    assert cx(a["left_lung"]) < cx(b["left_lung"]) - 2.0


def test_masks_follow_vertical_lung_extent():
    model = CVSegmentationROIModel()
    high = model.generate_masks(_phantom(lung_top=0.12, lung_bottom=0.55))
    low = model.generate_masks(_phantom(lung_top=0.30, lung_bottom=0.80))

    def cy(m):
        ys = np.nonzero(m)[0]
        return float(ys.mean())

    assert cy(high["full_lung"]) < cy(low["full_lung"]) - 5.0


# ---------- 2) 국소화 ----------
def test_lung_masks_land_on_the_dark_lung_fields():
    size = 256
    left_x, right_x = (0.12, 0.40), (0.58, 0.86)
    lung_y = (0.20, 0.70)
    model = CVSegmentationROIModel()
    masks = model.generate_masks(_phantom(size, left_x=left_x, right_x=right_x))

    truth_left = _rect_mask(size, lung_y, left_x)
    truth_right = _rect_mask(size, lung_y, right_x)

    for pred, truth in ((masks["left_lung"], truth_left), (masks["right_lung"], truth_right)):
        p = pred.astype(bool)
        assert p.sum() > 0
        recall = (p & truth).sum() / float(truth.sum())
        precision = (p & truth).sum() / float(p.sum())
        assert recall >= 0.60, f"recall={recall:.3f}"
        assert precision >= 0.60, f"precision={precision:.3f}"


def test_heart_is_not_placed_on_the_lung_fields():
    size = 256
    model = CVSegmentationROIModel()
    masks = model.generate_masks(_phantom(size))
    heart = masks["heart"].astype(bool)
    assert heart.sum() > 0
    truth_lungs = _rect_mask(size, (0.20, 0.70), (0.12, 0.40)) | _rect_mask(
        size, (0.20, 0.70), (0.58, 0.86)
    )
    overlap = (heart & truth_lungs).sum() / float(heart.sum())
    assert overlap < 0.15, f"heart overlaps lung fields: {overlap:.3f}"


# ---------- 3) 결정성 ----------
def test_deterministic_for_identical_input():
    img = _phantom()
    a = CVSegmentationROIModel().generate_masks(img)
    b = CVSegmentationROIModel().generate_masks(img.copy())
    assert set(a) == set(b)
    for k in a:
        assert np.array_equal(a[k], b[k]), f"{k} 가 호출마다 달라진다"


def test_deterministic_across_repeated_calls_on_same_instance():
    model = CVSegmentationROIModel()
    img = _phantom()
    first = model.generate_masks(img)
    for _ in range(3):
        again = model.generate_masks(img)
        for k in first:
            assert np.array_equal(first[k], again[k]), f"{k} 가 반복 호출에서 달라진다"


# ---------- 4) 계약 / 배타성 ----------
def test_returns_all_expected_keys_as_binary_uint8():
    masks = CVSegmentationROIModel().generate_masks(_phantom())
    assert EXPECTED_KEYS <= set(masks)
    for k, m in masks.items():
        assert m.dtype == np.uint8, k
        assert m.shape == (256, 256), k
        assert set(np.unique(m)) <= {0, 1}, k


def test_core_masks_are_non_empty():
    masks = CVSegmentationROIModel().generate_masks(_phantom())
    for k in ("full_lung", "left_lung", "right_lung", "heart", "pleural_region", "mediastinum"):
        assert masks[k].sum() > 0, f"{k} 가 비어 있다"


def test_left_and_right_lungs_are_disjoint():
    masks = CVSegmentationROIModel().generate_masks(_phantom())
    assert int((masks["left_lung"] & masks["right_lung"]).sum()) == 0


def test_heart_and_lungs_are_disjoint():
    masks = CVSegmentationROIModel().generate_masks(_phantom())
    assert int((masks["heart"] & masks["full_lung"]).sum()) == 0
    assert int((masks["heart"] & masks["mediastinum"]).sum()) == 0


def test_upper_lower_split_partitions_each_lung():
    masks = CVSegmentationROIModel().generate_masks(_phantom())
    for side in ("left", "right"):
        up = masks[f"upper_{side}_lung"]
        lo = masks[f"lower_{side}_lung"]
        whole = masks[f"{side}_lung"]
        assert int((up & lo).sum()) == 0
        assert np.array_equal((up | lo).astype(np.uint8), whole)
        assert up.sum() > 0 and lo.sum() > 0


def test_rejects_non_2d_input():
    with pytest.raises(ValueError):
        CVSegmentationROIModel().generate_masks(np.zeros((3, 16, 16), dtype=np.float32))


# ---------- 5) fallback 가시성 ----------
def _degenerate() -> np.ndarray:
    """폐야가 없는 입력(균일 영상). 분할이 성립할 수 없다."""
    return np.full((256, 256), 0.5, dtype=np.float32)


def test_falls_back_to_mock_masks_when_segmentation_finds_no_lung():
    model = CVSegmentationROIModel()
    img = _degenerate()
    masks = model.generate_masks(img)
    expected = MockROIModel().generate_masks(img)
    for k in EXPECTED_KEYS:
        assert np.array_equal(masks[k], expected[k]), f"{k} 가 mock fallback 결과와 다르다"


def test_fallback_is_visible_in_counter_and_source():
    model = CVSegmentationROIModel()
    assert model.fallback_count == 0
    assert model.last_source is None

    model.generate_masks(_phantom())
    assert model.fallback_count == 0
    assert model.last_source == "cv"

    model.generate_masks(_degenerate())
    assert model.fallback_count == 1
    assert model.last_source == "mock_fallback"


def test_fallback_logs_a_warning(caplog):
    """조용한 fallback 은 금지다. 되돌아갔으면 로그로 말해야 한다."""
    model = CVSegmentationROIModel()
    with caplog.at_level(logging.WARNING, logger="app.ml.cv_roi_model"):
        model.generate_masks(_degenerate())
    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert warnings, "fallback 이 일어났는데 WARNING 로그가 없다"
    assert any("mock" in r.getMessage().lower() for r in warnings)


def test_successful_segmentation_does_not_warn(caplog):
    model = CVSegmentationROIModel()
    with caplog.at_level(logging.WARNING, logger="app.ml.cv_roi_model"):
        model.generate_masks(_phantom())
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


# ---------- 빌더 계약 ----------
def test_builder_returns_model_or_none_never_a_disguised_mock():
    m = build_cv_roi_model()
    assert m is None or isinstance(m, CVSegmentationROIModel)


def test_builder_returns_none_when_scipy_is_unavailable(monkeypatch):
    monkeypatch.setattr("app.ml.cv_roi_model._scipy_available", lambda: False)
    assert build_cv_roi_model() is None


def test_model_declares_its_mask_version():
    assert CVSegmentationROIModel().version == "cv_lung_heart_v1"
    assert MockROIModel().version == "mock_ellipse_mask_v1"
