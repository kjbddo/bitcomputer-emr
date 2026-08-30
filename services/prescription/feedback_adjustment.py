"""의사 피드백이 confidence 를 어떻게 조정하는가 — 산술 한 곳.

spec: Docs/superpowers/specs/2026-08-30-ai-service-redesign-design.md §3.4

순수 함수만 둔다(GC-1) — I/O 도 LLM 도 전역 상태도 쓰지 않는다.
`ranking.py`·`medication_codes.py` 와 같은 이유로 분리한다: 이 산술은
`fetch_confidence_scores_by_diagnosis_codes`(run_prescription_agent.py) 안에
인라인으로 있었고 테스트가 하나도 없었다.

## 무엇을 하는가

의사가 처방을 수용/거절했거나, 추천됐어야 할 처방이 놓쳤을 때 그 기록이
`history_recommended_prescription`(Arango) 에 쌓인다. 이 모듈은 그 집계
(총 건수·수용·거절·놓침)를 받아 confidence 점수에 더할 조정값 하나를 낸다.

    accepted_rate = accepted / total
    rejected_rate = rejected / total
    missed_rate   = missed   / total
    raw_adj = (accepted_boost * accepted_rate)
            - (rejected_penalty * rejected_rate)
            + (missed_boost * missed_rate)
    shrink  = total / (total + feedback_smoothing)
    feedback_adjustment = raw_adj * shrink

`shrink` 가 표본이 적을 때 조정값을 강하게 눌러 놓는다 — 클릭 한두 번이
순위를 함부로 뒤집지 못하게 하는 장치다. 다만 표본이 아주 적어도 0 은
아니므로, 데이터 규모가 작은 지금은 여전히 클릭 한 번이 순위를 흔들
정도의 크기가 나온다(아래 "이 조정이 얼마나 예민한가" 참고).

## 왜 지금 이걸 뽑아내는가 — 이 로직은 켜져 있지만 검증된 적이 없다

라이브 시스템 실측(2026-08-30)에서 고리 자체는 배선이 끊긴 곳 없이 닫혀
있었다: 웹 → `AgentController` → `AgentServiceImpl.savePrescriptionFeedback`
→ MySQL `prescription_feedback` + Arango `saveFeedbackToGraph` → 이 조정
산술을 쓰는 confidence AQL. `grep -rn "feedback_adjustment" tests/` 는
아무것도 찾지 못했다 — 부호가 뒤집혀도(거절을 가점으로 계산해도) 테스트
스위트는 그것을 잡아내지 못했을 것이다. 이 모듈과 `tests/test_feedback_adjustment.py`
가 그 공백을 메운다.

## 지금 쌓인 데이터는 이 조정에 효과가 없다 — 읽는 사람이 반드시 알아야 하는 것

Arango `history_recommended_prescription` 에는 현재 3행이 있지만, 그 세
`prescription_code`(`625900141`, `642600070`, `E02960081`) 는 **`order_lines`
어디에도 존재하지 않는다**(개별 확인함). `E02960081` 은 `medication_codes.py`
의 9자리 숫자 규칙으로도 약제 코드가 아니다. 이 조정 함수를 호출하는
쪽(`fetch_confidence_scores_by_diagnosis_codes`)은 후보 코드(`order_lines`
에서 나온 `union_rows`)를 키로 `feedback_by_code` 를 조회하므로, 후보 목록에
없는 코드의 피드백 행은 **절대 매칭되지 않고 조용히 무시된다** — 조정값이
0.0 이 아니라 애초에 계산 자체가 그 행을 보지 못한다.

**따라서 `prescription_feedback`/`history_recommended_prescription` 의 행
수가 0 이 아니라는 것이, 이 고리가 실제로 순위에 영향을 주고 있다는 뜻은
아니다.** 지금 쌓인 3행을 만든 경로는 현재의 추천 경로(§3.1 이 옮긴 조회
기반 후보)가 아니었다는 뜻이고, 다음에 이 상태를 확인하는 사람은 반드시
"행이 있다"가 아니라 "그 행의 `prescription_code` 가 실제 후보 코드와
매칭되는가"를 봐야 한다.

## 이 조정이 얼마나 예민한가 — 상수를 건드릴 사람에게

현재 데이터 규모에서 관측 **1건**(전량 수용, `total=1`)의 조정값은
`0.15 * (1/6) = 0.025` 다. 2026-08-30 라이브 조회에서 E11 약제 후보
confidence 는 0.0718 근방에 몰려 있었고 1위가 0.1105 였다 — 군집 폭이
0.0387 이다. 0.025 는 그 폭의 절반을 넘는다. **의사 한 명의 클릭 한 번이
순위를 뒤집을 수 있다.** 이것은 결함이 아니라 표본이 적을 때 이 설계가
의도한 대로 동작하는 것이지만(스무딩이 없으면 더 심했을 것), 나중에
`feedback_smoothing` 상수를 바꾸는 사람은 이 크기가 어떻게 움직이는지
보고 결정해야 한다. `tests/test_feedback_adjustment.py` 가 이 수치를
고정해 둔다.
"""
from __future__ import annotations

_EPSILON = 1e-9


def compute_feedback_adjustment(
    *,
    total: float,
    accepted: float,
    rejected: float,
    missed: float,
    accepted_boost: float,
    rejected_penalty: float,
    missed_boost: float,
    feedback_smoothing: float,
) -> float:
    """수용/거절/놓침 집계에서 confidence 에 더할 조정값 하나를 낸다.

    `total <= 0` 이면(관측이 없으면) 다른 인자와 무관하게 정확히 ``0.0`` 을
    돌려준다 — 근사값이 아니라 관측 없음을 뜻하는 값이다.
    """
    if total <= 0:
        return 0.0
    accepted_rate = accepted / total
    rejected_rate = rejected / total
    missed_rate = missed / total
    raw_adj = (
        (accepted_boost * accepted_rate)
        - (rejected_penalty * rejected_rate)
        + (missed_boost * missed_rate)
    )
    shrink = total / (total + max(feedback_smoothing, _EPSILON))
    return raw_adj * shrink


def apply_feedback_adjustment(*, base_score: float, feedback_adjustment: float) -> float:
    """조정값을 기본 점수에 더하고 confidence 계약대로 [0, 1] 로 자른다."""
    return min(1.0, max(0.0, base_score + feedback_adjustment))
