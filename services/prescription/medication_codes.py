"""이 데이터셋에서 "약제 처방코드" 를 가리는 규칙 한 곳.

순수 함수만 둔다 — I/O 도 LLM 도 전역 상태도 쓰지 않는다(GC-1).
spec: Docs/superpowers/specs/2026-08-29-runtime-verification-design.md
리뷰 근거: .superpowers/sdd/agent-architecture-review.md F-H1

## 왜 이 모듈이 있나

`order_lines`(6,809행)는 처방 그래프의 후보 출처인데, 그 다수가 약이 아니라
**진찰료·방문료 같은 수가 라인과 검사 결과 성분**이다. 최빈 20개 항목에 약이
한 건도 없다. §11.8.2 가 실측으로 확인한 대로 이 모델은 건네받은 후보 밖으로
나가지 않으므로, **후보 품질이 곧 답 품질**이다. 실제로 J18(폐렴) 요청에
`AL801`(의약품관리료)·`AA254`(재진진찰료)·`KK052`(정맥내점적주사)가 "AI 추천
처방" 세 건으로 화면까지 갔고, 세 코드 전부 조회된 후보에서 왔으므로 검증은
정직하게 `passed` 를 냈다.

## 규칙

**이 데이터셋에서 처방코드가 약제인 것과 그것이 9자리 숫자인 것은 동치다.**

`처방코드_norm` 이 정확히 9자리 숫자면 약제(국민건강보험 약제 급여목록의
EDI 코드 형태)이고, 그 밖의 모든 형태는 수가·검사·처치·재료다.

## 이것이 이 데이터셋의 성질이라는 것 — 실측 (2026-08-30, 라이브 ArangoDB)

    order_lines                                     6,809행
    9자리 숫자 코드                                  2,983행  (distinct 657)
      그중 비약제 키워드(진찰료·관리료·검사·촬영·
      판독·방문료·처치·입원료·상담·촉탁 …)에 걸린 행      0행
    9자리 숫자가 아닌 코드                           3,826행
      그중 약제 제형 키워드(서방정·캡슐·시럽·연고·
      주사액·점안·크림·현탁액·밀리그램 …)에 걸린 행       3행

즉 위양성 0건, 위음성 3건(6,809행의 0.04%)이다. 위음성 3행은 원내 임의 코드를
달고 들어온 약이다:

    7771       (비)훼로바-유서방정
    LAEN       라에넥주사액
    W32950011  라에넥주사액

이 세 행은 후보에서 빠지고, 같은 규칙을 쓰는 `code_is_medication` 검사에서도
`flagged` 가 된다. 필터와 검사가 같은 규칙을 쓰기 때문에 둘의 판정은 언제나
같은 방향으로 틀린다 — 걸러진 것이 조용히 통과하는 일은 없다.

접두 `'6'` 규칙이 아닌 이유: 9자리 약제 코드 중 2,929행은 `6` 으로 시작하지만
54행은 `0` 으로 시작한다(`073000850 리플록신정500mg`, `051600131 라미실크림1%`,
`052400511 메게이트현탁액` …). `'6'` 만 보면 이 54행이 조용히 사라진다.

## 무엇이 이 규칙을 무효로 만드나

이것은 **이 데이터셋의 코딩 체계에 대한 성질**이지 보편 규칙이 아니다.
다음 중 하나라도 사실이 되면 여기부터 다시 봐야 한다.

- `packages/graph-etl` 의 원본 엑셀이 다른 병원/다른 코드 체계로 교체된다.
- 약제 코드 자릿수가 바뀐다(현행 EDI 약제 코드는 9자리).
- 수가·검사 코드에 9자리 순수 숫자 형태가 도입된다.
- `order_lines` 에 `line_type` 같은 1급 분류 필드가 실제로 적재된다.
  그때는 이 모양 규칙을 버리고 그 필드를 읽는 것이 옳다 — 모양으로 추론하는
  것보다 데이터가 스스로 말하게 하는 편이 언제나 낫다.

재현:

    FOR o IN order_lines
      LET c = TRIM(TO_STRING(o.`처방코드_norm`))
      COLLECT drug = REGEX_TEST(c, "^[0-9]{9}$") WITH COUNT INTO n
      RETURN {drug, n}
"""
from __future__ import annotations

import re
from typing import Any

# AQL 의 REGEX_TEST 와 파이썬 re 가 같은 문자열을 쓴다. 조회에서 걸러지는
# 집합과 검사가 판정하는 집합이 갈라지면, 필터에 걸린 행이 검사에서는
# 통과하는(또는 그 반대의) 모순이 생긴다.
MEDICATION_CODE_REGEX = r"^[0-9]{9}$"

# 조회 AQL 이 정규식을 바인드 변수로 받는 키. 쿼리 문자열에 정규식을
# 끼워 넣지 않는다 — 쿼리 텍스트는 정적으로 두고 규칙은 이 모듈이 소유한다.
MEDICATION_CODE_BIND_KEY = "med_code_re"

# 조회 AQL 에 넣는 술어 조각. `{code}` 에 코드 표현식을 넣어 쓴다.
# 예: MEDICATION_CODE_AQL_PREDICATE.format(code="ol.`처방코드_norm`")
#
# 필터를 파이썬 후처리가 아니라 AQL 에 두는 이유: `LIMIT` 이 필터 뒤에
# 적용돼야 한다. 후처리로 거르면 `LIMIT 80` 이 수가·검사 라인 80행을 먼저
# 가져오고 그중 약제 몇 건만 남아, 후보 수가 조용히 말라붙는다.
MEDICATION_CODE_AQL_PREDICATE = (
    "REGEX_TEST(TRIM(TO_STRING({code})), @" + MEDICATION_CODE_BIND_KEY + ")"
)

_MEDICATION_CODE_PATTERN = re.compile(MEDICATION_CODE_REGEX)


def is_medication_code(code: Any) -> bool:
    """처방코드가 이 데이터셋의 약제 코드 형태인가.

    판정 불가를 예외로 만들지 않는다(GC-4). ``None``·빈 문자열·플레이스홀더
    ("미기재" 등)·리스트 같은 비문자열은 전부 ``False`` 다 — 다만 호출부는
    "약이 아님(flagged)" 과 "판정할 코드가 없음(skipped)" 을 구분해야 하므로,
    플레이스홀더 여부는 이 함수가 아니라 호출부가 먼저 가른다.
    """
    if code is None or isinstance(code, (list, tuple, dict, set)):
        return False
    return bool(_MEDICATION_CODE_PATTERN.fullmatch(str(code).strip()))
