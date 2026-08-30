"""app.ml.torch_embedding_model 의 실제 pretrained backbone embedding 모델 테스트.

배경: 과거 구현(TorchSimpleConvEmbedding)은 random-init Conv encoder였다 -
시드를 고정하지 않아 프로세스마다 다른 가중치를 가졌고, 그 결과 같은 입력이
프로세스마다 다른 벡터를 만들어냈다 (벡터 저장소로 쓸 수 없는 결함). 이 테스트는
새 구현(DenseNet121 ImageNet pretrained backbone)이:
  1) build_torch_embedding_model() 계약(dim, image_size) -> Optional[Model] 을
     그대로 지킨다 (실패 시 None, 절대 mock을 real처럼 위장하지 않는다).
  2) embed() 가 L2 정규화된 float32 벡터를 반환한다.
  3) 같은 입력에 대해 "같은 프로세스 안에서 모델을 두 번 만들어도" 항상 같은
     벡터가 나온다 (cross-process 결정성의 필요조건). 진짜 cross-process
     증거는 scripts/verify_embedding_determinism.py 를 두 개의 별도 OS
     프로세스로 실행해 별도로 확인한다(리포트 참고).
"""
from __future__ import annotations

import numpy as np
import pytest

from app.ml.torch_embedding_model import (
    _NATIVE_DIM,
    TorchDenseNetEmbedding,
    build_torch_embedding_model,
)


def _fixed_error_map(size: int = 256) -> np.ndarray:
    # 프로세스와 무관하게 항상 같은 입력을 만들기 위해 np.random 대신
    # 결정론적 패턴(좌표 기반)을 쓴다.
    yy, xx = np.mgrid[0:size, 0:size]
    m = (np.sin(xx / 11.0) + np.cos(yy / 7.0) + 2.0) / 4.0
    return m.astype(np.float32)


def test_build_returns_model_for_native_dim():
    model = build_torch_embedding_model(dim=_NATIVE_DIM, image_size=256)
    assert model is not None


def test_build_returns_none_when_backbone_load_fails(monkeypatch):
    """계약: 로드 실패 시 절대 조용히 real 로 위장하지 않고 None 을 반환해야 한다."""

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated weight load failure")

    monkeypatch.setattr(
        "torchvision.models.densenet121",
        _boom,
    )
    model = build_torch_embedding_model(dim=_NATIVE_DIM, image_size=256)
    assert model is None


def test_embed_output_shape_and_dtype():
    model = TorchDenseNetEmbedding(dim=_NATIVE_DIM, image_size=256)
    v = model.embed(_fixed_error_map())
    assert v.shape == (_NATIVE_DIM,)
    assert v.dtype == np.float32


def test_embed_output_is_l2_normalized():
    model = TorchDenseNetEmbedding(dim=_NATIVE_DIM, image_size=256)
    v = model.embed(_fixed_error_map())
    norm = float(np.linalg.norm(v))
    assert norm == pytest.approx(1.0, abs=1e-4)


def test_two_instances_same_process_produce_identical_native_dim_vectors():
    """가중치가 사전학습 고정값이어야 한다 - random-init 이면 이 테스트가 깨진다."""
    error_map = _fixed_error_map()
    m1 = TorchDenseNetEmbedding(dim=_NATIVE_DIM, image_size=256)
    m2 = TorchDenseNetEmbedding(dim=_NATIVE_DIM, image_size=256)
    v1 = m1.embed(error_map)
    v2 = m2.embed(error_map)
    assert np.array_equal(v1, v2)


def test_two_instances_same_process_produce_identical_projected_vectors():
    """dim != 1024(native) 경로: 고정 시드 투영이 없으면 이 테스트가 깨진다."""
    projected_dim = 768
    error_map = _fixed_error_map()
    m1 = TorchDenseNetEmbedding(dim=projected_dim, image_size=256)
    m2 = TorchDenseNetEmbedding(dim=projected_dim, image_size=256)
    v1 = m1.embed(error_map)
    v2 = m2.embed(error_map)
    assert v1.shape == (projected_dim,)
    assert np.array_equal(v1, v2)


def test_embed_is_sensitive_to_input():
    """완전히 다른 입력은 (거의 확실히) 다른 벡터를 만든다 - 상수 함수가 아님을 확인."""
    model = TorchDenseNetEmbedding(dim=_NATIVE_DIM, image_size=256)
    v_zero = model.embed(np.zeros((256, 256), dtype=np.float32))
    v_pattern = model.embed(_fixed_error_map())
    assert not np.array_equal(v_zero, v_pattern)
