"""
이미지 처리 유틸리티
"""
from __future__ import annotations
import sys
from pathlib import Path
from typing import Tuple, Optional
from PIL import Image
import numpy as np
import torch
from torchvision import transforms
import cv2

from config import DEFAULT_IMAGE_SIZE, DEFAULT_MEAN, DEFAULT_STD, ENABLE_MASKING

# 마스킹 지원 (선택적)
try:
    api_root = Path(__file__).parent
    utils_dir = api_root / 'utils'
    segmentation_dir = utils_dir / 'segmentation_processing'
    
    if segmentation_dir.exists():
        if str(segmentation_dir) not in sys.path:
            sys.path.insert(0, str(segmentation_dir))
        from hybridgnet_segmenter import HybridGNetSegmenter
        MASKING_SUPPORT = True
    else:
        MASKING_SUPPORT = False
except (ImportError, FileNotFoundError):
    MASKING_SUPPORT = False

# 전역 세그멘터 (lazy loading)
_segmenter: Optional[HybridGNetSegmenter] = None


def _get_segmenter() -> Optional[HybridGNetSegmenter]:
    """마스킹 세그멘터 초기화"""
    global _segmenter
    if not ENABLE_MASKING or not MASKING_SUPPORT:
        return None
    
    if _segmenter is None:
        try:
            device = 'cuda:0' if torch.cuda.is_available() else 'cpu'
            _segmenter = HybridGNetSegmenter(device=device)
        except Exception as e:
            print(f"Warning: 마스킹 세그멘터 초기화 실패: {e}")
            return None
    
    return _segmenter


def load_image(image_path: Path) -> Image.Image:
    """이미지 로드 및 그레이스케일 변환"""
    img = Image.open(str(image_path))
    if img.mode != 'L':
        img = img.convert('L')
    return img


def resize_and_center_crop(img: Image.Image, target_size: Tuple[int, int]) -> Image.Image:
    """이미지를 정해진 크기로 리사이즈 (비율 유지하면서 중앙 크롭)"""
    target_w, target_h = target_size
    orig_w, orig_h = img.size
    
    scale = max(target_w / orig_w, target_h / orig_h)
    new_w = int(orig_w * scale)
    new_h = int(orig_h * scale)
    
    img_resized = img.resize((new_w, new_h), Image.LANCZOS)
    
    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    right = left + target_w
    bottom = top + target_h
    
    return img_resized.crop((left, top, right, bottom))


def load_or_generate_mask(image_path: Path, mask_path: Path, target_size: Tuple[int, int]) -> np.ndarray:
    """
    마스크 파일을 로드하거나 생성
    AI dataloader와 동일: 이미지를 먼저 256x256으로 리사이즈한 후 마스크 생성
    """
    # 마스크 파일이 있으면 로드
    if mask_path.exists():
        try:
            mask = np.load(str(mask_path))
            if mask.shape != target_size:
                mask = cv2.resize(mask, target_size, interpolation=cv2.INTER_NEAREST)
                np.save(str(mask_path), mask)
            return mask
        except Exception:
            pass
    
    # 마스크 생성
    segmenter = _get_segmenter()
    if segmenter is None:
        return np.ones(target_size, dtype=np.uint8)
    
    try:
        # AI dataloader와 동일: 이미지를 먼저 256x256으로 리사이즈한 후 마스크 생성
        # 1. 원본 이미지를 256x256으로 리사이즈
        original_image = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
        if original_image is None:
            raise FileNotFoundError(f"Unable to read image: {image_path}")
        
        resized_image = cv2.resize(original_image, target_size, interpolation=cv2.INTER_LINEAR)
        
        # 2. 리사이즈된 이미지를 임시 파일로 저장하여 HybridGNetSegmenter에 전달
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp_file:
            tmp_path = Path(tmp_file.name)
            cv2.imwrite(str(tmp_path), resized_image)
        
        try:
            # 3. 리사이즈된 이미지로 마스크 생성 (이미 256x256 크기)
            mask = segmenter.generate_mask(tmp_path)
            
            # 4. 마스크가 이미 256x256 크기인지 확인하고, 필요시 리사이즈
            if mask.shape != target_size:
                mask = cv2.resize(mask, target_size, interpolation=cv2.INTER_NEAREST)
        finally:
            # 임시 파일 삭제
            if tmp_path.exists():
                tmp_path.unlink()
        
        # 5. 디스크에 마스크 저장
        mask_path.parent.mkdir(parents=True, exist_ok=True)
        np.save(str(mask_path), mask)
        return mask
    except Exception:
        return np.ones(target_size, dtype=np.uint8)


def preprocess_image(image_path: Path, mask_path: Optional[Path] = None) -> Tuple[torch.Tensor, Optional[torch.Tensor]]:
    """
    이미지 전처리 (모델 입력용)
    AI dataloader와 동일한 방식으로 처리
    
    Returns:
        (img_tensor, mask_tensor): img_tensor는 [1, 1, H, W], mask_tensor는 [1, 1, H, W] 또는 None
    """
    # 이미지 로드 및 리사이즈 (AI dataloader와 동일: 단순 resize 사용)
    img = load_image(image_path)
    img_resized = img.resize((DEFAULT_IMAGE_SIZE, DEFAULT_IMAGE_SIZE), Image.LANCZOS)  # AI 코드와 동일: 비율 무시하고 강제 리사이즈
    
    # 텐서 변환 (AI dataloader와 동일: normalize=False이므로 정규화하지 않음)
    transform = transforms.Compose([
        transforms.ToTensor()
    ])
    img_tensor = transform(img_resized)  # [1, H, W], 0-1 범위
    # AI 코드는 normalize=False이므로 정규화하지 않음
    img_tensor = img_tensor.unsqueeze(0)  # [1, 1, H, W]
    
    # 마스크 처리
    mask_tensor = None
    if ENABLE_MASKING and mask_path is not None:
        mask_array = load_or_generate_mask(image_path, mask_path, (DEFAULT_IMAGE_SIZE, DEFAULT_IMAGE_SIZE))
        mask_tensor = torch.from_numpy(mask_array).float().unsqueeze(0).unsqueeze(0)  # [1, 1, H, W]
        mask_tensor = (mask_tensor > 0.5).float()
    
    return img_tensor, mask_tensor


