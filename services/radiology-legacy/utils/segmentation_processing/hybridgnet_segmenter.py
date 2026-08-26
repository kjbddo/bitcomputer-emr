from __future__ import annotations

import sys
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import cv2
import numpy as np
import torch

# HybridGNet의 InstanceNorm1d 경고 억제
warnings.filterwarnings('ignore', category=UserWarning, module='torch.nn.modules.instancenorm')

# CheXmask repository lives inside the project tree. We dynamically append its
# HybridGNet module path so we can reuse the original models without copying
# files around.
# __file__은 anomaly_squid/utils/segmentation_processing/hybridgnet_segmenter.py
# parents[1] = utils/ 디렉토리
CHEXMASK_ROOT = (Path(__file__).resolve().parents[1] / "CheXmask-Database-main").resolve()
HYBRIDGNET_DIR = CHEXMASK_ROOT / "HybridGNet"

# 경로 존재 확인
if not CHEXMASK_ROOT.exists():
    raise FileNotFoundError(f"CheXmask-Database-main not found at: {CHEXMASK_ROOT}\n"
                           f"Current file: {__file__}\n"
                           f"Parent dirs: {[str(p) for p in Path(__file__).resolve().parents]}")
if not HYBRIDGNET_DIR.exists():
    raise FileNotFoundError(f"HybridGNet directory not found at: {HYBRIDGNET_DIR}\n"
                           f"CheXmask_ROOT: {CHEXMASK_ROOT}")

# seg_models와 hybridgnet_utils 디렉토리 존재 확인
SEG_MODELS_DIR = HYBRIDGNET_DIR / "seg_models"
UTILS_DIR = HYBRIDGNET_DIR / "hybridgnet_utils"
if not SEG_MODELS_DIR.exists():
    raise FileNotFoundError(f"seg_models directory not found at: {SEG_MODELS_DIR}")
if not UTILS_DIR.exists():
    raise FileNotFoundError(f"hybridgnet_utils directory not found at: {UTILS_DIR}")

# HybridGNet 디렉토리를 sys.path에 추가 (이 디렉토리가 Python 패키지 루트가 됨)
hybridgnet_path = str(HYBRIDGNET_DIR.resolve())
if hybridgnet_path not in sys.path:
    sys.path.insert(0, hybridgnet_path)

# Import modules
# Note: seg_models와 hybridgnet_utils 디렉토리에 __init__.py 파일이 필요합니다.
from seg_models.HybridGNet2IGSC import Hybrid  # type: ignore  # noqa: E402
from hybridgnet_utils.utils import (  # type: ignore  # noqa: E402
    genMatrixesLungsHeart,
    scipy_to_torch_sparse,
)

import scipy.sparse as sp  # noqa: E402


def _ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _normalize_rel_path(rel_path: str) -> Path:
    """
    Normalise CheXpert relative paths so that `CheXpert-v1.0-small/...` and raw
    `train/...` references resolve to the same location.
    """
    rel_path = rel_path.strip().replace("\\", "/")
    if "CheXpert-v1.0-small/" in rel_path:
        rel_path = rel_path.split("CheXpert-v1.0-small/")[-1]
    # Trim leading slashes if present
    rel_path = rel_path.lstrip("/")
    return Path(rel_path)


def _dense_mask_from_landmarks(rl: np.ndarray, ll: np.ndarray, heart: np.ndarray) -> np.ndarray:
    """Re-implement CheXmask's dense mask construction for clarity."""
    canvas = np.zeros((1024, 1024), dtype=np.uint8)
    rl = rl.reshape(-1, 1, 2).astype(int)
    ll = ll.reshape(-1, 1, 2).astype(int)
    heart = heart.reshape(-1, 1, 2).astype(int)
    canvas = cv2.drawContours(canvas, [rl], -1, 1, -1)
    canvas = cv2.drawContours(canvas, [ll], -1, 1, -1)
    canvas = cv2.drawContours(canvas, [heart], -1, 2, -1)
    return canvas


@dataclass
class HybridGNetConfig:
    """Wrapper config to keep track of HybridGNet internals."""

    latents: int = 64
    input_size: int = 1024
    filters: Tuple[int, ...] = (2, 32, 32, 32, 16, 16, 16)


class HybridGNetSegmenter:
    """
    Thin wrapper around the original HybridGNet implementation so we can
    generate ROI masks for arbitrary CheXpert images.
    """

    def __init__(
        self,
        device: Optional[str] = None,
        weights_path: Optional[Path] = None,
    ) -> None:
        if not CHEXMASK_ROOT.exists():
            raise RuntimeError("CheXmask repository not found. Expected at %s" % CHEXMASK_ROOT)

        resolved_device = torch.device(device or ("cuda:0" if torch.cuda.is_available() else "cpu"))
        self.device = resolved_device

        default_weights = CHEXMASK_ROOT / "Weights" / "SegmentationModel" / "bestMSE.pt"
        self.weights_path = Path(weights_path) if weights_path else default_weights
        if not self.weights_path.exists():
            raise FileNotFoundError(f"HybridGNet weights not found at {self.weights_path}")

        self.config = HybridGNetConfig()
        self.hybrid = self._load_model()

    def _load_model(self) -> torch.nn.Module:
        A, AD, D, U = genMatrixesLungsHeart()

        # Convert matrices to sparse tensors as expected by HybridGNet
        A = sp.csc_matrix(A).tocoo()
        AD = sp.csc_matrix(AD).tocoo()
        D = sp.csc_matrix(D).tocoo()
        U = sp.csc_matrix(U).tocoo()

        D_ = [D.copy()]
        U_ = [U.copy()]
        n1 = A.shape[0]
        n2 = AD.shape[0]
        config_dict = {
            "n_nodes": [n1, n1, n1, n2, n2, n2],
            "latents": self.config.latents,
            "inputsize": self.config.input_size,
            "filters": list(self.config.filters),
            "skip_features": self.config.filters[1],
        }

        A_list = [A.copy(), A.copy(), A.copy(), AD.copy(), AD.copy(), AD.copy()]
        A_t, D_t, U_t = (
            [scipy_to_torch_sparse(x).to(self.device) for x in matrices]
            for matrices in (A_list, D_, U_)
        )

        model = Hybrid(config_dict, D_t, U_t, A_t).to(self.device)
        state = torch.load(self.weights_path, map_location=self.device)
        model.load_state_dict(state)
        model.eval()
        return model

    def _prepare_input(self, image: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Resize to 1024x1024 and keep track of original shape."""
        if image.ndim == 3:
            image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        original = image.copy()
        resized = cv2.resize(original, (self.config.input_size, self.config.input_size))
        normalized = resized.astype(np.float32) / 255.0
        return original, normalized

    def _predict_landmarks(self, tensor_input: torch.Tensor) -> np.ndarray:
        with torch.no_grad():
            outputs = self.hybrid(tensor_input)
        if isinstance(outputs, (tuple, list)):
            outputs = outputs[0]
        coords = outputs.cpu().numpy().reshape(-1, 2) * self.config.input_size
        return coords.round().astype(int)

    def generate_mask(self, image_path: Path) -> np.ndarray:
        """Generate a binary ROI mask for the provided image."""
        image = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
        if image is None:
            raise FileNotFoundError(f"Unable to read image at {image_path}")

        original, normalized = self._prepare_input(image)
        tensor_input = torch.from_numpy(normalized).unsqueeze(0).unsqueeze(0).to(self.device)
        coords = self._predict_landmarks(tensor_input)
        rl = coords[:44]
        ll = coords[44:94]
        heart = coords[94:]
        dense_mask = _dense_mask_from_landmarks(rl, ll, heart)

        resized_mask = cv2.resize(dense_mask, (original.shape[1], original.shape[0]), interpolation=cv2.INTER_NEAREST)
        binary_mask = (resized_mask > 0).astype(np.uint8)
        return binary_mask

    def apply_mask(
        self,
        image_path: Path,
        output_path: Path,
        mask_save_path: Optional[Path] = None,
        skip_if_exists: bool = True,
    ) -> None:
        """Generate & apply mask, then persist masked image (and optional mask)."""
        if skip_if_exists and output_path.exists():
            return

        mask = self.generate_mask(image_path)
        image = cv2.imread(str(image_path), cv2.IMREAD_UNCHANGED)
        if image is None:
            raise FileNotFoundError(f"Unable to read image at {image_path}")

        if image.ndim == 2:
            masked = cv2.bitwise_and(image, image, mask=mask * 255)
        else:
            masked = np.zeros_like(image)
            for c in range(image.shape[2]):
                masked[:, :, c] = cv2.bitwise_and(image[:, :, c], image[:, :, c], mask=mask * 255)

        _ensure_parent_dir(output_path)
        cv2.imwrite(str(output_path), masked)

        if mask_save_path:
            _ensure_parent_dir(mask_save_path)
            np.save(mask_save_path.with_suffix(".npy"), mask)


__all__ = ["HybridGNetSegmenter", "_normalize_rel_path"]
