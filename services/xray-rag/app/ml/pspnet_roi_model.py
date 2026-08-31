"""사전학습 해부학 분할(ChestX-Det PSPNet)을 쓰는 ROI 마스크 어댑터.

왜 이게 있는가
--------------
`MockROIModel` 은 고정 타원이고, `CVSegmentationROIModel`(EVALUATION.md §9)은 그
타원을 대체하려고 직접 쓴 고전 CV 파이프라인이다. 후자는 "ROI 정합성이 병목인가"를
시험하기 위한 도구였고 그 가설은 기각됐지만, 분할 품질 자체는 거칠었다 — 표본 12건
중 2~3건이 팔/어깨를 물거나 폐야를 덜 잡았다.

직접 쓴 휴리스틱 대신 **이 일을 실제로 하는 방식**을 쓴다. TorchXRayVision 이 배포하는
ChestX-Det PSPNet 은 흉부 정면 X-ray 에서 14개 해부 구조를 분할하고, 그 중
Left Lung / Right Lung / Heart / Mediastinum 이 이 서비스가 쓰는 ROI 집합과 그대로
겹친다.

    Lian J, Liu J, Zhang S, et al. "A Structure-Aware Relation Network for
    Thoracic Diseases Detection and Segmentation." IEEE TMI, 2021.
    doi:10.48550/arxiv.2104.10326
    데이터셋/모델 출처: https://github.com/Deepwise-AILab/ChestX-Det-Dataset

라이선스(직접 확인한 것)
-----------------------
- `torchxrayvision` 패키지: Apache-2.0(배포 메타데이터의 OSI classifier). 다만
  동봉된 LICENSE 파일은 "Licenses vary by subpackage ... Baseline models (check
  each model's license)" 라고 명시한다. 즉 라이브러리 라이선스가 baseline 모델까지
  덮지 않는다.
- 이 모델의 상류인 `Deepwise-AILab/ChestX-Det-Dataset` 저장소는 **Apache-2.0** 이다
  (LICENSE 파일이 Apache 2.0 전문).
- `torchxrayvision.baseline_models.chestx_det` 모듈에는 사용 제한 문구가 없다.
  같은 패키지의 `chestx_anatomy`(CXAS UNetResNet50, 159 구조)에는
  "Creative Commons Attribution-NonCommercial-ShareAlike" 가 명시돼 있다 —
  **비상업 조건이라 쓰지 않는다.** 제한이 있는 모델에는 문구가 붙어 있고 이 모델에는
  없다는 점이 위 판단의 근거다.
- PSPNet 구현 코드(`ptsemseg/`)는 meetshah1995/pytorch-semseg(MIT) 유래다.

이 모듈이 지키는 규약
--------------------
**좌/우 명명.** 이 저장소의 `left_lung` 은 *영상의 왼쪽* 이다 — mock 타원
(`left[:, w//2:] = 0`)과 cv 분할(`left_region[:, :spine]`) 둘 다 그렇게 만든다.
흉부 정면 영상에서 영상의 왼쪽은 **환자의 오른쪽**이므로, 이 이름은 해부학적으로는
틀렸다. 그런데 PSPNet 은 해부학 이름(`Left Lung` = 환자의 왼쪽)을 쓴다. 여기서
채널을 이름 그대로 받으면 `left_lung` 필드가 세대마다 다른 폐를 가리키게 된다 —
`roiMaskVersion` 을 보기 전에는 어느 쪽인지 알 수 없는 상태가 된다.

그래서 **매핑을 교차시킨다**: PSPNet `Right Lung` → 우리 `left_lung`,
PSPNet `Left Lung` → 우리 `right_lung`. 필드 이름의 의미(영상 기준)를 세 어댑터에서
동일하게 유지한다. 필드를 해부학 기준으로 개명하는 것은 DB 필드·Java DTO·웹까지
가는 별개 변경이고, 이 작업의 범위가 아니다.

**정직한 fallback.** `build_pspnet_roi_model()` 은 실패하면 `None` 을 돌려준다 —
`build_torch_*` / `build_cv_roi_model` 과 같은 계약이고, **mock 을 real 인 척
돌려주지 않는다.** 케이스별로 분할이 성립하지 않으면 주입된 fallback(기본은 cv,
cv 도 없으면 mock)으로 되돌아가되 WARNING 로그와 `fallback_count` / `last_source`
로 드러낸다.

**다운로드를 기본으로 하지 않는다.** 가중치는 273MB 이고 `~/.torchxrayvision/
models_data/` 에 캐시된다. 운영 컨테이너에는 egress 가 없으므로 여기서 다운로드를
시도하면 기동이 네트워크 타임아웃만큼 멈춘다. 파일이 이미 있을 때만 올리고, 없으면
즉시 `None` 을 돌려 factory 가 다음 후보로 내려가게 한다. 호스트에서 한 번 받아두는
것은 `scripts/fetch_pspnet_weights.py` 가 한다.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional, Tuple

import numpy as np

from app.ml.base import ROIMaskModel
from app.ml.mock_roi_model import MockROIModel, _border_band

logger = logging.getLogger(__name__)

# torchxrayvision 이 배포하는 ChestX-Det PSPNet 의 채널 순서. 어댑터가 채널을
# **이름으로** 찾도록 여기 복제해 둔다 - 상류가 순서를 바꿔도 조용히 엉뚱한 채널을
# 읽지 않게 하려는 것이다(실제 조회는 segmenter.targets 를 쓴다).
PSPNET_TARGETS: Tuple[str, ...] = (
    "Left Clavicle",
    "Right Clavicle",
    "Left Scapula",
    "Right Scapula",
    "Left Lung",
    "Right Lung",
    "Left Hilus Pulmonis",
    "Right Hilus Pulmonis",
    "Heart",
    "Aorta",
    "Facies Diaphragmatica",
    "Mediastinum",
    "Weasand",
    "Spine",
)

PSPNET_WEIGHTS_FILENAME = "pspnet_chestxray_best_model_4.pth"

# xrv 모델은 [-1024, 1024] 스케일 입력을 기대한다(xrv.datasets.normalize 규약).
# 우리 error map 은 [0, 1] 이므로 여기서 늘린다. 이걸 빠뜨리면 모델이 전 화면을
# 배경으로 보고 빈 마스크를 내고, fallback 만 계속 뜬다.
_XRV_SCALE = 1024.0

_PROB_THRESHOLD = 0.5
# 폐 하나가 이보다 작으면 분할 실패로 본다. cv 어댑터의 _MIN_LUNG_AREA_FRAC 과 같은
# 기준을 쓴다 - 두 어댑터가 "성립했다"를 서로 다르게 판정하면 fallback 통계를
# 비교할 수 없다.
_MIN_LUNG_AREA_FRAC = 0.008


class PSPNetROIModel:
    """ChestX-Det PSPNet 출력에서 이 서비스의 ROI 마스크 dict 를 만든다.

    `segmenter` 는 `targets` 속성(채널 이름 목록)을 갖고 `[1, 1, H, W]` 텐서를 받아
    `[1, C, 512, 512]` 로짓을 돌려주는 호출 가능 객체면 된다. 실제 모델을 넣지 않고도
    매핑 규약을 테스트할 수 있도록 주입식으로 뒀다.
    """

    version = "pspnet_chestxdet_v1"

    def __init__(
        self,
        segmenter: Any,
        *,
        fallback: Optional[ROIMaskModel] = None,
        threshold: float = _PROB_THRESHOLD,
    ) -> None:
        self._segmenter = segmenter
        self._fallback: ROIMaskModel = fallback if fallback is not None else MockROIModel()
        self._threshold = threshold
        self.fallback_count: int = 0
        self.last_source: Optional[str] = None

    # ---------- public ----------
    def generate_masks(self, image: np.ndarray) -> Dict[str, np.ndarray]:
        if image.ndim != 2:
            raise ValueError(f"image must be [H,W], got {image.shape}")

        try:
            masks, reason = self._segment(image)
        except Exception as exc:  # 분할 실패가 파이프라인 전체를 죽이지 않는다
            masks, reason = None, f"분할 중 예외: {exc!r}"

        if masks is None:
            self.fallback_count += 1
            self.last_source = "fallback"
            logger.warning(
                "PSPNet ROI 분할 실패(%s) - fallback 어댑터(%s)로 되돌아간다 "
                "(누적 %d회). 이 케이스의 ROI 임베딩은 PSPNet 분할에서 나온 것이 "
                "아니다.",
                reason or "원인 미상",
                type(self._fallback).__name__,
                self.fallback_count,
            )
            return self._fallback.generate_masks(image)

        self.last_source = "pspnet"
        return masks

    # ---------- 내부 ----------
    def _segment(self, image: np.ndarray) -> Tuple[Optional[Dict[str, np.ndarray]], Optional[str]]:
        import torch

        h, w = image.shape
        x = np.clip(image.astype(np.float32), 0.0, 1.0)
        # [0,1] -> [-1024, 1024]
        x = x * (2.0 * _XRV_SCALE) - _XRV_SCALE
        tensor = torch.from_numpy(np.ascontiguousarray(x)).unsqueeze(0).unsqueeze(0)

        with torch.no_grad():
            logits = self._segmenter(tensor)
            prob = torch.sigmoid(logits.float())
            # 구조들은 서로 겹칠 수 있으므로 채널 간 softmax 가 아니라 채널별 임계.
            binary = (prob >= self._threshold).to(torch.float32)
            resized = torch.nn.functional.interpolate(
                binary, size=(h, w), mode="nearest"
            )[0].cpu().numpy()

        targets = list(getattr(self._segmenter, "targets", PSPNET_TARGETS))

        def channel(name: str) -> np.ndarray:
            try:
                i = targets.index(name)
            except ValueError:
                return np.zeros((h, w), dtype=bool)
            return resized[i] > 0.5

        # 좌/우 교차 매핑. 모듈 독스트링의 "좌/우 명명" 참고.
        left_lung = channel("Right Lung")   # 환자의 오른쪽 = 영상의 왼쪽
        right_lung = channel("Left Lung")   # 환자의 왼쪽  = 영상의 오른쪽
        heart = channel("Heart")
        mediastinum = channel("Mediastinum")

        min_area = _MIN_LUNG_AREA_FRAC * h * w
        if left_lung.sum() < min_area or right_lung.sum() < min_area:
            missing = "left" if left_lung.sum() < min_area else "right"
            return None, (
                f"{missing} 폐 마스크가 비었거나 너무 작다"
                f"(left={int(left_lung.sum())}, right={int(right_lung.sum())}, "
                f"최소={int(min_area)})"
            )
        if heart.sum() == 0:
            # cv 어댑터와 같은 판정 기준이다("두 폐 사이의 심장/종격동 영역이
            # 비었다"). 심장 마스크가 전부 0 이면 heartErrorEmbedding 이 아무것도
            # 아닌 벡터가 되는데 roi_status 는 여전히 pspnet 이라고 말한다.
            # 실제로 측면 영상에서 이 경로가 뜬다 - 이 모델은 정면 학습이다.
            return None, "심장 마스크가 비었다(정면 영상이 아닐 가능성)"

        # mock/cv 와 같은 성질을 유지한다 - 폐야가 심장을 삼키지 않는다.
        left_lung = left_lung & ~heart
        right_lung = right_lung & ~heart
        full_lung = left_lung | right_lung

        upper_left, lower_left = _split_by_own_extent(left_lung)
        upper_right, lower_right = _split_by_own_extent(right_lung)
        pleural = _border_band(full_lung.astype(np.uint8), width=max(2, h // 64)).astype(bool)

        out = {
            "full_lung": full_lung,
            "left_lung": left_lung,
            "right_lung": right_lung,
            "heart": heart,
            "upper_left_lung": upper_left,
            "lower_left_lung": lower_left,
            "upper_right_lung": upper_right,
            "lower_right_lung": lower_right,
            "pleural_region": pleural,
            "mediastinum": mediastinum,
        }
        return {k: v.astype(np.uint8) for k, v in out.items()}, None


def _split_by_own_extent(mask: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """각 폐를 **자기 자신의 세로 범위** 중앙에서 상/하로 나눈다.

    `cv_roi_model` 과 같은 정의다. 영상 전체의 `h // 2` 로 자르면 폐가 위쪽에 몰린
    영상에서 아래쪽 ROI 가 비어버린다.
    """
    rows = np.nonzero(mask.any(axis=1))[0]
    upper = np.zeros_like(mask)
    lower = np.zeros_like(mask)
    if rows.size == 0:
        return upper, lower
    mid = int(rows[0]) + max(1, (int(rows[-1]) - int(rows[0]) + 1) // 2)
    upper[:mid, :] = mask[:mid, :]
    lower[mid:, :] = mask[mid:, :]
    return upper, lower


# ---------- 빌더 ----------
def _default_cache_dir() -> str:
    try:
        from torchxrayvision.utils import get_cache_dir

        return str(get_cache_dir())
    except Exception:
        return os.path.expanduser(os.path.join("~", ".torchxrayvision", "models_data"))


def _construct_pspnet(cache_dir: str) -> Any:
    """실제 모델 생성. 테스트가 "네트워크를 건드리지 않는다"를 검증할 수 있도록
    별도 함수로 뺐다."""
    import torchxrayvision as xrv

    return xrv.baseline_models.chestx_det.PSPNet(cache_dir=cache_dir)


def weights_path(cache_dir: Optional[str] = None) -> str:
    return os.path.join(cache_dir or _default_cache_dir(), PSPNET_WEIGHTS_FILENAME)


def build_pspnet_roi_model(
    cache_dir: Optional[str] = None,
    allow_download: bool = False,
) -> Optional[PSPNetROIModel]:
    """어댑터를 만들 수 있으면 만들고, 못 만들면 `None`.

    `build_torch_anomaly_model` / `build_cv_roi_model` 과 같은 계약이다 - **절대
    mock 을 real 인 척 돌려주지 않는다.** `None` 을 받은 factory 가 다음 후보(cv)로
    내려가고, 그 사실이 `roi_status` 에 남는다.
    """
    path = weights_path(cache_dir)
    if not os.path.isfile(path) and not allow_download:
        logger.warning(
            "PSPNet ROI 어댑터를 만들 수 없다 - 가중치 %s 가 %s 에 없다. "
            "이 컨테이너/호스트에는 다운로드를 허용하지 않았다"
            "(PSPNET_ALLOW_DOWNLOAD=false). 호스트에서 "
            "`python scripts/fetch_pspnet_weights.py` 로 한 번 받아두고, 컨테이너에는 "
            "그 디렉터리를 마운트한다. 지금은 다음 ROI 후보(cv)로 내려간다.",
            PSPNET_WEIGHTS_FILENAME,
            os.path.dirname(path),
        )
        return None

    try:
        segmenter = _construct_pspnet(cache_dir or _default_cache_dir())
    except Exception as exc:
        logger.warning(
            "PSPNet 로드 실패(%r) - 다음 ROI 후보(cv)로 내려간다. mock 을 real 인 척 "
            "돌려주지 않는다.",
            exc,
        )
        return None

    fallback: ROIMaskModel
    try:
        from app.ml.cv_roi_model import build_cv_roi_model

        fallback = build_cv_roi_model() or MockROIModel()
    except Exception:  # pragma: no cover - 방어적
        fallback = MockROIModel()

    return PSPNetROIModel(segmenter=segmenter, fallback=fallback)
