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

## 스무딩 상수 도출 — `feedback_smoothing = 10`, 실측 간격 분포에서 뽑았다

`feedback_smoothing` 은 원래 5 였다. `total=1`(전량 수용)일 때 그 값은
`0.15 * (1/6) = 0.025` 였다. 이 값 자체는 작지만, **실제 후보 목록의
순위 간격과 비교해야 의미가 있다** — 그래서 아홉 개 상병코드 전체의
confidence 후보 목록에서 인접 순위 간 간격(gap)을 쟀다:

    상병   confidence 상위 값                       인접 gap
    A15    0.5000  0.5000  0.5000  ...               0.0000  0.0000  0.0000
    C34    0.1250  0.1250  0.1250  ...               0.0000  0.0000  0.0000
    D50    0.2414  0.1379  0.1379  ...               0.1034  0.0000  0.0000
    E03    0.1198  0.1042  0.0885  0.0573  ...        0.0156  0.0156  0.0313
    E11    0.1105  0.0718  0.0718  ...                0.0387  0.0000  0.0000
    I10    0.0624  0.0541  0.0499  0.0478  ...        0.0083  0.0042  0.0021
    J18    0.2500  0.2500  0.2500  ...                0.0000  0.0000  0.0000
    J90    0.2308  0.2115  0.2115  ...                0.0192  0.0000  0.0000

    24개 인접 gap · 15개가 정확히 0(동점) · 동점이 아닌 9개: median 0.0156,
    min 0.0021, max 0.1034

**여기서 뽑은 원칙:** 관측 1건이 동점을 깨는 것은 유용한 신호다 —
24개 인접 쌍 중 15개(5/8)가 실제로 동점이니 흔한 상황이다. 하지만 관측
1건이 **검색이 이미 만들어 놓은 진짜 간격**(median 0.0156 같은)을 뒤집으면
안 된다. 반대로 **일관된 피드백**(관측 몇 건)이 쌓이면 그 간격을 넘어설 수
있어야 한다 — 그래야 피드백이 실제로 쓸모가 있다.

이 원칙을 median 값(0.0156)에 대고 `feedback_smoothing` 을 검증하면:

    total=1, accepted=1 -> 0.15 * (1/(1+10)) = 0.15/11 = 0.013636...
      < median(0.0156)  -> 관측 1건은 넘지 못한다. 동점만 깬다.
    total=3, accepted=3 -> 0.15 * (3/(3+10)) = 0.45/13 = 0.034615...
      > median(0.0156)  -> 관측 3건(일관된 수용)은 넘어선다.

`smoothing=10` 은 이 두 부등식을 동시에 만족하는 값이다(`total=2` 도 이미
0.025 > median 을 넘는다 — "몇 건"의 문턱은 2~3건 근처다). `smoothing=5`
였다면 관측 1건(0.025)이 이미 median 을 넘어 **검색 간격을 클릭 한 번이
뒤집었을 것**이다 — 그것이 상수를 올린 이유다. `tests/test_feedback_adjustment.py`
의 "5. 스무딩 상수가 실측 간격 분포와 맞는가" 절이 두 부등식을 모두 고정한다.

**이것은 전망(prospective)이다.** 지금 `history_recommended_prescription`
에는 유효 피드백이 0건이다(위 "지금 쌓인 데이터는 이 조정에 효과가 없다"
참조) — 그러니 이 상수 변경은 **오늘의 순위를 하나도 바꾸지 않는다.**
피드백이 실제로 쌓이기 시작할 때를 대비해 미리 방향을 정해 둔 것이다.
"""
from __future__ import annotations

_EPSILON = 1e-9

# 도출 과정은 위 "스무딩 상수 도출" 절 전체를 본다 — 숫자만 옮기면 다음
# 사람이 왜 10인지 재판단할 수 없다. prescription_api.py 의
# CONFIDENCE_FEEDBACK_SMOOTHING 환경변수 기본값과 run_prescription_agent.py
# 의 fetch_confidence_scores_by_diagnosis_codes 기본 인자가 둘 다 이 상수를
# 가져다 쓴다 — 리터럴을 두 곳에 복제하지 않는다.
DEFAULT_FEEDBACK_SMOOTHING = 10.0


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
