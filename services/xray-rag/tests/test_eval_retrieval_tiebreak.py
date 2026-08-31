"""`eval_retrieval.py` 의 weighted voting 이 동점을 결정론적으로 깨는지 검증한다.

배경(EVALUATION.md §9.4)
------------------------
`scores` 는 `defaultdict` 이고 `for d in labels[j]` 는 **set** 을 순회한다. 파이썬
문자열의 해시는 `PYTHONHASHSEED` 에 따라 프로세스마다 달라지므로, set 순회 순서 →
`scores` 삽입 순서 → stable sort 의 동점 순서가 프로세스마다 달라졌다. 같은 DB,
같은 임베딩인데 top-1 any-match 가 146건 중 1건(±0.0068) 흔들렸다.

여기서 못박는 규칙
-----------------
1. 득표 총합이 큰 질환이 먼저 (기존과 동일).
2. 총합이 **정확히** 같으면, **더 가까운 이웃에서 처음 지지받은** 질환이 먼저.
3. 그것마저 같으면 질환 이름의 사전순.

2번이 핵심이다. 사전순만으로 깨면 순위가 라벨 철자라는 우연에 걸리고, 코퍼스
빈도로 깨면 평가가 비교 대상인 다수 라벨 기준선을 공짜로 얻어간다. "동점이면 더
비슷한 케이스가 지지한 쪽" 은 검색 신호 자체에서 나오는 규칙이라 둘 다 피한다.
3번은 1·2 로도 갈리지 않는 잔여 동점을 위한 것이고, 라벨 이름이 유일하므로 전순서가
보장된다.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import numpy as np

from scripts.eval_retrieval import _evaluate, _rank_diseases

_SERVICE_ROOT = Path(__file__).resolve().parent.parent


def test_exact_tie_is_broken_by_nearest_supporting_neighbour():
    """총합이 같으면 더 가까운 이웃이 지지한 라벨이 이긴다.

    aaa: 0순위 이웃 하나가 0.5 를 몰아준다.
    bbb: 1·2순위 이웃이 0.25 씩 나눠 0.5 를 만든다 (이진 부동소수에서 정확히 0.5).
    총합은 동점이고, 규칙 2 에 의해 aaa 가 이겨야 한다.
    """
    ranking = _rank_diseases(
        [
            (0, {"aaa"}, 0.5),
            (1, {"bbb"}, 0.25),
            (2, {"bbb"}, 0.25),
        ]
    )

    assert [d for d, _ in ranking] == ["aaa", "bbb"]
    assert ranking[0][1] == ranking[1][1]  # 실제로 동점이었음을 확인


def test_tie_at_same_rank_falls_back_to_label_order():
    """같은 이웃이 동시에 지지해 규칙 2 로도 갈리지 않으면 사전순으로 깬다.

    이 경우가 바로 해시 순서에 걸려 있던 자리다 — 한 이웃의 라벨 **집합** 을
    순회하는 순간 순서가 프로세스마다 달라졌다.
    """
    ranking = _rank_diseases([(0, {"bbb", "aaa"}, 0.5)])

    assert [d for d, _ in ranking] == ["aaa", "bbb"]


def test_higher_score_still_wins_over_closer_neighbour():
    """동점 파기 규칙이 1번(총합) 을 넘어서면 안 된다."""
    ranking = _rank_diseases(
        [
            (0, {"near"}, 0.1),
            (1, {"far"}, 0.9),
        ]
    )

    assert [d for d, _ in ranking] == ["far", "near"]


# ---------- 프로세스 간 불변성 ----------

_MULTISEED_SNIPPET = textwrap.dedent(
    """
    import json, sys
    sys.path.insert(0, __SERVICE_ROOT__)
    import numpy as np
    from scripts.eval_retrieval import _evaluate

    NEG = -np.inf
    # 케이스 0 을 질의로 두면 1순위 이웃(케이스 1)이 동점 라벨 두 개를 동시에
    # 지지한다 - 예전 구현에서 top-1 예측이 해시 순서로 결정되던 바로 그 형태다.
    # 고치기 전에는 이 조각이 seed 0,11 에서 0.6667 / seed 1,2,3,5,7 에서 0.3333 을
    # 냈다(146건 실측에서 본 ±1건 흔들림의 최소 재현).
    sim = np.array(
        [
            [NEG, 0.9, 0.3],
            [0.9, NEG, 0.3],
            [0.3, 0.3, NEG],
        ],
        dtype=np.float64,
    )
    labels = [{"aaa"}, {"aaa", "bbb"}, {"zzz"}]
    m = _evaluate(sim=sim, labels=labels, vote_top_k=1)
    print(json.dumps(m, sort_keys=True))
    """
)


def _run_with_hashseed(tmp_path: Path, seed: int) -> str:
    script = tmp_path / f"multiseed_{seed}.py"
    script.write_text(
        _MULTISEED_SNIPPET.replace("__SERVICE_ROOT__", repr(str(_SERVICE_ROOT))),
        encoding="utf-8",
    )
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = str(seed)
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(_SERVICE_ROOT),
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


def test_metrics_do_not_move_across_pythonhashseed(tmp_path):
    """서로 다른 `PYTHONHASHSEED` 로 띄운 프로세스들이 같은 지표를 내야 한다.

    이 테스트가 빨개지면 동점 파기가 다시 해시 순서에 의존하게 된 것이다.
    """
    outputs = {seed: _run_with_hashseed(tmp_path, seed) for seed in (0, 1, 2, 3, 5)}

    distinct = set(outputs.values())
    assert len(distinct) == 1, (
        "PYTHONHASHSEED 에 따라 지표가 달라졌다. seed별 결과:\n"
        + "\n".join(
            f"  seed={s}: top1={json.loads(o)['top1_accuracy_any_match']}"
            for s, o in outputs.items()
        )
    )


def test_evaluate_uses_the_deterministic_rule():
    """`_evaluate` 가 헬퍼를 실제로 쓰는지 - 단위 테스트만으로는 배선을 보장 못 한다.

    위 다중 seed 조각과 같은 데이터다. 케이스 0(정답 {aaa})의 1순위 이웃이
    {aaa, bbb} 라 동점이고, 규칙 3(사전순)에 따라 예측은 항상 `aaa` 여야 한다.
    그러면 top-1 any-match 는 케이스 0·1 이 맞고 케이스 2 가 틀려 2/3 이다.
    """
    NEG = -np.inf
    sim = np.array(
        [
            [NEG, 0.9, 0.3],
            [0.9, NEG, 0.3],
            [0.3, 0.3, NEG],
        ],
        dtype=np.float64,
    )
    labels = [{"aaa"}, {"aaa", "bbb"}, {"zzz"}]

    m = _evaluate(sim=sim, labels=labels, vote_top_k=1)

    assert m["top1_accuracy_any_match"] == 2 / 3
    assert m["per_disease_recall"]["aaa"]["top1"] == 1.0
    assert m["per_disease_recall"]["bbb"]["top1"] == 0.0


def test_per_disease_report_order_is_deterministic():
    """리포트의 per-disease 표 순서도 삽입 순서(=해시 순서)에 걸려 있었다.

    n 이 같은 라벨끼리는 stable sort 가 삽입 순서를 그대로 남긴다. 값은 같아도
    산출물 파일이 실행마다 달라지면 diff 로 회귀를 볼 수 없다.
    """
    NEG = -np.inf
    sim = np.array(
        [
            [NEG, 0.9, 0.3],
            [0.9, NEG, 0.3],
            [0.3, 0.3, NEG],
        ],
        dtype=np.float64,
    )
    labels = [{"ccc", "aaa", "bbb"}, {"ccc", "aaa", "bbb"}, {"ccc", "aaa", "bbb"}]

    m = _evaluate(sim=sim, labels=labels, vote_top_k=1)

    assert list(m["per_disease_recall"].keys()) == ["aaa", "bbb", "ccc"]
