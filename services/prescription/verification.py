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

spec: Docs/superpowers/specs/2026-08-29-runtime-verification-design.md §6.1
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from verification_contract import CheckResult, VerificationResult, aggregate_status


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
    schema_ok = (
        None not in raw_ranks
        and sorted(raw_ranks) == [1, 2, 3]
        and len(set(codes)) == len(codes)
    )
    checks.append(
        CheckResult(
            id="schema_top3",
            target="response",
            outcome="ok" if schema_ok else "flagged",
            evidence=f"rank={raw_ranks} 코드중복={len(codes) - len(set(codes))}건",
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

        if confidence is None:
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
