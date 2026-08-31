"""코드 기본값과 compose 기본값이 어긋나면 안 된다.

이 저장소에서 실제로 일어난 일이다. `USE_PSPNET_ROI` 가 `app/config.py` 에서는
`True`, `infra/docker-compose.yml` 에서는 `${USE_PSPNET_ROI:-false}` 였다.

컨테이너는 compose 를 거치므로 `false` 로 떠서 고전 CV 마스크로 질의했다.
그런데 **적재 스크립트는 호스트에서 돈다.** compose 를 거치지 않으므로
`app/config.py` 의 기본값을 읽어 PSPNet 으로 코퍼스를 만들었다.

결과: 저장된 ROI 임베딩은 `pspnet_chestxdet_v1`, 질의는 `cv_lung_heart_v1`.
유사도 검색이 서로 다른 해부 기준끼리를 비교하는데 **양쪽 다 정상으로 보인다.**
컨테이너는 healthy 고, 시더는 202건 적재 성공을 보고하고, 검색은 결과를 낸다.
런북대로 따라가기만 해도 그 상태가 만들어졌다.

그래서 두 기본값이 같다는 것을 테스트가 지킨다. 값 자체가 무엇이든 상관없다 -
**둘이 다르면 실패한다.**
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.config import Settings

REPO_ROOT = Path(__file__).resolve().parents[3]
COMPOSE = REPO_ROOT / "infra" / "docker-compose.yml"

# 코드 기본값과 compose 기본값이 같아야 하는 토글.
#
# 여기 없는 토글이 어긋나도 이 테스트는 모른다. 새 토글을 만들 때 한 줄
# 넣는 것이 이 테스트를 유지하는 유일한 수작업이다.
TOGGLES = ["USE_PSPNET_ROI", "USE_CV_ROI"]

# `USE_TORCH_ANOMALY` / `USE_TORCH_EMBEDDING` 은 일부러 뺐다.
#
# 그 둘은 코드 기본값 False, compose 기본값 true 로 **의도적으로** 다르다.
# 기본값이 False 인 이유는 테스트 때문이다 - True 면 단위 테스트가 매번 torch
# 가중치를 올리려 들어 스위트가 몇 분씩 걸리고, 가중치가 없는 환경에서는
# CI 가 깨진다. 컨테이너는 실제 추론을 해야 하므로 compose 가 true 로 덮는다.
#
# 대신 적재 스크립트를 호스트에서 돌릴 때 그 둘을 명시적으로 켜야 한다.
# 잊으면 mock 임베딩으로 코퍼스가 만들어지는데, 런북 §5.4 가 그 확인 절차를
# 함께 적어 둔다("v 가 mock_pca_v1 이면 ..."). 시더 자신도 끝에 어느 모델로
# 적재했는지 출력한다.
#
# USE_PSPNET_ROI 는 사정이 다르다. 그것을 켜고 끄는 것은 mock 이냐 실제냐가
# 아니라 **어느 실제 분할기냐**(pspnet/cv)이고, 둘 다 실제 마스크를 만든다.
# 그래서 "안 켜면 mock 이라 티가 난다" 는 안전장치가 없고, 어긋나도 양쪽 다
# 정상으로 보인다. 이 축만 기본값 일치를 강제하는 이유다.


def _compose_default(name: str) -> str | None:
    """compose 의 `${NAME:-기본값}` 에서 기본값을 뽑는다.

    compose 가 그 변수를 아예 싣지 않으면 None 이다 - 그때는 컨테이너도 코드
    기본값을 쓰므로 어긋날 수가 없다.
    """
    text = COMPOSE.read_text(encoding="utf-8")
    match = re.search(rf"\$\{{{name}:-([^}}]*)\}}", text)
    return match.group(1).strip().strip('"').strip("'") if match else None


def _as_bool(raw: str) -> bool:
    return raw.strip().lower() in ("1", "true", "yes", "y", "on")


@pytest.mark.parametrize("name", TOGGLES)
def test_code_default_matches_compose_default(name):
    compose_raw = _compose_default(name)
    if compose_raw is None:
        pytest.skip(f"{name} 은 compose 가 싣지 않는다 - 어긋날 수 없다")

    code_default = getattr(Settings, name)
    assert isinstance(code_default, bool), (
        f"{name} 의 코드 기본값이 bool 이 아니다: {code_default!r}"
    )
    assert code_default == _as_bool(compose_raw), (
        f"{name}: 코드 기본값 {code_default} != compose 기본값 {compose_raw!r}.\n"
        "컨테이너는 compose 를 거치지만 호스트에서 도는 적재 스크립트는 코드\n"
        "기본값을 읽는다. 둘이 다르면 저장된 벡터와 질의 벡터가 서로 다른\n"
        "기준 위에 놓이고, 그 상태에서 양쪽 다 정상으로 보인다."
    )


def test_compose_actually_declares_the_roi_toggle():
    """위 테스트가 skip 으로 조용히 통과하지 않게 한다.

    compose 에서 `USE_PSPNET_ROI` 줄이 사라지면 `_compose_default` 가 None 을
    내고 파라미터 테스트는 skip 된다 - 지켜야 할 것이 사라졌는데 초록으로
    남는다. 이 축만은 선언 자체를 요구한다.
    """
    assert _compose_default("USE_PSPNET_ROI") is not None, (
        "compose 가 USE_PSPNET_ROI 를 싣지 않는다 - 컨테이너의 ROI 분할기를 "
        "환경변수로 제어할 수 없게 됐다"
    )
