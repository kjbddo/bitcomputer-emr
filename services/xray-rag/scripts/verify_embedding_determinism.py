"""app.ml.torch_embedding_model 의 cross-process 결정성 검증 스크립트.

목표: 같은 입력(고정 패턴 error map)에 대해, 매번 새로 뜨는 OS 프로세스가
항상 같은 임베딩 벡터를 만드는지 확인한다. 프로세스 내부 테스트(같은
프로세스 안에서 모델을 두 번 만들어 비교)만으로는 "모듈 import 시점의
프로세스 전역 상태(예: 난수 시드)"에 우연히 의존하는 결정성을 놓칠 수 있다 -
이 스크립트를 별도 OS 프로세스로 두 번 실행해 stdout을 비교하는 것이
실제 요구사항("두 프로세스가 같은 벡터를 만든다")을 직접 증명한다.

실행:
  /c/Python314/python scripts/verify_embedding_determinism.py > run1.txt
  /c/Python314/python scripts/verify_embedding_determinism.py > run2.txt
  diff run1.txt run2.txt   # 비어 있어야 함(완전히 동일)

옵션:
  --dim N   임베딩 차원(기본: EMBEDDING_DIM 설정값, 보통 1024 - 투영 없음).
            1024가 아닌 값을 주면 고정 시드 투영 경로를 검증한다.
"""
from __future__ import annotations

import argparse
import sys

import numpy as np

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))

from app.config import Settings  # noqa: E402
from app.ml.torch_embedding_model import build_torch_embedding_model  # noqa: E402


def _fixed_error_map(size: int = 256) -> np.ndarray:
    # np.random 대신 좌표 기반 결정론적 패턴 - 실행할 때마다(프로세스가 달라도)
    # 항상 동일한 입력을 보장한다.
    yy, xx = np.mgrid[0:size, 0:size]
    m = (np.sin(xx / 11.0) + np.cos(yy / 7.0) + 2.0) / 4.0
    return m.astype(np.float32)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dim", type=int, default=None)
    args = parser.parse_args()

    settings = Settings()
    dim = args.dim if args.dim is not None else settings.EMBEDDING_DIM

    model = build_torch_embedding_model(dim=dim, image_size=settings.IMAGE_SIZE)
    if model is None:
        print("BUILD_FAILED", file=sys.stderr)
        return 1

    v = model.embed(_fixed_error_map())
    print(f"dim={dim}")
    print(f"shape={v.shape[0]}")
    print(f"norm={float(np.linalg.norm(v)):.10f}")
    # 벡터 전체를 raw bytes의 16진수 표현으로 출력해 bit-for-bit 비교를 가능하게
    # 한다. 부동소수점을 %.Nf 로 반올림해서 출력하면 실제로는 다른데 같아
    # 보이는 거짓양성이 생길 수 있어, hex 표현을 기준으로 diff한다.
    print("vector_hex=" + v.tobytes().hex())
    print("vector_head=" + ",".join(f"{x:.8f}" for x in v[:8]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
