"""진단서 소견을 premise 와 대조한다.

자유 산문이라 결정론적으로 잡을 수 있는 것이 얇다. 이 모듈이 실제로 검사하는
것은 정확히 다음 두 가지뿐이다.

1. `cited_code_known` — 소견 텍스트에서 **대괄호 [ ] 또는 소괄호 ( ) 로 감싼**
   ICD-10 형태 코드만 "인용"으로 본다(예: `[J00]`, `(E11.9)`). 괄호 없이 문장에
   섞여 있는 코드(`...E21.9으로...`)나 `비타민 B12` 같은 의학 약어는 이 검사의
   범위 밖이며, "인용이 없다"는 뜻으로 skipped 로 처리한다 — 검증했다는 뜻이
   아니다.
2. `premise_term_present` — premise(상병명·처방명)의 문자열이 소견 텍스트 안에
   부분 문자열로 "등장"하는지만 본다. 소견이 그 상병에 "대한" 것인지, 문맥상
   실제로 그 진단을 뒷받침하는지는 보지 않는다 — 짧은 premise 용어가 무관한
   복합어 안에 부분 문자열로 등장해도 ok 로 판정될 수 있다(알려진 한계).

문장 단위 함의 판정은 B(NLI)의 몫이다(spec §6.2).
"""
from __future__ import annotations

import re
import time
import unicodedata

from typing import Any, List, Optional, Sequence

from verification_contract import CheckResult, VerificationResult, aggregate_status

# 대괄호 또는 소괄호로 감싼 ICD-10 형태 코드만 인용으로 본다.
#
# certificate_agent.py 의 프롬프트가 상병을 `- [J00] 급성 비인두염` 형태로
# 제시하므로(certificate_agent.py:106 부근), 실제로 쓰이는 인용 형식은 괄호로
# 감싼 것이다. 경계를 괄호가 아니라 `\b` 로만 두면 두 방향으로 다 틀린다:
# 한글 음절은 Python 정규식에서 \w 로 취급되어 `\b` 가 한글-코드 경계에서
# 전혀 작동하지 않으므로 `...심근경색E21.9으로...` 같은 위조 코드를 놓치고,
# 반대로 `비타민 B12` 같은 정상적인 의학 약어를 코드로 오인해 flag 한다
# (spec §6.2). 괄호 한정은 이 두 오탐/누락을 모두 피하는 대신, 괄호 없는
# 인용은 이 검사의 범위 밖으로 명시적으로 둔다.
# 대소문자를 가리지 않고, 괄호 안 여백과 전각 괄호도 받는다.
# 대문자만 받으면 `[e21.9]` 같은 소문자 인용이 findall 에서 조용히 빠지고,
# 그러면 `[J00]` 하나만 걸린 채 "인용한 코드가 모두 premise 안에 있음" 이라는
# 적극적 거짓 진술이 나간다. 못 본 것을 봤다고 말하는 것이 가장 나쁘다.
BRACKETED_ICD10_PATTERN = re.compile(
    r"[\[(［（]\s*([A-Za-z]\d{2}(?:\.\d+)?)\s*[\])］）]"
)


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _normalize(value: str) -> str:
    """한글 NFC 정규화. NFC 와 NFD 는 화면상 같지만 코드포인트가 다르고,
    Arango 적재 경로나 입력기에 따라 어느 쪽으로도 premise 값이 들어올 수
    있어 정규화 없이 부분 문자열 비교하면 같은 용어가 불일치로 잡힌다
    (verification.py 의 _normalize_dosage 와 동일한 근거)."""
    return unicodedata.normalize("NFC", value)


# 문장 경계는 종결부호([.!?。]) 바로 뒤, 또는 줄바꿈이다.
#
# 다루는 것: 종결부호 뒤에 숫자가 바로 오면(가격·용량의 소수점, 예:
# "1.5mg") 문장 경계로 보지 않는다 — 그러지 않으면 소수점마다 문장이
# 쪼개져 NLI 2차 판정이 문장 수만큼 늘어나고, 예산은 요청 전체에 대한
# 것이라 사다리가 뒤집힌다(spec §8.4, CRITICAL 리뷰). 줄바꿈만 있고
# 종결부호가 없는 소견도 `\n+` 로 문장을 나눈다.
#
# 다루지 않는 것: 종결부호 바로 뒤에 공백 없이 숫자로 시작하는 다음
# 문장이 오면(예: "...완료했습니다.2026년...") 경계를 놓친다 — 그런
# 붙여쓰기 표기는 이 정규식의 범위 밖이다.
SENTENCE_SPLIT = re.compile(r"(?<=[.!?。])(?!\d)|\n+")

# 모델이 돌려주는 판정 문자열. 이 셋 밖의 값은 판정 실패로 본다 —
# 알 수 없는 응답을 통과로 읽으면 검증층이 스스로를 무력화한다.
_VERDICT_OK = "ENTAILMENT"
_VERDICT_BAD = {"CONTRADICTION", "NEUTRAL"}

# NLI 호출 예산의 기본값. 호출자가 넘기지 않을 때만 쓰인다 — 실제 운영
# 값은 certificate_api.NLI_TIMEOUT_SECONDS 가 결정하고, 호출부가 이를
# budget_seconds 로 명시적으로 넘긴다(아래 참조).
_DEFAULT_BUDGET_SECONDS = 30.0


def verify_certificate_nli(
    *,
    premise: str,
    text: str,
    call_llm,
    budget_seconds: float = _DEFAULT_BUDGET_SECONDS,
    clock=time.monotonic,
) -> List[CheckResult]:
    """소견 각 문장이 premise 에서 함의되는지 모델에게 묻는다(B(NLI), spec §6.2).

    검증기는 순수 함수로 남는다 — I/O 는 `call_llm` 으로 주입받는다(GC-1).
    호출 실패·타임아웃·알 수 없는 판정은 전부 skipped 다. 절대 ok 가 아니다
    (GC-2). `nli_entailment` 는 근거 검사다 — STRUCTURAL_CHECK_IDS 에 넣지
    않는다.

    `budget_seconds` 는 이 함수 호출 **전체**에 대한 예산이지, 문장마다
    새로 지급되지 않는다(CRITICAL 리뷰). `call_llm` 은 문장 하나당 게이트웨이
    왕복 하나이고, 각 왕복은 독립적으로 최대 그 정도 시간을 쓸 수 있다.
    사다리(게이트웨이 총예산 136.5s + NLI 예산 30s = 166.5s < 호출자 타임아웃
    180s, spec §8.4)는 요청당 게이트웨이 호출이 "하나 더" 붙는다는 전제로
    설계됐다 — 문장 수만큼 호출이 늘면 136.5 + 30×N 이 되어 사다리가
    뒤집힌다. 그래서 루프 시작 시점에 마감(deadline)을 한 번만 계산하고,
    이미 마감을 넘긴 뒤의 문장은 call_llm 을 아예 부르지 않고 skipped 로
    떨어뜨려 총 지연을 한 예산 안으로 묶는다. `clock` 은 `call_llm` 과 같은
    이유로 주입한다(GC-1) — 실시간이 흐르길 기다리지 않고도 이 판정 로직을
    테스트하기 위해서다.
    """
    if not premise.strip():
        return []

    sentences = [s.strip() for s in SENTENCE_SPLIT.split(text or "") if s and s.strip()]
    checks: List[CheckResult] = []
    deadline = clock() + budget_seconds
    for index, sentence in enumerate(sentences):
        target = f"sentence[{index}]"
        if clock() >= deadline:
            checks.append(CheckResult(
                id="nli_entailment", target=target, outcome="skipped",
                evidence="NLI 예산 소진으로 미검증(예산은 문장별이 아니라 요청 전체)"))
            continue
        try:
            verdict = str(call_llm(premise, sentence)).strip().upper()
        except Exception as exc:  # noqa: BLE001
            checks.append(CheckResult(
                id="nli_entailment", target=target, outcome="skipped",
                evidence=f"NLI 호출 실패: {type(exc).__name__}"))
            continue

        if verdict == _VERDICT_OK:
            outcome = "ok"
            evidence = "premise 에서 함의됨"
        elif verdict in _VERDICT_BAD:
            outcome = "flagged"
            evidence = f"판정: {verdict}"
        else:
            outcome = "skipped"
            evidence = f"알 수 없는 판정: {verdict!r}"
        checks.append(CheckResult(
            id="nli_entailment", target=target, outcome=outcome, evidence=evidence))
    return checks


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
    cited = BRACKETED_ICD10_PATTERN.findall(normalized_text)
    if not cited:
        checks.append(CheckResult(
            id="cited_code_known", target="certificate", outcome="skipped",
            evidence="소견에 괄호로 감싼 ICD-10 형태 코드가 없음"
                      "(괄호 없는 인라인 코드는 이 검사의 범위 밖)"))
    else:
        # 코드는 대문자로 비교한다. 상병코드의 대소문자는 표기 차이일 뿐이라
        # `[j00]` 을 premise 의 `J00` 과 다른 코드로 취급하면 오탐이 된다.
        upper_known = {c.upper() for c in known_codes}
        unknown = [c for c in cited if c.upper() not in upper_known]
        checks.append(CheckResult(
            id="cited_code_known", target="certificate",
            outcome="flagged" if unknown else "ok",
            evidence=(f"소견이 괄호로 인용한 코드 {cited} 중 premise 밖: {unknown}"
                      if unknown else
                      f"소견이 괄호로 인용한 코드 {cited} 가 모두 premise 안에 있음")))

    if not known_terms:
        checks.append(CheckResult(
            id="premise_term_present", target="certificate", outcome="skipped",
            evidence="premise 에 상병명·처방명이 없어 대조할 수 없음"))
    else:
        present = [t for t in sorted(known_terms) if _normalize(t) in normalized_text]
        checks.append(CheckResult(
            id="premise_term_present", target="certificate",
            outcome="ok" if present else "flagged",
            evidence=(f"premise 용어가 텍스트에 부분 문자열로 등장함: {present}"
                      "(등장했다는 뜻이지 그 상병에 대한 소견이라는 보장은 아님)"
                      if present else
                      "소견이 premise 의 상병명·처방명을 하나도 언급하지 않음")))

    return VerificationResult(
        status=aggregate_status(checks), checks=checks, skippedReason=skipped_reason)
