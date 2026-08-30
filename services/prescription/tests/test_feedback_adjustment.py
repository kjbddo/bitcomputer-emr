"""피드백 고리의 핵심 산술을 고정한다.

spec: Docs/superpowers/specs/2026-08-30-ai-service-redesign-design.md §3.4

`fetch_confidence_scores_by_diagnosis_codes` 안에 인라인으로 있던 조정식을
`feedback_adjustment.py` 로 옮기고 여기서 성질을 고정한다. 다섯 성질:

1. 방향 — 수용은 올리고 거절은 내리고 놓침은 소폭 올린다. 부호가 뒤집히면
   시스템이 "의사가 거절한 것을 더 추천하도록" 조용히 학습하게 된다.
2. 스무딩이 실제로 줄인다 — 표본 1개일 때 조정값은 원 조정값(raw_adj)보다
   훨씬 작아야 하고, 표본이 늘수록 원 조정값에 단조적으로 접근해야 한다.
3. 클램핑 — 최종 점수는 항상 [0, 1] 안에 있다.
4. 피드백 0건은 정확히 0.0 — 근사값이 아니라 정확히 0.0.
5. 민감도 — 현재 데이터 규모에서 관측 1건이 후보 목록을 뒤집을 수 있을
   만큼 크다는 것을 수치로 남긴다.
"""
from __future__ import annotations

from feedback_adjustment import apply_feedback_adjustment, compute_feedback_adjustment

# prescription_api.py:515-518 이 읽는 기본값과 동일해야 한다.
ACCEPTED_BOOST = 0.15
REJECTED_PENALTY = 0.20
MISSED_BOOST = 0.05
FEEDBACK_SMOOTHING = 5.0


def _adj(total, accepted, rejected, missed, **overrides):
    kwargs = dict(
        accepted_boost=ACCEPTED_BOOST,
        rejected_penalty=REJECTED_PENALTY,
        missed_boost=MISSED_BOOST,
        feedback_smoothing=FEEDBACK_SMOOTHING,
    )
    kwargs.update(overrides)
    return compute_feedback_adjustment(
        total=total, accepted=accepted, rejected=rejected, missed=missed, **kwargs
    )


# --- 1. 방향: 수용은 올리고, 거절은 내리고, 놓침은 소폭 올린다 ---


def test_all_accepted_raises_the_adjustment():
    assert _adj(total=10, accepted=10, rejected=0, missed=0) > 0.0


def test_all_rejected_lowers_the_adjustment():
    assert _adj(total=10, accepted=0, rejected=10, missed=0) < 0.0


def test_all_missed_raises_the_adjustment_slightly():
    """놓침도 올라가지만 같은 비율의 수용보다는 작게(0.05 < 0.15)."""
    missed_adj = _adj(total=10, accepted=0, rejected=0, missed=10)
    accepted_adj = _adj(total=10, accepted=10, rejected=0, missed=0)
    assert missed_adj > 0.0
    assert missed_adj < accepted_adj


def test_rejected_penalty_outweighs_missed_boost_for_same_rate():
    """거절 감점(0.20)이 놓침 가점(0.05)보다 크다 — 섞이면 순감점이어야 한다."""
    mixed = _adj(total=10, accepted=0, rejected=5, missed=5)
    assert mixed < 0.0


# --- 2. 스무딩이 실제로 줄인다 ---


def test_single_observation_shrinks_far_below_the_raw_boost():
    """표본 1개(전량 수용)일 때 조정값은 원 부스트(0.15)보다 훨씬 작다.

    total=1, accepted=1 -> raw_adj = 0.15, shrink = 1/(1+5) = 1/6
    -> adjustment = 0.15/6 = 0.025 (원문 §3.4 캡션의 계산과 동일).
    """
    adj = _adj(total=1, accepted=1, rejected=0, missed=0)
    assert adj == 0.15 / 6
    assert adj < 0.15 * 0.5  # 원 부스트의 절반에도 한참 못 미친다


def test_shrink_approaches_raw_adjustment_monotonically_as_total_grows():
    """표본이 늘수록 조정값이 원 조정값(raw_adj=0.15, 전량 수용)에 단조 접근한다."""
    raw_adj = 0.15
    totals = [1, 5, 10, 50, 200, 10_000]
    adjustments = [_adj(total=t, accepted=t, rejected=0, missed=0) for t in totals]

    # 전부 raw_adj 아래에서 시작해 raw_adj 에 접근한다.
    for value in adjustments:
        assert 0.0 < value < raw_adj

    # 단조 증가.
    for earlier, later in zip(adjustments, adjustments[1:]):
        assert later > earlier

    # 표본이 아주 크면 raw_adj 에 근접한다(1% 이내).
    assert adjustments[-1] > raw_adj * 0.99


def test_smoothing_of_zero_still_behaves_like_no_smoothing_via_epsilon_floor():
    """feedback_smoothing 이 0 이하로 들어와도 0 나눗셈이 아니라 1e-9 바닥을 쓴다."""
    adj = _adj(total=10, accepted=10, rejected=0, missed=0, feedback_smoothing=0.0)
    # shrink = 10 / (10 + 1e-9) ~= 1.0 이므로 raw_adj 에 사실상 근접한다.
    assert adj == 0.15 * (10 / (10 + 1e-9))


# --- 3. 클램핑: 최종 점수는 항상 [0, 1] ---


def test_score_clamps_at_one_when_base_and_adjustment_overflow():
    assert apply_feedback_adjustment(base_score=0.95, feedback_adjustment=0.5) == 1.0


def test_score_clamps_at_zero_when_adjustment_is_deeply_negative():
    assert apply_feedback_adjustment(base_score=0.05, feedback_adjustment=-0.5) == 0.0


def test_score_within_bounds_is_untouched():
    assert apply_feedback_adjustment(base_score=0.4, feedback_adjustment=0.1) == 0.5


# --- 4. 피드백 0건은 정확히 0.0 ---


def test_zero_total_yields_exactly_zero_not_a_near_zero_artifact():
    adj = _adj(total=0, accepted=0, rejected=0, missed=0)
    assert adj == 0.0
    assert adj is not None


def test_zero_total_with_nonzero_counts_still_yields_exactly_zero():
    """total<=0 이면 accepted/rejected/missed 값이 남아 있어도 0.0 이다.

    운영에서는 나올 수 없는 조합(합계보다 세부 항목이 큰 경우)이지만, 방어적으로
    total<=0 을 유일한 게이트로 삼는다는 계약을 고정한다.
    """
    adj = _adj(total=0, accepted=3, rejected=1, missed=1)
    assert adj == 0.0


# --- 5. 민감도: 관측 1건이 목록을 뒤집을 수 있다 ---


def test_single_accepted_click_is_the_same_order_of_magnitude_as_live_candidate_gaps():
    """현재 데이터 규모의 경고를 수치로 고정한다.

    2026-08-30 라이브 조회에서 E11 약제 후보 confidence 는 0.0718 근방에 몰려
    있고 1위가 0.1105 였다(§3.4 실측, live). 표본 1건짜리 수용 피드백의
    조정값은 0.025 로, 이는 그 군집 폭(0.1105-0.0718=0.0387)의 절반을 넘는
    크기다. 즉 **클릭 한 번이 순위를 뒤집을 수 있다** — 결함이 아니라
    작은 표본에서 이 설계가 의도한 동작이지만, smoothing 상수를 나중에
    바꿀 사람에게 그 결과가 보이도록 여기 남긴다.
    """
    single_click_adjustment = _adj(total=1, accepted=1, rejected=0, missed=0)
    live_cluster_gap = 0.1105 - 0.0718

    assert single_click_adjustment > live_cluster_gap * 0.5
