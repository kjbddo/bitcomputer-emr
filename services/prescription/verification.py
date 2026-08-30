"""처방 추천 출력을 조회 결과와 대조한다.

순수 함수만 둔다(GC-1). 출력을 변형하지 않는다(GC-3).
근거가 없으면 통과가 아니라 미확인이다(GC-2).

용량(dosage) 대조 검사는 제거되었다. 실측(spec §11.1,
scripts/measure_verification.py) 결과 10개 시나리오 30건 전부
skipped 였고, 원인은 상류에 용량 데이터 자체가 없기 때문이다:
run_prescription_agent.py 의 후보 조회 AQL RETURN 절, 이 파일이
읽는 packages/graph-etl/graph_normalize.py 의 CANONICAL_COLS,
그리고 그 원본인 packages/graph-etl 의
20260406_상병별 처방코드 추출_특이사항 추가.xlsx 세 곳 모두 용량
개념이 없다. 쿼리나 키 조회를 넓혀서 고칠 수 있는 문제가 아니라서
제거했다. 용량 데이터가 확보되면 새로 설계해 다시 추가할 것.

confidence_in_range 검사는 커밋 9289321 에서 한 번 제거됐다가 복구됐다.
제거 사유("prescription_agent.py 프롬프트가 confidence_score 를 요구하지
않아 값이 항상 None")는 **사실이 아니었다**. 이 값을 채우는 것은 LLM 이
아니라 prescription_api.py 다 — Arango co-occurrence 조회
(fetch_confidence_scores_by_diagnosis_codes -> confidence_by_code, :473-489)
결과를 처방코드로 매칭해 it.confidence_score 에 주입하고(:710-719), 그
주입은 _safe_verify 호출(:736)보다 먼저 실행된다. 180건 전부 skipped 로
나온 실측은 ArangoDB 에 컬렉션이 하나도 없고 시나리오의 유일한
상병코드(M2556)가 그래프에 존재하지도 않던 환경에서 돌았기 때문이다
(spec §11.3 의 [환경 조건]). 그래프를 적재하고 그래프에 실재하는
상병코드로 부르면 값이 실제로 채워진다. dosage_verbatim(상류 데이터
자체가 없어 발화 불가)과 같은 부류가 아니다 — 그 판단이 틀렸다.

confidence_in_range 는 구조 검사다(STRUCTURAL_CHECK_IDS). 0..1 범위만
보고 조회된 어떤 데이터와도 대조하지 않으므로, 이 검사의 ok 하나로
passed 가 나가면 안 된다(GC-2).

한계(M-4): prescription_api.py:719 는
`it.confidence_score = confidence_by_code.get(code, 0.0)` 로 주입한다.
모델이 고른 코드가 co-occurrence 조회 결과에 없을 때도 정확히 0.0 이
주입되므로, 이 검사는 "실제로 조회돼 0.0 이 나온 값"과 "조회 결과에
없어서 폴백된 0.0"을 구분하지 못하고 둘 다 ok 로 판정한다. 값 자체를
바꾸는 수정이 아니라 이 한계를 기록만 해 둔다 — 이 검사의 ok 가
"co-occurrence 결과 안에 실제로 있었다"는 뜻까지는 보증하지 않는다는
점을 후속 독자가 과대 해석하지 않도록.

code_in_candidates·name_matches_code 는 모델이 "미기재" 류 플레이스홀더로
근거 없음을 정직하게 신고한 경우를 flagged 가 아니라 skipped 로 다룬다.
60 시나리오 실측에서 code_in_candidates 의 flagged 22건 전부가 리터럴
"미기재" 였고 지어낸 코드는 0건이었다 — 정직한 거절을 근거 불일치로
보고하면 안 된다. 지어낸 것처럼 보이지만 후보에 없는 코드는 여전히
flagged 다(§10.1 변이 테스트 표의 test_invented_code_is_flagged 참조).

schema_top3 의 코드중복 조건도 같은 플레이스홀더를 면제한다(최종 리뷰
I1). 애초에 이 면제가 빠져 있어서, 모델이 세 추천 중 둘 이상에 "미기재"를
정직하게 쓴 경우(코드가 없다는 뜻)가 "코드중복"으로 flag 됐다 — §11.5 의
60% 수치에 이 오탐이 섞여 있었다(§11.4/§11.5 재측정 참조). rank 집합
조건은 이 면제와 무관하며 그대로 둔다.

code_is_medication 은 추천된 처방코드가 이 데이터셋의 약제 코드 형태인지만
본다(medication_codes.py 가 규칙을 소유한다). 조회 데이터와 대조하지 않으므로
구조 검사다(STRUCTURAL_CHECK_IDS) — 이 ok 하나로 passed 가 나가면 안 된다.
후보가 아니라 출력 항목을 대상으로 하는 이유는 아래 검사 본문의 주석에 있다.
근거: .superpowers/sdd/agent-architecture-review.md F-H1.

spec: Docs/superpowers/specs/2026-08-29-runtime-verification-design.md §6.1, §11.2
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from medication_codes import is_medication_code
from verification_contract import CheckResult, VerificationResult, aggregate_status

# 모델이 근거 없음을 정직하게 신고할 때 쓰는 고정 문자열들.
# prescription_agent.py 의 프롬프트 본문(임의 목록이 아니라 실제 지시문에서
# 뽑은 값)이 출처다:
#   - "미기재": prescription_code 필드 폴백(44행), dosage 필드 폴백(45행),
#     sparse override 섹션의 prescription_code 폴백(133행)
#   - "데이터 부족": top_rx 가 비었을 때 name 필드 안내문의 어근
#     (46행, "데이터 부족: top_rx 비어 있음" 등)
#   - "데이터에 용량 없음": dosage 필드 폴백(45, 134행)
#   - "": 필드 자체가 채워지지 않은 경우
# 이 값들은 지어낸 코드·이름이 아니라 "낼 근거가 없다"는 모델의 정직한
# 신고다 — flagged(근거 불일치)가 아니라 skipped(미검증)로 다룬다.
_PLACEHOLDER_VALUES = frozenset({"미기재", "데이터 부족", "데이터에 용량 없음", ""})


def _row_code(row: Any) -> str:
    """후보 행의 처방코드. 두 키 형태가 실제로 공존한다."""
    if not isinstance(row, dict):
        return ""
    value = row.get("prescription_code")
    if value is None:
        value = row.get("처방코드")
    return str(value).strip() if value is not None else ""


def _row_name(row: Any) -> str:
    if not isinstance(row, dict):
        return ""
    value = row.get("prescription_name")
    if value is None:
        value = row.get("처방명")
    return str(value).strip() if value is not None else ""


def _index_candidates(candidates: Sequence[Any]) -> Dict[str, Dict[str, str]]:
    index: Dict[str, Dict[str, str]] = {}
    for row in candidates:
        code = _row_code(row)
        if not code:
            continue
        index.setdefault(code, {"name": _row_name(row)})
    return index


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _safe_int(value: Any) -> Optional[int]:
    """숫자로 변환할 수 없으면 예외 대신 None 을 반환한다(GC-4)."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_float(value: Any) -> Optional[float]:
    """숫자로 변환할 수 없으면 예외 대신 None 을 반환한다(GC-4)."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def verify_prescriptions(*, candidates: Sequence[Any], items: Sequence[Any]) -> VerificationResult:
    index = _index_candidates(candidates)
    has_candidates = bool(index)
    checks: List[CheckResult] = []

    # 구조 검사 — 조회 데이터 없이도 판정된다.
    # rank 가 숫자로 변환되지 않으면(예: "first") 예외를 던지는 대신
    # 스키마 위반으로 취급한다 — 어차피 {1,2,3} 집합에 속할 수 없다(GC-4).
    raw_ranks = [_safe_int(getattr(i, "rank", None)) for i in items]
    codes = [_text(getattr(i, "prescription_code", "")) for i in items]
    # 중복 판정은 실제 코드끼리만 본다. "미기재" 류 플레이스홀더는
    # code_in_candidates/name_matches_code 와 같은 이유로 여기서도 면제한다
    # (최종 리뷰 I1) — 프롬프트가 지어내지 말고 플레이스홀더를 쓰라고 명시적으로
    # 지시하는데, 그 지시를 두 번 따른 정직한 출력("미기재","미기재")이 "코드
    # 중복"으로 flag 되면 §11.3 이 code_in_candidates 에서 고친 바로 그 오탐이
    # 다른 검사로 되돌아온다. 실제 코드의 중복은 여전히 flag 해야 하므로
    # comparable_codes(플레이스홀더 제외)로만 집합 크기를 비교한다.
    comparable_codes = [c for c in codes if c not in _PLACEHOLDER_VALUES]
    duplicate_count = len(comparable_codes) - len(set(comparable_codes))
    schema_ok = (
        None not in raw_ranks
        and sorted(raw_ranks) == [1, 2, 3]
        and duplicate_count == 0
    )
    checks.append(
        CheckResult(
            id="schema_top3",
            target="response",
            outcome="ok" if schema_ok else "flagged",
            evidence=f"rank={raw_ranks} 코드중복={duplicate_count}건",
        )
    )

    for item in items:
        rank = _text(getattr(item, "rank", ""))
        target = f"prescription[{rank}]"
        code = _text(getattr(item, "prescription_code", ""))
        name = _text(getattr(item, "name", ""))
        confidence = getattr(item, "confidence_score", None)

        if not has_candidates:
            checks.append(CheckResult(
                id="code_in_candidates", target=target, outcome="skipped",
                evidence="조회된 후보가 없어 대조할 수 없음"))
            checks.append(CheckResult(
                id="name_matches_code", target=target, outcome="skipped",
                evidence="조회된 후보가 없어 대조할 수 없음"))
        elif code in _PLACEHOLDER_VALUES:
            # 모델이 코드를 기재하지 않았다(정직한 신고) — 후보가 없어서
            # 못 대조하는 것과는 다른 이유의 skipped 다. "미기재"가 우연히
            # 후보 색인에 없어 flagged 로 새는 것을 여기서 막는다.
            checks.append(CheckResult(
                id="code_in_candidates", target=target, outcome="skipped",
                evidence=f"모델이 처방코드를 기재하지 않음(플레이스홀더 {code!r})"))
            checks.append(CheckResult(
                id="name_matches_code", target=target, outcome="skipped",
                evidence="처방코드가 플레이스홀더라 이름을 대조할 수 없음"))
        else:
            matched = index.get(code)
            checks.append(CheckResult(
                id="code_in_candidates", target=target,
                outcome="ok" if matched else "flagged",
                evidence=f"코드 {code!r} 가 후보 {len(index)}건 중 " +
                         ("있음" if matched else "없음")))

            if matched is None:
                checks.append(CheckResult(
                    id="name_matches_code", target=target, outcome="skipped",
                    evidence="코드가 후보에 없어 이름을 대조할 수 없음"))
            elif name in _PLACEHOLDER_VALUES:
                # 코드는 실제 후보와 일치했지만 이름 필드가 플레이스홀더인
                # 드문 경우 — 문자열 동등 비교로 넘기면 "이름을 기재하지
                # 않음"이 "이름이 후보와 다름"(flagged)으로 잘못 보고된다.
                checks.append(CheckResult(
                    id="name_matches_code", target=target, outcome="skipped",
                    evidence=f"모델이 처방명을 기재하지 않음(플레이스홀더 {name!r})"))
            else:
                expected_name = matched["name"]
                if not expected_name:
                    checks.append(CheckResult(
                        id="name_matches_code", target=target, outcome="skipped",
                        evidence="후보 행에 처방명이 없어 대조할 수 없음"))
                else:
                    checks.append(CheckResult(
                        id="name_matches_code", target=target,
                        outcome="ok" if expected_name == name else "flagged",
                        evidence=f"후보 {expected_name!r} vs 출력 {name!r}"))

        # code_is_medication — 추천된 코드가 약제 코드인가(F-H1).
        #
        # 구조 검사다(STRUCTURAL_CHECK_IDS). 코드 문자열의 모양만 보고 조회된
        # 어떤 데이터와도 대조하지 않으므로, 이 ok 하나로 passed 가 나가면
        # 안 된다(GC-2).
        #
        # 후보가 아니라 **출력 항목**을 대상으로 한다. 후보를 대상으로 쓰면
        # 조회 AQL 이 이미 약제만 올리므로 구조적으로 발화할 수 없는 검사가
        # 된다 — 제거된 dosage_verbatim 과 같은 부류다. 출력 항목을 보면
        # Arango 를 우회하는 경로에서 실제로 발화한다: 요청이 top_rx 를 직접
        # 주면(시나리오 fixture, 상류 서비스가 채운 목록) 그 후보에는 무엇이든
        # 들어올 수 있고 모델은 §11.8.2 대로 그것을 충실히 추천한다.
        # F-H1 의 라이브 관측(AL801·AA254·KK052)이 정확히 그 모양이다.
        if code in _PLACEHOLDER_VALUES:
            # 코드를 기재하지 않은 것은 "약이 아니다" 가 아니라 판정 불가다.
            # §11.3(code_in_candidates)·최종 리뷰 I1(schema_top3)이 두 번
            # 걷어낸 오탐 — 정직한 신고를 근거 불일치로 보고하면 안 된다.
            checks.append(CheckResult(
                id="code_is_medication", target=target, outcome="skipped",
                evidence=f"모델이 처방코드를 기재하지 않음(플레이스홀더 {code!r})"))
        elif is_medication_code(code):
            checks.append(CheckResult(
                id="code_is_medication", target=target, outcome="ok",
                evidence=f"코드 {code!r} 가 약제 코드 형태(9자리 숫자)"))
        else:
            checks.append(CheckResult(
                id="code_is_medication", target=target, outcome="flagged",
                evidence=f"코드 {code!r} 는 약제 코드 형태가 아님 — "
                         "이 데이터셋에서 수가·검사·처치·재료 코드다"))

        if confidence is None:
            # Arango co-occurrence 주입이 일어나지 않았다(그래프가 비었거나
            # 이 상병코드에 co-occurrence 가 없다). 대조할 것이 없으므로
            # 통과가 아니라 미검증이다(GC-2).
            checks.append(CheckResult(
                id="confidence_in_range", target=target, outcome="skipped",
                evidence="confidence_score 없음"))
        else:
            safe_confidence = _safe_float(confidence)
            if safe_confidence is None:
                # 값이 아예 숫자로 변환되지 않는 경우는 "근거가 없어 판정 불가"
                # (skipped) 가 아니라 "출력 형식 자체가 잘못됨" (flagged) 이다 —
                # 범위를 벗어난 숫자와 같은 취급이다(GC-4: 예외 대신 판정으로).
                checks.append(CheckResult(
                    id="confidence_in_range", target=target, outcome="flagged",
                    evidence=f"confidence_score={confidence!r} 가 숫자가 아님"))
            else:
                in_range = 0.0 <= safe_confidence <= 1.0
                checks.append(CheckResult(
                    id="confidence_in_range", target=target,
                    outcome="ok" if in_range else "flagged",
                    evidence=f"confidence_score={safe_confidence}"))

    skipped_reason: Optional[str] = None
    if not has_candidates:
        skipped_reason = "조회된 처방 후보가 없어 근거 대조를 수행하지 못했습니다."

    return VerificationResult(
        status=aggregate_status(checks),
        checks=checks,
        skippedReason=skipped_reason,
    )
