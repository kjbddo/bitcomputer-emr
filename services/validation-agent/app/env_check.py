"""필수 환경변수 검증. 누락 시 즉시 종료한다."""
from __future__ import annotations

import os
import sys
from typing import Iterable


def require_env(names: Iterable[str]) -> None:
    missing = [n for n in names if not (os.environ.get(n) or "").strip()]
    if not missing:
        return
    print(
        "필수 환경변수가 설정되지 않았습니다: " + ", ".join(missing) + "\n"
        "infra/.env.example 을 참고해 infra/.env 를 채우세요.",
        file=sys.stderr,
    )
    raise SystemExit(1)
