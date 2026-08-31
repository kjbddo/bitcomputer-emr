"""ChestX-Det PSPNet 가중치를 호스트 캐시에 한 번 받아둔다.

왜 별도 스크립트인가
--------------------
`app/ml/pspnet_roi_model.build_pspnet_roi_model()` 은 **기본적으로 다운로드하지
않는다**. 운영 컨테이너에는 egress 가 없어서, 모델 빌드 시점에 다운로드를 시도하면
기동이 네트워크 타임아웃만큼 멈춘다(DenseNet 가중치가 같은 이유로 호스트 캐시를
마운트해 쓰고 있다 - infra/docker-compose.yml 의 xraygraph 블록, 그리고
Docs/07-runbook-data-loading.md §5.5 참고).

그래서 "받는 일"을 여기로 분리한다. 호스트에서 한 번 실행해 캐시를 채우고,
컨테이너에는 그 디렉터리를 read-only 로 마운트한다.

사용:
    python scripts/fetch_pspnet_weights.py            # 기본 캐시 경로
    python scripts/fetch_pspnet_weights.py --cache-dir /some/where
    python scripts/fetch_pspnet_weights.py --verify-only

받는 것:
    pspnet_chestxray_best_model_4.pth  (273MB)
    sha256 019b167eac6b729fc1bb92bbbc185fc1730aaa65819f4e3fe718186cadc044fc
    출처 https://github.com/mlmed/torchxrayvision/releases/download/v1/
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path


def _setup_path() -> None:
    here = Path(__file__).resolve()
    if str(here.parent.parent) not in sys.path:
        sys.path.insert(0, str(here.parent.parent))


_setup_path()

from app.ml.pspnet_roi_model import (  # noqa: E402
    PSPNET_WEIGHTS_FILENAME,
    _default_cache_dir,
    build_pspnet_roi_model,
    weights_path,
)

# 2026-08-31 에 받은 파일의 해시. 상류가 같은 파일명으로 다른 가중치를 올리면
# 여기서 드러난다 - 조용히 다른 모델로 바뀌는 것이 이 프로젝트가 제일 피하고 싶은
# 종류의 사고다.
EXPECTED_SHA256 = "019b167eac6b729fc1bb92bbbc185fc1730aaa65819f4e3fe718186cadc044fc"


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cache-dir", default=None, help="기본: ~/.torchxrayvision/models_data/")
    ap.add_argument("--verify-only", action="store_true", help="받지 않고 해시만 확인한다")
    args = ap.parse_args()

    cache_dir = args.cache_dir or _default_cache_dir()
    path = weights_path(cache_dir)
    print(f"[cache] {cache_dir}")

    if not os.path.isfile(path):
        if args.verify_only:
            print(f"[fail] {PSPNET_WEIGHTS_FILENAME} 이 없다")
            return 2
        print(f"[fetch] {PSPNET_WEIGHTS_FILENAME} (273MB) ...")
        # 실제 다운로드는 torchxrayvision 이 한다. 어댑터를 만들면서 받는다.
        model = build_pspnet_roi_model(cache_dir=cache_dir, allow_download=True)
        if model is None:
            print("[fail] 다운로드/로드에 실패했다")
            return 1

    actual = _sha256(path)
    ok = actual == EXPECTED_SHA256
    print(f"[sha256] {actual} {'ok' if ok else 'MISMATCH'}")
    if not ok:
        print(f"[fail] 기대값과 다르다: {EXPECTED_SHA256}")
        print("       상류 릴리스가 바뀌었을 수 있다. 확인 전에는 쓰지 않는다.")
        return 1

    size_mb = os.path.getsize(path) / (1024 * 1024)
    print(f"[ok] {path} ({size_mb:.0f}MB)")
    print()
    print("컨테이너에는 이 디렉터리를 마운트한다(infra/docker-compose.yml, xraygraph):")
    print(f"  - {cache_dir}:/root/.torchxrayvision/models_data:ro")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
