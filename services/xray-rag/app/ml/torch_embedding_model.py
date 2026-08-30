"""(선택) PyTorch 기반 embedding model.

DenseNet121(ImageNet 사전학습)을 고정 feature extractor로 쓰는 실제 embedding
어댑터. 이전 구현(TorchSimpleConvEmbedding)은 random-init Conv encoder였고
가중치를 시드 고정 없이 초기화했다 - 그 결과 같은 입력이라도 프로세스마다
다른 벡터가 나왔다(벡터 저장소 유사도 검색이 전혀 성립하지 않는 결함). 이
모듈은 그 자리를 대체한다.

## 왜 DenseNet121인가
CheXpert 계열 흉부 X-ray 벤치마크(Irvin et al., 2019 및 그 이후 대다수 후속
연구)의 관례적 baseline backbone이 DenseNet121이다. ResNet50/ResNet18도
ImageNet 특징 추출기로는 무난하지만, 이 프로젝트가 다루는 도메인(흉부 X-ray
reconstruction-error map)과 같은 계열의 선행 연구가 이미 DenseNet121로 수렴해
있어 이후 CheXpert 기반 fine-tuning/비교를 할 때 기존 문헌과 맞대기 쉽다는
실질적 이점이 있다. 특별히 이를 뒤집을 이유(레이턴시 제약, 파라미터 예산 등)가
없어 관례를 따른다.

## 입력 변환 (중요 - 여기를 틀리면 "진짜" 모델인데 의미 없는 임베딩이 나온다)
error_map은 app.services.error_map_service.compute_error_map()이 만드는
[H, W] float32이며 값 범위는 [0, 1]이다(reconstruction error를 그 프레임의
최댓값으로 나눠 정규화 - 완벽히 복원된 픽셀은 0, error_map 이 apply_roi_mask로
마스킹된 경우도 0/해당 오차값만 남으므로 여전히 [0, 1] 범위). DenseNet121은
3채널, ImageNet 정규화가 적용된 224x224 입력을 기대한다. 변환 절차:

  1) [H, W] -> 채널 축 추가 후 3채널로 복제한다 (흑백 오차맵을 RGB처럼 취급).
  2) bilinear 보간으로 256x256으로 리사이즈한 뒤 224x224로 center crop한다.
     이는 torchvision의 표준 IMAGENET1K_V1 전처리(Resize(256)+CenterCrop(224),
     bilinear)와 동일한 절차다 - DenseNet121_Weights.IMAGENET1K_V1.transforms()
     참고.
  3) 채널별로 ImageNet mean/std ([0.485, 0.456, 0.406] / [0.229, 0.224, 0.225])
     로 정규화한다. error_map 값이 이미 [0, 1] 범위이므로, 이 지점에서
     torchvision.transforms.ToTensor()가 [0, 255] uint8 이미지에 대해 수행하는
     "/255" 스케일링과 동일한 스케일이 된다 - 즉 error_map을 "이미 [0, 1]로
     스케일된 흑백 사진"으로 취급해 그대로 정규화한다.

이 변환은 자연 사진이 아닌 흑백 오차맵에 ImageNet 정규화를 적용하는 근사다.
흉부 X-ray 도메인 특화 사전학습(CheXpert self-supervised encoder 등)보다는
부정확하겠지만, ImageNet 특징 공간이 갖는 텍스처/형태 변별력 덕분에
random-init보다는 훨씬 유의미한 유사도를 낸다 - 이 교체 작업의 목적이다.

## 차원(dim)과 결정성
DenseNet121의 pooled feature는 1024차원(_NATIVE_DIM)이다.
  - dim == 1024 (기본값. EMBEDDING_DIM 기본값을 1024로 맞췄으므로 보통 이
    경로를 탄다)면 투영 없이 그대로 반환한다.
  - dim != 1024로 호출되면(예: 과거 EMBEDDING_DIM=768 설정과의 호환), 고정
    시드(_PROJECTION_SEED)로 초기화한 random linear projection(1024 -> dim)을
    거친다. **_PROJECTION_SEED를 바꾸면 이미 저장된 모든 임베딩 벡터가
    무효화된다** - 같은 입력이라도 다른 투영 행렬을 거치면 다른 벡터가 나온다.

두 경로 모두 가중치가 고정(사전학습 체크포인트, 또는 고정 시드 투영)이고
모델이 eval() 상태로 고정돼(BatchNorm이 배치 통계가 아닌 저장된 running
통계를 쓰고, Dropout이 비활성화됨) 순전파에 난수가 개입하지 않는다. 따라서
"같은 입력 -> 같은 벡터"가 프로세스와 무관하게 성립한다. 두 개의 독립된 OS
프로세스를 새로 띄워 같은 입력을 넣었을 때 벡터가 bit-for-bit 동일함을
scripts/verify_embedding_determinism.py 로 확인했다(리포트의 실측치 참고).

최종 벡터는 L2 정규화해서 반환한다(cosine 유사도 기반 vector index와 맞춤).
"""
from __future__ import annotations

from typing import Optional

import numpy as np

# DenseNet121 pooled feature의 네이티브 차원. dim이 이 값과 다를 때만 투영을 쓴다.
_NATIVE_DIM = 1024

# dim != _NATIVE_DIM일 때만 쓰이는 투영 행렬의 고정 시드.
# **이 값을 바꾸면 이미 저장된 모든 (dim != 1024인) 임베딩 벡터가 무효화된다**
# - 같은 입력이라도 다른 랜덤 투영 행렬을 거치게 되어 다른 벡터가 나온다.
_PROJECTION_SEED = 20260830

# torchvision DenseNet121_Weights.IMAGENET1K_V1.transforms() 와 동일한 전처리
# 파라미터(Resize(256) -> CenterCrop(224), bilinear, ImageNet mean/std).
_RESIZE_SIZE = 256
_CROP_SIZE = 224
_IMAGENET_MEAN = (0.485, 0.456, 0.406)
_IMAGENET_STD = (0.229, 0.224, 0.225)


class TorchDenseNetEmbedding:
    """ImageNet 사전학습 DenseNet121을 고정 feature extractor로 쓰는 embedding 모델."""

    def __init__(self, dim: int = 768, image_size: int = 256) -> None:
        import torch
        import torch.nn as nn
        import torch.nn.functional as F
        from torchvision.models import DenseNet121_Weights, densenet121

        self._torch = torch
        self._F = F
        self.dim = dim
        self.image_size = image_size

        backbone = densenet121(weights=DenseNet121_Weights.IMAGENET1K_V1)
        backbone.eval()
        for p in backbone.parameters():
            p.requires_grad_(False)
        # classifier(1000-way ImageNet head)는 쓰지 않는다 - conv feature 스택만.
        self._backbone_features = backbone.features

        self._projection = None
        if dim != _NATIVE_DIM:
            gen = torch.Generator().manual_seed(_PROJECTION_SEED)
            proj = nn.Linear(_NATIVE_DIM, dim, bias=False)
            with torch.no_grad():
                proj.weight.copy_(
                    torch.randn(dim, _NATIVE_DIM, generator=gen) / (_NATIVE_DIM ** 0.5)
                )
            proj.eval()
            for p in proj.parameters():
                p.requires_grad_(False)
            self._projection = proj

        self._mean = torch.tensor(_IMAGENET_MEAN, dtype=torch.float32).view(1, 3, 1, 1)
        self._std = torch.tensor(_IMAGENET_STD, dtype=torch.float32).view(1, 3, 1, 1)

    def _preprocess(self, error_map: np.ndarray):
        torch = self._torch
        F = self._F
        x = torch.from_numpy(np.ascontiguousarray(error_map, dtype=np.float32))
        x = torch.clamp(x, 0.0, 1.0)
        x = x.unsqueeze(0).unsqueeze(0)  # [1, 1, H, W]
        x = x.repeat(1, 3, 1, 1)  # [1, 3, H, W] - grayscale -> RGB로 취급
        x = F.interpolate(x, size=(_RESIZE_SIZE, _RESIZE_SIZE), mode="bilinear", align_corners=False)
        top = (_RESIZE_SIZE - _CROP_SIZE) // 2
        left = top
        x = x[:, :, top:top + _CROP_SIZE, left:left + _CROP_SIZE]
        x = (x - self._mean) / self._std
        return x

    def embed(self, error_map: np.ndarray) -> np.ndarray:
        torch = self._torch
        F = self._F
        with torch.no_grad():
            x = self._preprocess(error_map)
            feat = self._backbone_features(x)
            feat = F.relu(feat, inplace=True)
            feat = F.adaptive_avg_pool2d(feat, (1, 1))
            feat = torch.flatten(feat, 1)  # [1, 1024]
            if self._projection is not None:
                feat = self._projection(feat)
            v = feat.cpu().numpy()[0]
        n = float(np.linalg.norm(v))
        if n < 1e-8:
            return v.astype(np.float32)
        return (v / n).astype(np.float32)


def build_torch_embedding_model(dim: int, image_size: int) -> Optional[TorchDenseNetEmbedding]:
    try:
        return TorchDenseNetEmbedding(dim=dim, image_size=image_size)
    except Exception as e:  # pragma: no cover
        print(f"[ml] torch embedding model unavailable, falling back to mock: {e}")
        return None
