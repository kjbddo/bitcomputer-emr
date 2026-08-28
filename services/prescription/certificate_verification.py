"""진단서 소견을 premise 와 대조한다.

자유 산문이라 결정론적으로 잡을 수 있는 것이 얇다. 잡히는 것은 "없는 상병코드를
인용했다"와 "근거로 삼았다는 상병을 한 번도 언급하지 않았다" 두 가지다.
문장 단위 함의 판정은 B(NLI)의 몫이다(spec §6.2).
"""
from __future__ import annotations

import re
import unicodedata

from typing import Any, List, Optional, Sequence

from verification_contract import CheckResult, VerificationResult, aggregate_status

# ICD-10 형태. "코드처럼 생긴 것"을 애매하게 두면 검사가 무엇을 하는지
# 아무도 말할 수 없게 된다(spec §6.2).
ICD10_PATTERN = re.compile(r"\b[A-Z]\d{2}(?:\.\d+)?\b")


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _normalize(value: str) -> str:
    """한글 NFC 정규화. NFC 와 NFD 는 화면상 같지만 코드포인트가 다르고,
    Arango 적재 경로나 입력기에 따라 어느 쪽으로도 premise 값이 들어올 수
    있어 정규화 없이 부분 문자열 비교하면 같은 용어가 불일치로 잡힌다
    (verification.py 의 _normalize_dosage 와 동일한 근거)."""
    return unicodedata.normalize("NFC", value)


def verify_certificate(
    *,
    diseases: Sequence[Any],
    diagnoses: Sequence[Any],
    text: str,
) -> VerificationResult:
    premise_entries = list(diseases) + list(diagnoses)
    known_codes = {_text(getattr(e, "code", "")) for e in premise_entries}
    known_codes.discard("")
    known_terms = {_text(getattr(e, "name", "")) for e in premise_entries}
    known_terms.discard("")

    has_premise = bool(known_codes or known_terms)
    checks: List[CheckResult] = []
    skipped_reason: Optional[str] = None

    if not has_premise:
        skipped_reason = "상병·처방 정보가 없어 소견을 대조하지 못했습니다."
        checks.append(CheckResult(
            id="cited_code_known", target="certificate", outcome="skipped",
            evidence="premise 가 비어 대조할 수 없음"))
        checks.append(CheckResult(
            id="premise_term_present", target="certificate", outcome="skipped",
            evidence="premise 가 비어 대조할 수 없음"))
        return VerificationResult(
            status=aggregate_status(checks), checks=checks, skippedReason=skipped_reason)

    normalized_text = _normalize(text or "")
    cited = ICD10_PATTERN.findall(normalized_text)
    if not cited:
        checks.append(CheckResult(
            id="cited_code_known", target="certificate", outcome="skipped",
            evidence="소견에 ICD-10 형태 토큰이 없음"))
    else:
        unknown = [c for c in cited if c not in known_codes]
        checks.append(CheckResult(
            id="cited_code_known", target="certificate",
            outcome="flagged" if unknown else "ok",
            evidence=(f"소견의 코드 {cited} 중 premise 밖: {unknown}" if unknown
                      else f"소견의 코드 {cited} 가 모두 premise 안에 있음")))

    if not known_terms:
        checks.append(CheckResult(
            id="premise_term_present", target="certificate", outcome="skipped",
            evidence="premise 에 상병명·처방명이 없어 대조할 수 없음"))
    else:
        present = [t for t in sorted(known_terms) if _normalize(t) in normalized_text]
        checks.append(CheckResult(
            id="premise_term_present", target="certificate",
            outcome="ok" if present else "flagged",
            evidence=(f"소견이 언급한 premise 용어: {present}" if present
                      else "소견이 premise 의 상병명·처방명을 하나도 언급하지 않음")))

    return VerificationResult(
        status=aggregate_status(checks), checks=checks, skippedReason=skipped_reason)
