"""ChestX-Det PSPNet ROI 어댑터.

`app/ml/cv_roi_model.py` 는 ROI 정합성이 병목인지 시험하려고 직접 쓴 고전 CV
파이프라인이었다(EVALUATION.md §9). 가설은 기각됐지만 분할 자체의 품질도 거칠었다.
그 자리를 **사전학습된 해부학 분할 모델**로 바꾼다 — TorchXRayVision 이 배포하는
ChestX-Det PSPNet 이고, 14개 구조 중 Left Lung / Right Lung / Heart / Mediastinum 이
이 서비스가 이미 쓰는 ROI 집합과 그대로 겹친다.

이 파일이 지키는 것
------------------
1. **좌/우 명명 규약.** 이 저장소의 `left_lung` 은 *영상의 왼쪽* 이다(mock 타원과
   cv 분할 둘 다 그렇게 만든다). PSPNet 의 `Left Lung` 은 *환자의 왼쪽* 이고,
   흉부 정면 영상에서 그것은 **영상의 오른쪽**에 온다. 그래서 채널 매핑이
   교차한다 - PSPNet `Right Lung` → 우리 `left_lung`. 이 규약을 뒤집으면 같은
   필드 이름이 세대마다 다른 폐를 가리키게 된다.
2. **정직한 fallback.** 가중치가 없으면 빌더가 `None` 을 돌려준다(mock 을 real 인
   척 돌려주지 않는다). 케이스별로 분할이 비면 주입된 fallback 으로 되돌아가되
   WARNING 로그와 `fallback_count` / `last_source` 로 드러낸다.
"""
from __future__ import annotations

import logging

import numpy as np
import pytest
import torch

from app.ml.mock_roi_model import MockROIModel
from app.ml.pspnet_roi_model import (
    PSPNET_TARGETS,
    PSPNET_WEIGHTS_FILENAME,
    PSPNetROIModel,
    build_pspnet_roi_model,
)

_REQUIRED_KEYS = {
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


class _FakeSegmenter:
    """PSPNet 대역. 채널 이름 → 512x512 이진 마스크를 받아 로짓으로 돌려준다."""

    targets = list(PSPNET_TARGETS)

    def __init__(self, active):
        self.active = active
        self.seen_shapes = []
        self.seen_ranges = []

    def __call__(self, x):
        self.seen_shapes.append(tuple(x.shape))
        self.seen_ranges.append((float(x.min()), float(x.max())))
        out = torch.full((1, len(self.targets), 512, 512), -10.0, dtype=torch.float32)
        for name, mask in self.active.items():
            i = self.targets.index(name)
            out[0, i] = torch.from_numpy(mask.astype(np.float32)) * 20.0 - 10.0
        return out


def _block(y0, y1, x0, x1) -> np.ndarray:
    m = np.zeros((512, 512), dtype=np.float32)
    m[y0:y1, x0:x1] = 1.0
    return m


def _anatomical_case():
    """해부학적으로 맞는 배치. 환자 좌폐가 영상 오른쪽에 온다."""
    return {
        # 환자의 오른쪽 폐 = 영상 왼쪽
        "Right Lung": _block(100, 400, 60, 220),
        # 환자의 왼쪽 폐 = 영상 오른쪽
        "Left Lung": _block(100, 400, 292, 452),
        "Heart": _block(280, 400, 230, 300),
        "Mediastinum": _block(100, 280, 235, 285),
    }


def _model(active=None, fallback=None):
    return PSPNetROIModel(
        segmenter=_FakeSegmenter(_anatomical_case() if active is None else active),
        fallback=fallback if fallback is not None else MockROIModel(),
    )


# ---------- 명명 규약 ----------

def test_left_lung_field_comes_from_pspnet_right_lung_channel():
    """이 저장소의 `left_lung` = 영상의 왼쪽 = PSPNet 의 `Right Lung`.

    매핑을 곧이곧대로(`Left Lung` → `left_lung`) 하면 같은 필드가 mock/cv 세대와
    다른 폐를 가리키게 된다. 이 테스트가 그 교차를 못박는다.
    """
    masks = _model().generate_masks(np.zeros((256, 256), dtype=np.float32))

    left = masks["left_lung"]
    right = masks["right_lung"]

    # 영상을 반으로 갈랐을 때 각 마스크가 어느 쪽에 있는지로 검증한다.
    half = left.shape[1] // 2
    assert left[:, :half].sum() > 0 and left[:, half:].sum() == 0
    assert right[:, half:].sum() > 0 and right[:, :half].sum() == 0


def test_heart_and_mediastinum_come_from_their_own_channels():
    masks = _model().generate_masks(np.zeros((256, 256), dtype=np.float32))

    assert masks["heart"].sum() > 0
    assert masks["mediastinum"].sum() > 0
    # 종격동은 심장보다 위에 있다(_anatomical_case 배치 그대로).
    heart_rows = np.nonzero(masks["heart"].any(axis=1))[0]
    med_rows = np.nonzero(masks["mediastinum"].any(axis=1))[0]
    assert med_rows.mean() < heart_rows.mean()


def test_all_required_roi_keys_are_present_and_binary_at_input_resolution():
    masks = _model().generate_masks(np.zeros((160, 224), dtype=np.float32))

    assert _REQUIRED_KEYS <= set(masks)
    for name, m in masks.items():
        assert m.shape == (160, 224), name
        assert m.dtype == np.uint8, name
        assert set(np.unique(m)) <= {0, 1}, name


def test_lungs_do_not_swallow_the_heart():
    """`full_lung` 에서 심장을 뺀다 - mock/cv 어댑터와 같은 성질."""
    overlapping = _anatomical_case()
    overlapping["Right Lung"] = _block(100, 400, 60, 300)  # 심장 위로 겹치게
    masks = _model(active=overlapping).generate_masks(np.zeros((256, 256), dtype=np.float32))

    assert (masks["full_lung"] & masks["heart"]).sum() == 0


def test_model_declares_its_mask_version():
    assert PSPNetROIModel.version == "pspnet_chestxdet_v1"


def test_input_is_rescaled_to_the_xrv_range():
    """xrv 모델은 [-1024, 1024] 를 기대한다. error map 은 [0, 1] 이다.

    스케일을 안 맞추면 모델이 전부 배경으로 보고 조용히 빈 마스크를 낸다 -
    fallback 은 뜨지만 분할은 한 번도 성공하지 못한다.
    """
    seg = _FakeSegmenter(_anatomical_case())
    model = PSPNetROIModel(segmenter=seg, fallback=MockROIModel())

    image = np.stack([np.zeros(256), np.ones(256)] * 128).astype(np.float32)
    model.generate_masks(image)

    assert seg.seen_shapes == [(1, 1, 256, 256)]
    lo, hi = seg.seen_ranges[0]
    assert lo == pytest.approx(-1024.0)
    assert hi == pytest.approx(1024.0)


# ---------- 정직한 fallback ----------

def test_empty_segmentation_falls_back_loudly(caplog):
    """분할이 비면 fallback 하되 **조용히 하지 않는다.**"""
    fallback = MockROIModel()
    model = PSPNetROIModel(segmenter=_FakeSegmenter({}), fallback=fallback)

    with caplog.at_level(logging.WARNING):
        masks = model.generate_masks(np.zeros((256, 256), dtype=np.float32))

    assert model.fallback_count == 1
    assert model.last_source == "fallback"
    assert any(r.levelno >= logging.WARNING for r in caplog.records), (
        "fallback 이 WARNING 로그를 남기지 않았다 - 조용한 fallback 은 mock 을 "
        "real 처럼 보이게 만든다"
    )
    # 실제로 fallback 결과가 나왔는지
    assert masks.keys() == fallback.generate_masks(np.zeros((256, 256))).keys()


def test_successful_segmentation_does_not_count_as_fallback():
    model = _model()
    model.generate_masks(np.zeros((256, 256), dtype=np.float32))

    assert model.fallback_count == 0
    assert model.last_source == "pspnet"


def test_single_lung_only_is_treated_as_failure():
    """한쪽 폐만 나온 분할은 성공으로 치지 않는다 - ROI별 임베딩이 반쪽이 된다."""
    only_left = {"Right Lung": _block(100, 400, 60, 220)}
    model = _model(active=only_left)

    model.generate_masks(np.zeros((256, 256), dtype=np.float32))

    assert model.fallback_count == 1


def test_segmenter_exception_falls_back_instead_of_crashing(caplog):
    class _Boom:
        targets = list(PSPNET_TARGETS)

        def __call__(self, x):
            raise RuntimeError("boom")

    model = PSPNetROIModel(segmenter=_Boom(), fallback=MockROIModel())
    with caplog.at_level(logging.WARNING):
        masks = model.generate_masks(np.zeros((64, 64), dtype=np.float32))

    assert model.fallback_count == 1
    assert masks["full_lung"].shape == (64, 64)


def test_rejects_non_2d_input():
    with pytest.raises(ValueError):
        _model().generate_masks(np.zeros((3, 64, 64), dtype=np.float32))


# ---------- 빌더 계약 ----------

def test_builder_returns_none_when_weights_are_missing(tmp_path, caplog):
    """가중치가 없으면 **None** 이다. mock 을 real 인 척 돌려주지 않는다.

    컨테이너에는 egress 가 없다. 여기서 다운로드를 시도하면 기동이 멈추므로,
    파일이 없고 다운로드가 허용되지 않았으면 즉시 포기하고 factory 가 다음
    후보(cv)로 내려가게 한다.
    """
    with caplog.at_level(logging.WARNING):
        built = build_pspnet_roi_model(cache_dir=str(tmp_path), allow_download=False)

    assert built is None
    joined = " ".join(r.getMessage() for r in caplog.records)
    assert PSPNET_WEIGHTS_FILENAME in joined, (
        "실패 로그가 어떤 파일이 없어서 실패했는지 말해주지 않는다"
    )


def test_builder_does_not_download_when_not_allowed(tmp_path, monkeypatch):
    """`allow_download=False` 면 네트워크를 건드리지 않는다."""
    called = []

    def _boom(*a, **k):
        called.append(a)
        raise AssertionError("allow_download=False 인데 PSPNet 생성자를 호출했다")

    monkeypatch.setattr(
        "app.ml.pspnet_roi_model._construct_pspnet", _boom, raising=False
    )
    assert build_pspnet_roi_model(cache_dir=str(tmp_path), allow_download=False) is None
    assert not called


def test_empty_heart_is_treated_as_failure():
    """심장 채널이 비면 성공으로 치지 않는다.

    `heartErrorEmbedding` 은 심장 마스크로 가린 error map 에서 나온다. 마스크가
    전부 0 이면 그 벡터는 "심장 영역의 오차"가 아니라 아무것도 아니게 되는데,
    `roi_status` 는 여전히 pspnet 이라고 말한다. cv 어댑터도 같은 조건에서
    실패로 판정한다("두 폐 사이의 심장/종격동 영역이 비었다") - 두 어댑터가
    "성립했다"를 다르게 판정하면 fallback 통계를 비교할 수 없다.

    실제로 측면(lateral) 영상에서 이 경로가 뜬다 - 이 모델은 정면 학습이다.
    """
    lungs_only = {
        "Right Lung": _block(100, 400, 60, 220),
        "Left Lung": _block(100, 400, 292, 452),
    }
    model = _model(active=lungs_only)

    model.generate_masks(np.zeros((256, 256), dtype=np.float32))

    assert model.fallback_count == 1
    assert model.last_source == "fallback"
