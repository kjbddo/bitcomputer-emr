"""검증 에이전트 출력을 도구 관측값과 대조한다.

순수 함수만 둔다(GC-1). 출력을 변형하지 않는다(GC-3).

무관, 콜론·공백은 있어도 없어도 됨). 마커 없는 7~8자리 숫자(용량, 날짜 등)는
이 검사의 범위 밖이며 인용으로 보지 않는다 — 놓쳤다는 뜻이지 검증했다는
뜻이 아니다. certificate_verification.py 의 BRACKETED_ICD10_PATTERN 과
같은 이유로, 마커 뒤 숫자 경계는 `\\b` 가 아니라 ASCII 전용
lookahead/lookbehind 로 둔다: 파이썬 `re` 는 한글 음절도 `\\w` 로 취급해
`\\b` 가 숫자-한글 조사 경계에서 전혀 작동하지 않는다.

하나에만 결부시키면 목록의 두 번째 이후 id 는 전혀 추출되지 않아,
실재하는 id 뒤에 붙은 조작된 id 가 조회 결과와 대조조차 되지 않고
통과해버린다 — 이 검사가 막으려는 바로 그 실패다. 그래서 마커는 한 번만
매칭하고 그 뒤에 이어지는 id 목록 전체를 잡은 뒤, 그 구간에서 개별 id 를
모두 뽑아낸다.

목록 구분자는 쉼표·`·`·`및`처럼 열거해서 정의하지 않는다. 열거는 반드시
뚫린다 — `/`·`;`·공백 없이 붙는 조사(`와`/`과`) 처럼 열거에 없는 구분자가
하나라도 있으면 그 뒤의 조작된 id 가 조용히 숨는다. 대신 구분자를 "모양"
으로 정의한다: 선택적 공백, 그 다음 ASCII 영숫자도 공백도 아닌 문자
정확히 1개, 그 다음 선택적 공백. 이 한 규칙이 실제로 쓰이는 구분자
(`,` `·` `/` `;` `및` `와` `과`)를 전부 포괄한다 — 전부 한 글자이기
때문이다. 그리고 순수 공백에는 그 "특수문자 1개"가 없으므로 규칙을
만족하지 못해, 공백만으로는 목록이 이어지지 않는다 — 인용 바로 뒤에
1234567 mg`) 목록에 딸려 들어가지 않는다(이전 라운드가 지운 오탐이
"구분자 = 공백"으로 되돌아오는 것을 막는다). 같은 이유로 산문도 걸러진다:
"정확히 1개"를 만족하지 못하기 때문이다. 두 글자 이상의 틈은 목록을
끊는다.

**알려진 한계 — 이 검사는 정규식 휴리스틱이고, 오탐 방향이 열려 있다.**
구분자를 "모양"으로 정의한 대가로, 문장 부호와 목록 접속사를 구별하지
못한다. 실재 인용 바로 뒤에 특수문자 하나만 두고 무관한 7~8자리 숫자가
한글 조사·한자 한 글자가 전부 같은 결과를 낸다.

이 방향은 의도적으로 안전한 쪽이다 — 조작된 인용이 통과하는 일은 네 차례
리뷰에서 어떤 입력으로도 재현되지 않았고(GC-2 유지), 넘치는 쪽으로만
틀린다. 다만 정밀도 비용은 실재한다. 이걸 정확히 닫으려면 "두 숫자 사이의
토큰이 문맥에서 목록 접속사로 기능하는가"를 알아야 하는데, 그건 문자
분류로는 얻을 수 없는 정보다. 구분자를 열거하면 빠뜨린 것에 뚫리고,
모양으로 정의하면 문장 경계를 삼킨다 — 정규식으로는 두 방향을 동시에
닫을 수 없다. 그 판정은 spec §8 의 NLI(기본 off) 가 맡는다.

spec: Docs/superpowers/specs/2026-08-29-runtime-verification-design.md §6.3
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence

from app.verification_contract import CheckResult, VerificationResult, aggregate_status



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
    finder_candidates: Sequence[Dict[str, Any]],
    response_dict: Dict[str, Any],
) -> VerificationResult:
    checks: List[CheckResult] = []
    skipped_reason: Optional[str] = None

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
        #
        # 코드가 빈 dict 행(_code 가 "" 반환 — 키가 없거나 값이 빈 문자열)도
        # 대조 불가다(최종 리뷰 C2-b). dict 이므로 malformed 에는 안 걸리고,
        # outside 계산은 `- {""}` 로 그 행 자체를 지워 버려 무엇과도 대조되지
        # 않았는데 "N건이 모두 finder 관측값에서 옴"이라는 evidence 에 그대로
        # 섞여 들었다 — 검사가 실제로 확인한 것보다 evidence 가 더 많이
        # 주장하는, 이 브랜치에서 반복된 결함 유형이다.
        #
        # 다만 결과는 flagged 가 아니라 skipped 다(최종 리뷰 IMP-1). flagged 의
        # 화면 문구는 "근거 불일치" — 출력이 근거와 어긋난다는 뜻인데, 코드가
        # 없는 행은 어긋나는 것이 아니라 대조할 대상이 없는 것이고 그건
        # skipped 의 정의다. 같은 행을 prescription 검증기는 이미 skipped 로
        # 분류하고 있어(verification.py 의 _PLACEHOLDER_VALUES) 두 서비스가
        # 갈려 있었다. 정직한 출력에 "근거 불일치"를 띄우면 §11.3·I1 에서 두 번
        # 걷어낸 오탐이 세 번째 서비스에서 되살아난다.
        malformed = [i for i, r in enumerate(returned) if not isinstance(r, dict)]
        uncoded = [i for i, r in enumerate(returned)
                   if isinstance(r, dict) and not _code(r)]
        outside = sorted({_code(r) for r in returned if isinstance(r, dict)}
                          - known_codes - {""})
        if malformed or outside:
            reasons = []
            if outside:
                reasons.append(f"finder 관측값 밖의 코드: {outside}")
            if malformed:
                reasons.append(f"형식이 잘못된 후보 인덱스: {malformed}")
            # 진짜 불일치와 같은 응답에 섞여 있으면 그 사실도 함께 적는다.
            if uncoded:
                reasons.append(f"코드가 없어 대조하지 못한 후보 인덱스: {uncoded}")
            checks.append(CheckResult(
                id="candidates_from_finder", target="response", outcome="flagged",
                evidence="; ".join(reasons)))
        elif uncoded:
            # 대조한 행이 일부 있어도 ok 를 내지 않는다. ok 는 "반환된 후보가
            # 전부 관측값에서 왔다"는 주장인데, 이 행들은 확인하지 못했다.
            checks.append(CheckResult(
                id="candidates_from_finder", target="response", outcome="skipped",
                evidence=f"코드가 없어 대조하지 못한 후보 인덱스: {uncoded}"))
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
