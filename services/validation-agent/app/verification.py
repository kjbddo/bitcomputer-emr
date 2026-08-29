"""검증 에이전트 출력을 도구 관측값과 대조한다.

순수 함수만 둔다(GC-1). 출력을 변형하지 않는다(GC-3).

`cited_pmid_in_evidence` 는 `PMID` 마커로 도입된 인용만 본다(대소문자
무관, 콜론·공백은 있어도 없어도 됨). 마커 없는 7~8자리 숫자(용량, 날짜 등)는
이 검사의 범위 밖이며 인용으로 보지 않는다 — 놓쳤다는 뜻이지 검증했다는
뜻이 아니다. certificate_verification.py 의 BRACKETED_ICD10_PATTERN 과
같은 이유로, 마커 뒤 숫자 경계는 `\\b` 가 아니라 ASCII 전용
lookahead/lookbehind 로 둔다: 파이썬 `re` 는 한글 음절도 `\\w` 로 취급해
`\\b` 가 숫자-한글 조사 경계에서 전혀 작동하지 않는다.

마커 하나가 쉼표·`·`·`및`·공백으로 구분된 id 목록 전체에 걸린다
(`PMID 11111111, 99999999`). 마커를 id 하나에만 결부시키면 목록의
두 번째 이후 id 는 전혀 추출되지 않아, 실재하는 id 뒤에 붙은 조작된
id 가 조회 결과와 대조조차 되지 않고 통과해버린다 — 이 검사가 막으려는
바로 그 실패다. 그래서 마커는 한 번만 매칭하고 그 뒤에 이어지는 id
목록 전체를 잡은 뒤, 그 구간에서 개별 id 를 모두 뽑아낸다.

spec: Docs/superpowers/specs/2026-08-29-runtime-verification-design.md §6.3
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence

from app.verification_contract import CheckResult, VerificationResult, aggregate_status

# PMID 마커로 도입된 인용만 대조한다(대소문자 무관, 마커와 숫자 사이 콜론·
# 공백은 있어도 없어도 됨). 마커 없는 7~8자리 숫자는 이 검사의 범위 밖이다 —
# 용량이나 날짜도 우연히 그 자릿수가 될 수 있고, 그런 숫자를 인용으로 잡으면
# 아무것도 인용하지 않은 응답에 할루시네이션 경보를 울리게 된다.
#
# 경계는 `\b` 대신 ASCII 전용 lookahead/lookbehind 로 둔다. 파이썬 `re` 는
# 한글 음절도 `\w` 로 취급해 `\b` 가 숫자-한글 조사 경계에서 전혀 작동하지
# 않는다(certificate_verification.py 의 BRACKETED_ICD10_PATTERN 문서와 같은
# 근거). 그 결과 `\b\d{7,8}\b` 는 두 방향으로 다 틀렸다: 공백 없이 조사가
# 붙은 정상 인용(`PMID 11111111을`)을 놓치고, 같은 자리에 붙은 위조 인용도
# 똑같이 놓친다 — 이 검사가 막으려던 바로 그 실패를 피해간다.
#
# 자릿수 범위(7~8)는 고정값이다. 넓히면 용량·날짜 같은 무관한 숫자를 다시
# 주워 담고, 좁히면 실제 PMID 형식을 놓친다 — 회귀 테스트로 양쪽 다 고정한다.
#
# 마커(PMID)는 뒤따르는 id 목록 전체에 한 번만 매칭한다 — id 하나하나에
# 마커를 요구하면 "PMID 11111111, 99999999" 같은 목록에서 두 번째 이후
# id 가 전혀 추출되지 않는다(마커가 없다는 이유로). 목록 구분자는 쉼표,
# `·`, `및`, 공백을 허용한다. 마지막 id 뒤 경계도 마커 뒤 첫 id 와 동일하게
# ASCII 전용 lookahead 로 막아, 자릿수 범위를 벗어나는 숫자가 목록에 이어
# 붙어도 그 앞부분만 잘라 먹지 않는다(뒤에 남은 숫자가 있으면 그 반복은
# 통째로 실패하고 그 전까지 확정된 id 들만 남는다).
PMID_PATTERN = re.compile(
    r"(?i)(?<![0-9A-Za-z])PMID\s*:?\s*"
    r"\d{7,8}(?:(?:\s*[,·]\s*|\s*및\s*|\s+)\d{7,8})*"
    r"(?![0-9A-Za-z])"
)
# 마커 매칭 구간에서 개별 id 를 뽑아내는 보조 패턴. 구분자는 숫자가 아니므로
# 이 패턴만으로 목록을 안전하게 쪼갤 수 있다.
_PMID_ID_PATTERN = re.compile(r"\d{7,8}")


def _code(row: Any) -> str:
    """행에서 처방 코드를 뽑는다. `prescription_code` 를 우선하고 없으면
    `처방코드` 로 fallback 한다 — 두 키 형태가 이 코드베이스에 실제로
    혼재한다(finder 관측값과 응답 후보가 서로 다른 키를 쓸 수 있음).
    dict 가 아닌 행은 코드를 뽑을 수 없어 "" 를 반환한다; 호출부는 그
    "코드 없음"을 "정상"과 구분해서 다룬다(malformed 행 참고)."""
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
    # ""를 버린다. pmid 필드가 없는(또는 빈) article 이 섞여 있으면 버리지
    # 않은 known_pmids 가 {""} 처럼 비어 있지 않은 집합이 돼 아래
    # `not known_pmids` 가드를 건너뛴다 — 그러면 실제로는 대조할 PMID가
    # 하나도 없는데도 "조회 결과 있음" 취급돼, 응답이 인용한 진짜 PMID가
    # 전부 "조회 결과 밖"으로 flag 된다(있어야 할 skipped 대신 오탐성
    # flagged). 죽은 코드가 아니라 이 가드의 전제조건이다.
    known_pmids.discard("")
    cited_text = " ".join([
        str(response_dict.get("pubmedEvidenceSummary") or ""),
        " ".join(str(c) for c in (response_dict.get("checks") or [])),
    ])
    cited: set = set()
    for marker_match in PMID_PATTERN.finditer(cited_text):
        cited.update(_PMID_ID_PATTERN.findall(marker_match.group()))

    if not known_pmids:
        checks.append(CheckResult(
            id="cited_pmid_in_evidence", target="response", outcome="skipped",
            evidence="조회된 PubMed 논문이 없어 인용을 대조할 수 없음"))
    elif not cited:
        checks.append(CheckResult(
            id="cited_pmid_in_evidence", target="response", outcome="skipped",
            evidence="응답에 PMID 마커로 표시된 인용이 없음"
                      "(마커 없는 숫자는 이 검사의 범위 밖)"))
    else:
        unknown = sorted(cited - known_pmids)
        checks.append(CheckResult(
            id="cited_pmid_in_evidence", target="response",
            outcome="flagged" if unknown else "ok",
            evidence=(f"조회 결과에 없는 PMID: {unknown}" if unknown
                      else f"인용 PMID {sorted(cited)} 가 모두 조회 결과에 있음")))

    # --- candidates_from_finder ---
    known_codes = {_code(r) for r in finder_candidates}
    # ""를 버린다. 코드 필드가 없는(또는 빈) finder 후보가 섞여 있으면 버리지
    # 않은 known_codes 가 {""} 처럼 비어 있지 않은 집합이 돼 아래
    # `not known_codes` 가드를 건너뛴다 — 그러면 대조할 코드가 실제로는
    # 하나도 없는데 "관측값 있음" 취급돼, 정상 후보가 전부 "finder 밖"으로
    # flag 된다(있어야 할 skipped 대신 오탐성 flagged). 죽은 코드가 아니라
    # 이 가드의 전제조건이다.
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
        # dict 가 아닌 행은 _code 가 "" 를 반환하고, 그대로 두면 `- {""}` 로
        # outside 계산에서 조용히 빠져 "정상"(ok) 취급된다. 형식이 깨진
        # 행은 대조하지 못했다는 뜻이지 검증됐다는 뜻이 아니다(GC-2) —
        # 그래서 malformed 행은 outside 와 별개로 flag 사유에 넣는다.
        malformed = [i for i, r in enumerate(returned) if not isinstance(r, dict)]
        outside = sorted({_code(r) for r in returned if isinstance(r, dict)}
                          - known_codes - {""})
        if malformed or outside:
            reasons = []
            if outside:
                reasons.append(f"finder 관측값 밖의 코드: {outside}")
            if malformed:
                reasons.append(f"형식이 잘못된 후보 인덱스: {malformed}")
            checks.append(CheckResult(
                id="candidates_from_finder", target="response", outcome="flagged",
                evidence="; ".join(reasons)))
        else:
            checks.append(CheckResult(
                id="candidates_from_finder", target="response", outcome="ok",
                evidence=f"후보 {len(returned)}건이 모두 finder 관측값에서 옴"))

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

    # aggregate 는 all(skipped) 보다 넓다 — 구조 검사(trace_step_has_observation)
    # 만 ok 이고 나머지가 skipped 여도 전체는 "skipped" 다(§5.1). all(...) 로
    # 판정하면 그 경우 skipped_reason 이 None 인 채로 status 만 "skipped" 가
    # 나가, 화면에는 "미확인"만 뜨고 이유가 안 붙는다.
    status = aggregate_status(checks)
    if status == "skipped":
        skipped_reason = "도구 관측값이 없어 대조를 수행하지 못했습니다."

    return VerificationResult(status=status, checks=checks, skippedReason=skipped_reason)
