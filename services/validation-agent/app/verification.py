"""검증 에이전트 출력을 도구 관측값과 대조한다.

순수 함수만 둔다(GC-1). 출력을 변형하지 않는다(GC-3).
spec: Docs/superpowers/specs/2026-08-29-runtime-verification-design.md §6.3
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence

from app.verification_contract import CheckResult, VerificationResult, aggregate_status

PMID_PATTERN = re.compile(r"\b\d{7,8}\b")


def _code(row: Any) -> str:
    if not isinstance(row, dict):
        return ""
    value = row.get("prescription_code")
    if value is None:
        value = row.get("처방코드")
    return str(value).strip() if value is not None else ""


def verify_validation(
    *,
    pubmed_articles: Sequence[Dict[str, Any]],
    finder_candidates: Sequence[Dict[str, Any]],
    response_dict: Dict[str, Any],
) -> VerificationResult:
    checks: List[CheckResult] = []
    skipped_reason: Optional[str] = None

    # --- cited_pmid_in_evidence ---
    known_pmids = {str(a.get("pmid", "")).strip() for a in pubmed_articles}
    known_pmids.discard("")
    cited_text = " ".join([
        str(response_dict.get("pubmedEvidenceSummary") or ""),
        " ".join(str(c) for c in (response_dict.get("checks") or [])),
    ])
    cited = set(PMID_PATTERN.findall(cited_text))

    if not known_pmids:
        checks.append(CheckResult(
            id="cited_pmid_in_evidence", target="response", outcome="skipped",
            evidence="조회된 PubMed 논문이 없어 인용을 대조할 수 없음"))
    elif not cited:
        checks.append(CheckResult(
            id="cited_pmid_in_evidence", target="response", outcome="skipped",
            evidence="응답에 PMID 인용이 없음"))
    else:
        unknown = sorted(cited - known_pmids)
        checks.append(CheckResult(
            id="cited_pmid_in_evidence", target="response",
            outcome="flagged" if unknown else "ok",
            evidence=(f"조회 결과에 없는 PMID: {unknown}" if unknown
                      else f"인용 PMID {sorted(cited)} 가 모두 조회 결과에 있음")))

    # --- candidates_from_finder ---
    known_codes = {_code(r) for r in finder_candidates}
    known_codes.discard("")
    returned = response_dict.get("candidatePrescriptions") or []

    if not returned:
        checks.append(CheckResult(
            id="candidates_from_finder", target="response", outcome="skipped",
            evidence="반환된 후보 처방이 없음"))
    elif not known_codes:
        checks.append(CheckResult(
            id="candidates_from_finder", target="response", outcome="skipped",
            evidence="finder 관측값이 없어 대조할 수 없음"))
    else:
        outside = sorted({_code(r) for r in returned} - known_codes - {""})
        checks.append(CheckResult(
            id="candidates_from_finder", target="response",
            outcome="flagged" if outside else "ok",
            evidence=(f"finder 관측값 밖의 코드: {outside}" if outside
                      else f"후보 {len(returned)}건이 모두 finder 관측값에서 옴")))

    # --- trace_step_has_observation ---
    # 구조 검사다(STRUCTURAL_CHECK_IDS). 조회 데이터와 대조하지 않으므로
    # 이것만 통과해서는 passed 가 되지 않는다.
    trace = response_dict.get("reasoningTrace") or []
    if not trace:
        checks.append(CheckResult(
            id="trace_step_has_observation", target="response", outcome="skipped",
            evidence="트레이스가 비어 있음"))
    else:
        missing = [i for i, step in enumerate(trace)
                   if not isinstance(step, dict) or not step.get("observation")]
        checks.append(CheckResult(
            id="trace_step_has_observation", target="response",
            outcome="flagged" if missing else "ok",
            evidence=(f"관측값이 없는 스텝 인덱스: {missing}" if missing
                      else f"{len(trace)}개 스텝이 모두 관측값을 가짐")))

    if all(c.outcome == "skipped" for c in checks):
        skipped_reason = "도구 관측값이 없어 대조를 수행하지 못했습니다."

    return VerificationResult(
        status=aggregate_status(checks), checks=checks, skippedReason=skipped_reason)
