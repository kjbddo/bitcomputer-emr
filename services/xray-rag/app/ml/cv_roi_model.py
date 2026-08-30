"""영상 적응형 폐/심장 ROI 분할 (classical computer vision).

왜 이게 있는가
--------------
`MockROIModel` 은 `cy=0.55h, rx=0.42w` 같은 **고정 비율 타원**을 그린다. 입력
영상이 무엇이든 같은 마스크가 나온다. CheXpert 처럼 자세·확대율·collimation·
crop 이 제각각인 데이터에서는 그 타원이 해부학 위에 얹힌다는 보장이 없고, 그러면
ROI별 임베딩은 "폐의 reconstruction error" 가 아니라 "그 자리에 무엇이 있든 그것"
을 인코딩한다. EVALUATION.md §8.4 가 남긴 세 후보 중 첫 번째가 이것이다.

이 모듈은 그 후보를 시험하기 위한 것이다. **학습된 segmentation 모델이 아니다.**
외부 가중치를 들이는 것은 의존성·출처 결정이라 이 작업에서 하지 않는다. 대신
실제 픽셀 위에서 도는 고전적 CV 파이프라인을 쓴다:

  1) percentile contrast normalize + gaussian smoothing
  2) 영상 테두리에 붙어 있고 균일한 어두운 영역 = 배경/collimation 으로 보고 제거
  3) 종격동/척추가 만드는 **가장 밝은 세로 축**을 찾아 좌/우 반쪽을 나눈다
     (고정된 w//2 가 아니라 영상마다 다르다)
  4) 각 반쪽에서 밝기 분위수 임계로 어두운 폐야 후보를 뽑고, 면적 × 위치 사전확률
     로 하나를 고른 뒤 opening/closing/hole-fill 로 정리
  5) 두 폐 사이의 **빈틈(gap)** 을 세로 위치에 따라 종격동(위)과 심장(아래)으로 나눈다

의학적으로 정확한 분할이 아니다. 고정 타원보다 "실제 어두운 폐야 위에 얹힌다"는
것만 보장하려는 가설 검증용이다.

정직성 규약
----------
분할이 성립하지 않는 영상(균일 영상, 폐야를 못 찾은 경우)에서는 `MockROIModel`
로 되돌아간다. 되돌아갔다는 사실을 **숨기지 않는다** - WARNING 로그를 남기고
`fallback_count` / `last_source` 로 셀 수 있게 한다. 조용한 fallback 은 mock 을
real 처럼 보이게 만들고, 그건 이 저장소가 이미 한 번 배운 실수다
(app/ml/factory.py 의 engine_status 독스트링 참고).
"""
from __future__ import annotations

import logging
from typing import Dict, Optional, Tuple

import numpy as np

from app.ml.base import ROIMaskModel
from app.ml.mock_roi_model import MockROIModel

try:  # scipy 는 requirements 에 있지만, 없더라도 import 시점에 죽지 않는다.
    from scipy import ndimage as _ndi  # type: ignore
except Exception:  # pragma: no cover - 환경 의존
    _ndi = None  # type: ignore

logger = logging.getLogger(__name__)

# 튜닝 상수. 모두 "영상마다 계산되는 값"에 붙는 계수이지, 마스크 위치를 직접
# 정하는 좌표가 아니다 - 그게 mock 타원과의 차이다.
_SMOOTH_SIGMA = 2.0
_LUNG_QUANTILE = 35.0  # 반쪽 안에서 어두운 쪽 몇 %를 폐 후보로 볼지
_BG_DARK_MAX = 0.12  # 배경으로 볼 수 있는 최대 밝기(정규화 후)
_BG_STD_MAX = 0.06  # 배경은 평탄하다 - 어두워도 결이 있으면 폐다
_MIN_LUNG_AREA_FRAC = 0.008
_MAX_LUNG_AREA_FRAC = 0.40
_MIN_TOTAL_LUNG_FRAC = 0.02
_MAX_TOTAL_LUNG_FRAC = 0.60


def _scipy_available() -> bool:
    return _ndi is not None


class CVSegmentationROIModel:
    """영상 적응형 ROI 마스크 생성기.

    실패 시 주입된 fallback(기본 `MockROIModel`)으로 되돌아가되, 그 사실을 로그와
    카운터로 드러낸다.
    """

    version = "cv_lung_heart_v1"

    def __init__(self, fallback: Optional[ROIMaskModel] = None) -> None:
        self._fallback: ROIMaskModel = fallback if fallback is not None else MockROIModel()
        self.fallback_count: int = 0
        self.last_source: Optional[str] = None

    # ---------- public ----------
    def generate_masks(self, image: np.ndarray) -> Dict[str, np.ndarray]:
        if image.ndim != 2:
            raise ValueError(f"image must be [H,W], got {image.shape}")

        reason: Optional[str] = None
        masks: Optional[Dict[str, np.ndarray]] = None
        if not _scipy_available():
            reason = "scipy.ndimage 를 불러올 수 없다"
        else:
            try:
                masks, reason = self._segment(image.astype(np.float32))
            except Exception as exc:  # pragma: no cover - 방어적
                masks, reason = None, f"분할 중 예외: {exc!r}"

        if masks is None:
            self.fallback_count += 1
            self.last_source = "mock_fallback"
            logger.warning(
                "CV ROI 분할 실패(%s) - mock 타원 마스크로 fallback 한다 "
                "(누적 %d회). 이 케이스의 ROI 임베딩은 해부학과 무관하다.",
                reason or "원인 미상",
                self.fallback_count,
            )
            return self._fallback.generate_masks(image)

        self.last_source = "cv"
        return masks

    # ---------- 내부 ----------
    def _segment(self, image: np.ndarray) -> Tuple[Optional[Dict[str, np.ndarray]], Optional[str]]:
        h, w = image.shape
        x = _normalize(image)
        xs = _ndi.gaussian_filter(x, sigma=_SMOOTH_SIGMA)
        body = _body_mask(xs)
        spine = _spine_column(xs, body)

        left_region = np.zeros((h, w), dtype=bool)
        left_region[:, :spine] = True
        right_region = np.zeros((h, w), dtype=bool)
        right_region[:, spine:] = True

        left = _pick_lung(xs, body, left_region, (spine / w) * 0.5, h, w)
        right = _pick_lung(xs, body, right_region, (spine / w) + (1.0 - spine / w) * 0.5, h, w)
        if left is None or right is None:
            missing = "left" if left is None else "right"
            return None, f"{missing} 폐야 후보를 찾지 못했다"

        total = float((left | right).sum()) / float(h * w)
        if not (_MIN_TOTAL_LUNG_FRAC <= total <= _MAX_TOTAL_LUNG_FRAC):
            return None, f"폐야 면적 비율이 비현실적이다({total:.3f})"

        full = left | right
        heart, mediastinum = _mediastinal_split(left, right, body, h, w)
        if heart.sum() == 0:
            return None, "두 폐 사이의 심장/종격동 영역이 비었다"

        upper_left, lower_left = _split_by_own_extent(left)
        upper_right, lower_right = _split_by_own_extent(right)
        pleural = _inner_border_band(full, width=max(2, h // 64))

        out = {
            "full_lung": full,
            "left_lung": left,
            "right_lung": right,
            "heart": heart,
            "upper_left_lung": upper_left,
            "lower_left_lung": lower_left,
            "upper_right_lung": upper_right,
            "lower_right_lung": lower_right,
            "pleural_region": pleural,
            "mediastinum": mediastinum,
        }
        return {k: v.astype(np.uint8) for k, v in out.items()}, None


# ---------- 파이프라인 단계 ----------
def _normalize(img: np.ndarray) -> np.ndarray:
    """2~98 분위수로 대비를 편다. 장비/노출 차이를 흡수한다."""
    lo = float(np.percentile(img, 2))
    hi = float(np.percentile(img, 98))
    return np.clip((img - lo) / max(hi - lo, 1e-6), 0.0, 1.0).astype(np.float32)


def _body_mask(x: np.ndarray) -> np.ndarray:
    """배경/collimation 제거.

    "어둡다"만으로는 폐야와 배경을 못 가른다 - 과팽창된 폐는 배경만큼 어둡고,
    tight crop 에서는 테두리에 닿기까지 한다. 그래서 세 조건을 모두 요구한다:
    어둡고(_BG_DARK_MAX), 영상 테두리에 붙어 있고, **평탄하다**(_BG_STD_MAX).
    폐야에는 늑골/혈관 결이 있어 평탄하지 않다.
    """
    h, w = x.shape
    dark = x <= _BG_DARK_MAX
    labels, n = _ndi.label(dark)
    background = np.zeros_like(dark)
    if n:
        border_ids = (
            set(labels[0, :].tolist())
            | set(labels[-1, :].tolist())
            | set(labels[:, 0].tolist())
            | set(labels[:, -1].tolist())
        )
        border_ids.discard(0)
        for i in sorted(border_ids):
            comp = labels == i
            if comp.sum() < 0.004 * h * w:
                continue
            if float(x[comp].std()) <= _BG_STD_MAX:
                background |= comp
    body = _ndi.binary_fill_holes(~background)
    if body.sum() < 0.15 * h * w:  # 배경 판정이 폭주하면 차라리 쓰지 않는다
        body = np.ones_like(dark)
    return body


def _spine_column(x: np.ndarray, body: np.ndarray) -> int:
    """좌/우 폐를 가르는 세로 축 = 몸통 중앙에서 가장 밝은 열(척추/종격동).

    고정된 `w // 2` 와 달리 회전·off-center crop 을 따라간다.
    """
    h, w = x.shape
    y0, y1 = int(0.25 * h), int(0.75 * h)
    band = x[y0:y1, :]
    band_body = body[y0:y1, :]
    s = (band * band_body).sum(axis=0)
    c = band_body.sum(axis=0)
    col_mean = np.where(c > 0, s / np.maximum(c, 1), -1.0)
    lo, hi = int(0.32 * w), int(0.68 * w)
    return lo + int(np.argmax(col_mean[lo:hi]))


def _pick_lung(
    x: np.ndarray,
    body: np.ndarray,
    side: np.ndarray,
    cx_expect: float,
    h: int,
    w: int,
) -> Optional[np.ndarray]:
    """한쪽 반구에서 폐야 하나를 고른다.

    임계값은 **그 반쪽의 밝기 분포**에서 온다(고정 상수가 아니다). 후보 중에서는
    면적 × 위치 사전확률이 가장 큰 것을 고른다 - 팔/어깨/배경 얼룩이 면적만으로는
    폐를 이길 수 있기 때문이다.
    """
    values = x[body & side]
    if values.size < 100:
        return None
    threshold = float(np.percentile(values, _LUNG_QUANTILE))
    candidate = (x < threshold) & body & side
    candidate = _ndi.binary_opening(candidate, np.ones((5, 5), dtype=bool))

    labels, n = _ndi.label(candidate)
    if n == 0:
        return None

    frame = _frame_band(h, w, 0.05)
    best: Optional[np.ndarray] = None
    best_score = -1.0
    for i in range(1, n + 1):
        comp = labels == i
        area = float(comp.sum())
        if area < _MIN_LUNG_AREA_FRAC * h * w or area > _MAX_LUNG_AREA_FRAC * h * w:
            continue
        if (comp & frame).sum() / area > 0.35:  # 테두리에 눌러붙은 덩어리는 배경일 확률이 높다
            continue
        ys, xs = np.nonzero(comp)
        cy = float(ys.mean()) / h
        cx = float(xs.mean()) / w
        prior = float(np.exp(-(((cy - 0.43) / 0.24) ** 2 + ((cx - cx_expect) / 0.16) ** 2)))
        score = area * prior
        if score > best_score:
            best_score, best = score, comp

    if best is None:
        return None

    # 상단/측면 테두리에 흘러들어간 꼬리를 잘라내고 다시 최대 성분만 남긴다.
    best = best & ~_frame_band(h, w, 0.06, side_frac=0.03)
    labels2, n2 = _ndi.label(best)
    if n2 == 0:
        return None
    sizes = _ndi.sum(best, labels2, range(1, n2 + 1))
    best = labels2 == (int(np.argmax(sizes)) + 1)
    if best.sum() < _MIN_LUNG_AREA_FRAC * h * w:
        return None

    best = _ndi.binary_closing(best, np.ones((7, 7), dtype=bool))
    return _ndi.binary_fill_holes(best)


def _frame_band(h: int, w: int, top_frac: float, side_frac: Optional[float] = None) -> np.ndarray:
    tb = max(1, int(round(top_frac * h)))
    sb = max(1, int(round((side_frac if side_frac is not None else top_frac) * w)))
    band = np.zeros((h, w), dtype=bool)
    band[:tb, :] = True
    band[-tb:, :] = True
    band[:, :sb] = True
    band[:, -sb:] = True
    return band


def _mediastinal_split(
    left: np.ndarray, right: np.ndarray, body: np.ndarray, h: int, w: int
) -> Tuple[np.ndarray, np.ndarray]:
    """두 폐 사이의 빈틈을 종격동(위)과 심장(아래)으로 나눈다.

    심장은 "정해진 자리에 있는 타원"이 아니라 **폐가 비켜난 자리**다. 행마다 좌폐의
    안쪽 끝과 우폐의 안쪽 끝 사이를 gap 으로 잡고, 폐 영역의 아래쪽 절반에서 gap 이
    중앙값보다 넓어지는 구간을 심장 실루엣으로 본다.
    """
    full = left | right
    rows = np.nonzero(full.any(axis=1))[0]
    gap = np.zeros((h, w), dtype=bool)
    if rows.size == 0:
        return gap, gap
    y0, y1 = int(rows[0]), int(rows[-1])

    left_cols = np.nonzero(left.any(axis=0))[0]
    right_cols = np.nonzero(right.any(axis=0))[0]
    default_l = int(left_cols[-1]) if left_cols.size else 0
    default_r = int(right_cols[0]) if right_cols.size else w - 1

    widths = np.zeros(h, dtype=np.int32)
    for y in range(y0, y1 + 1):
        lrow = np.nonzero(left[y])[0]
        rrow = np.nonzero(right[y])[0]
        a = int(lrow[-1]) + 1 if lrow.size else default_l + 1
        b = int(rrow[0]) if rrow.size else default_r
        if b > a:
            gap[y, a:b] = True
            widths[y] = b - a
    gap &= body
    if not gap.any():
        return np.zeros((h, w), dtype=bool), np.zeros((h, w), dtype=bool)

    lower_start = y0 + int(round(0.45 * (y1 - y0)))
    nonzero_w = widths[y0 : y1 + 1]
    nonzero_w = nonzero_w[nonzero_w > 0]
    median_w = float(np.median(nonzero_w)) if nonzero_w.size else 0.0

    heart_rows = np.zeros(h, dtype=bool)
    wide = [y for y in range(lower_start, y1 + 1) if widths[y] >= median_w and widths[y] > 0]
    if wide:
        # 가장 넓은 행을 포함하는 연속 구간만 심장으로 본다.
        peak = max(wide, key=lambda y: widths[y])
        y = peak
        while y >= lower_start and widths[y] >= median_w and widths[y] > 0:
            heart_rows[y] = True
            y -= 1
        y = peak + 1
        while y <= y1 and widths[y] >= median_w and widths[y] > 0:
            heart_rows[y] = True
            y += 1
    else:
        heart_rows[lower_start : y1 + 1] = True

    heart = gap & heart_rows[:, None]
    mediastinum = gap & ~heart_rows[:, None]

    if heart.any():
        labels, n = _ndi.label(heart)
        if n > 1:
            sizes = _ndi.sum(heart, labels, range(1, n + 1))
            heart = labels == (int(np.argmax(sizes)) + 1)
        heart = _ndi.binary_fill_holes(heart)
    return heart, mediastinum


def _split_by_own_extent(mask: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """각 폐를 **자기 자신의 세로 범위** 중앙에서 상/하로 나눈다.

    영상 전체의 `h // 2` 로 자르면 폐가 위쪽에 몰린 영상에서 아래쪽 ROI 가 비어버린다.
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


def _inner_border_band(mask: np.ndarray, width: int = 3) -> np.ndarray:
    """폐야 안쪽 테두리 띠(흉막/늑횡격막각 근처). mock 과 같은 정의를 유지한다."""
    eroded = _ndi.binary_erosion(mask, np.ones((3, 3), dtype=bool), iterations=max(1, width))
    return mask & ~eroded


# ---------- 빌더 ----------
def build_cv_roi_model() -> Optional[CVSegmentationROIModel]:
    """어댑터를 만들 수 있으면 만들고, 못 만들면 None.

    `build_torch_anomaly_model` / `build_torch_embedding_model` 과 같은 계약이다 -
    **절대 mock 을 real 인 척 돌려주지 않는다.** None 을 받은 factory 가 mock 으로
    fallback 하고 그 사실을 `roi_is_real=False` 로 기록한다.
    """
    if not _scipy_available():
        logger.warning("scipy.ndimage 가 없어 CV ROI 어댑터를 만들 수 없다 - mock 으로 간다")
        return None
    return CVSegmentationROIModel()
