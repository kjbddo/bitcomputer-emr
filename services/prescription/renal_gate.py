"""신기능 금기 관문 — 추천이 이 환자의 신기능에 금기인지 **경고**한다.

순수 함수만 둔다 — I/O 도 LLM 도 전역 상태도 쓰지 않는다(GC-1).
출력을 변형하지 않는다. 차단하지 않는다 — 표시하고 의사가 정한다.
spec: Docs/superpowers/specs/2026-08-30-ai-service-redesign-design.md §1.3, §3.3

## 왜 이 모듈이 있나

검증층(B1)은 **설계상 추적 가능성만 본다.** 출력의 모든 코드가 조회된 후보에서
왔으면 `passed` 다. §11.8.3 은 급성 충수염 양상에 진통제·정장제를 권한 응답이
정직하게 `passed` 를 받는 것을 실측으로 보였다 — 근거는 있고 임상적으로 틀렸다.
그 구멍을 LLM 이 자기 답을 검사하게 해서 메우지 않는다. 결정론적인 규칙이 한다.

**가설이 아니다.** 2026-08-31 라이브 그래프 실측:

    special_notes                                       1,025행
      신기능 표현(CKD/GFR/투석/신부전/신장)이 든 행         136행
      그중 visit_has_note 로 방문에 붙고 그 방문에
      9자리 약제 처방이 실제로 있는 행                      57행

    VISIT_530472595 (내원번호 530472595, 상병 E11)
      노트: [6ya / 6.4%['25.08]), DM-CKD, L-spine disc - 3등급 ...
      처방: 641600390 다이아벡스정500mg   <- 메트포르민
            662504840 플로가정10밀리그램(다파글리플로진...)
            693900170 레바트정(레바미피드)
            693902550 치옥셀정(티옥트산)

**CKD 환자에게 메트포르민이 실제로 나갔다.** 그 쌍이 이력에 있으므로 co-occurrence
랭킹은 그것을 배우고 다시 권한다.

## 세 결과는 서로 무너지지 않는다 (GC-3 fail-closed)

자유텍스트 파싱은 자주 실패한다. 그래서 세 결과를 갈라 두는 것이 이 부품의
전부다. "확인 못 함"이 "해당 없음"으로 렌더링되면 §1.3 의 구멍을 다른 모양으로
재현한다.

    warn     신기능 저하가 **확인**됐고 그 약이 신배설 금기 표에 있다
    clear    이 약이 표 밖이다 — 신기능 상태와 무관하게 이 금기는 해당 없음
    unknown  약은 표 안인데 신기능 상태를 확정하지 못했다
             (노트 없음 / 지표 없음 / `r/o` 같은 의심 표현)

`clear` 가 뜻하는 것은 **"이 표의 범위 안에서 해당 없음"** 이지 "안전함"이 아니다.
표는 아래에 적힌 대로 좁고 부분적이다. 항목별 evidence 문자열이 그 범위를
문장으로 들고 다닌다 — 화면이 evidence 를 버리고 outcome 만 쓰면 그 범위가
사라지므로, 렌더링은 반드시 evidence 를 함께 보여야 한다.

## `r/o` 를 의심으로 읽는 이유

`r/o CKD or CHF` 는 rule-out — **감별 대상이지 확진이 아니다.** 이 데이터셋에서
26행이 이 한 문장이다(전체 신기능 표현 136행의 19%).

확진으로 읽으면: 26행 전부가 경고가 되고, 경고가 흔해지면 GFR 13 짜리 진짜
경고가 그 안에 묻힌다. 신뢰할 수 없는 경고는 없는 경고보다 나쁘다.
해당 없음으로 읽으면: 노트가 명시적으로 "이 환자는 신장을 의심 중"이라고
적어 둔 것을 시스템이 "확인했고 문제없음"으로 바꿔 말하게 된다 — 이것이
정확히 금지된 붕괴다.

그래서 `suspected` 로 따로 잡아 `unknown` 으로 내보낸다. 화면에는 "확인 못 함"
으로 뜨고 evidence 에 `r/o` 가 실린다. 의사는 노트를 직접 읽고 판단한다.

## GFR 60 이상을 "정상"으로 확정하지 않는 이유

노트의 GFR 은 시점도 추세도 없이 숫자 하나로 적혀 있다(`eGFR 39.9` 옆에
6개월 뒤 `eGFR 36.3` 이 함께 적힌 노트가 있다). 한 값이 60 을 넘는다고
지금 신기능이 정상이라고 말할 수 없다. 그래서 60 이상은 지표로 세지 않고
`undetermined` 로 남긴다 — 상태를 확정하지 못한 것이지 정상인 것이 아니다.

## 무엇이 이 파서를 무효로 만드나

- `special_notes` 의 자유텍스트가 구조화 필드로 대체된다. 그때는 모양 추론을
  버리고 그 필드를 읽는 것이 옳다(medication_codes.py 와 같은 원칙).
- 원본 엑셀이 다른 병원 것으로 교체되어 표기 관행이 바뀐다.
- 검사 수치(Cr·cystatin C)만 적힌 노트가 생긴다. 지금은 Cr·cystatin 값을
  지표로 쓰지 않는다 — 성별·연령 보정 없이 신기능을 판정할 수 없고, 이
  데이터셋에서 그 값이 적힌 노트는 **전부 GFR 값을 함께 담고 있어** GFR
  경로로 잡히기 때문이다. 그 전제가 깨지면 여기부터 다시 본다.

재현:

    FOR n IN special_notes
      LET t = TO_STRING(n.`특이사항_norm`)
      FILTER REGEX_TEST(UPPER(t), "CKD|GFR|투석|신부전|신장")
      RETURN t
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional, Sequence, Tuple

RenalLevel = Literal["impaired", "suspected", "undetermined"]
GateOutcome = Literal["warn", "clear", "unknown"]

# 심각도 순서. status 집계와 "unknown 이 clear 로 무너지지 않는다"가 둘 다
# 이 한 줄에 걸린다.
_OUTCOME_SEVERITY: Dict[str, int] = {"clear": 0, "unknown": 1, "warn": 2}

# GFR 임계. 60 미만이면 CKD 3기 이상이다(KDIGO 2012 CKD 가이드라인의 G3a
# 경계). 이 값 하나만 상수로 둔다 — 메트포르민 금기선(30)이나 감량선(45)을
# 쓰지 않는 이유는, 관문의 출력이 "이 약을 쓰지 마라"가 아니라 "신기능을 보고
# 판단하라"이기 때문이다. 더 넓은 선이 그 목적에 맞는다.
GFR_IMPAIRED_BELOW = 60.0


# ---------------------------------------------------------------------------
# 약물 표 — 성분 기준이다. 코드 접두로 가르지 않는다.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RenalDrug:
    """신기능 저하에서 금기이거나 용량 조절이 필요한 성분 하나.

    ``name_tokens`` 는 **이 데이터셋의 order_lines 에 실제로 등장하는 문자열**
    에서 뽑았다. 성분명(`메트포르민`)과 상품명(`다이아벡스`)이 섞여 있는데,
    이 데이터셋의 처방명 중 상당수가 성분을 괄호로 밝히지 않기 때문이다
    (`다이아벡스정500mg`, `자누메트정50/500mg`, `케이메트서방정(내복)`).
    """

    ingredient: str
    label: str
    risk: str
    name_tokens: Tuple[str, ...]


# 2026-08-31 라이브 그래프 실측으로 만든 표.
#
# 만드는 규칙: order_lines 의 9자리 약제 코드 678개(distinct code+name)를 전부
# 뽑아 놓고, 그중 **신기능 저하에서 금기이거나 용량 조절이 필수인 성분**만
# 골라 넣었다. 아래 name_tokens 는 전부 그 678개 문자열에 실제로 걸리며,
# 걸리지 않는 다른 약에 잘못 걸리는 토큰은 0건이다(위양성 0 — 재현은 이
# 파일 아래 `## 표 검증` 참조).
#
# **일부러 넣지 않은 것들** — 이 표가 키워드 덤프가 아니라는 증거:
#
#   SGLT2 억제제(다파글리플로진 `플로가정`·`자디앙정`)  신기능 저하에서
#     오히려 신보호 목적으로 쓴다(DAPA-CKD). 경고하면 그것이 오탐이다.
#   제미글립틴(`제미글로정`)  DPP-4 중 신기능에 따른 용량 조절이 필요 없는
#     쪽이다. 같은 계열이라고 묶으면 안 된다.
#   푸로세미드(`라식스정`)  신기능 저하에서 쓰는 약이지 피하는 약이 아니다.
#
# **채웠던 빈 자리**(2026-08-31 재검토): `메모틴정10mg` 18행
# (코드 693901500). 원래는 "알면서 비운 자리"였다 — 메만틴 제제로 알려져
# 있으나 이 데이터셋의 처방명·`prescription_masters.canonical_name` 어느
# 쪽도 성분을 문자 그대로 밝히지 않았기 때문이다. 재검토하며 **간접** 증거
# 셋을 확인해 채웠다:
#
#   1. 처방명 자체가 급여기준을 담고 있다: `메모틴정10mg(MMSE20점이하,
#      GDS 4-7점)`. 국내 치매약 급여기준에서 MMSE 20 이하 + GDS 4-7 은
#      **메만틴** 기준이다 — 도네페질 급여기준(MMSE 10-26)과 다르다.
#   2. 같은 그래프에 **같은 10mg 용량**의, 성분을 괄호로 명시한 메만틴
#      형제 제품이 있다: `디멘틴정_(메만틴염산염/ 10mg/1정)`(코드
#      661900170, 메모틴과 다른 코드). `메만시아정10mg(메만틴염산염)`·
#      `영일메만틴정(메만틴염산염)`·`만티니정(메만틴염산염)` 도 전부 10mg
#      짜리다 — 이 데이터셋에서 10mg 메만틴 제제가 흔하다는 뜻이다.
#   3. 이 데이터셋의 도네페질 제제는 하나도 빠짐없이 성분을 괄호로
#      명시한다(`알로페질정5mg(도네페질염산염)`, `환인도네페질정23밀리그램
#      (도네페질염산염수화물)` 등). 메모틴이 무표기 도네페질일 가능성은
#      낮다 — 그랬다면 이 데이터셋의 관행과 어긋난다.
#
# **이것이 무엇이 아닌지가 중요하다.** 이것은 약물 데이터베이스나 원본
# 성분 컬럼의 직접 진술이 **아니다.** 급여기준 문자열 해석 + 동일 용량
# 형제 제품 존재 + 이 데이터셋의 표기 관행이라는 세 정황 증거를 겹쳐서 낸
# 추론이다. 증거 강도는 "확인됨"보다 낮고 "짐작"보다는 높다 — 다음에 이
# 자리를 다시 판단할 사람은 위 세 줄만 보고 그 판단을 다시 내릴 수 있어야
# 한다. 원본에 성분 컬럼이 직접 생기면 그것으로 이 추론을 교체한다.
#
# 이런 종류의 자리가 또 남아 있을 수 있다 — 이 표는 급여기준 문자열을
# 전수 조사해 다시 훑은 것이 아니라 이 하나의 알려진 빈 자리만 다시 봤다.
RENAL_CLEARED_DRUGS: Tuple[RenalDrug, ...] = (
    RenalDrug(
        ingredient="metformin",
        label="메트포르민",
        risk="신기능 저하에서 젖산산증 위험. eGFR 30 미만 금기, 30~45 감량·재평가",
        name_tokens=("메트포르민", "다이아벡스", "메트폴", "케이메트", "자누메트"),
    ),
    RenalDrug(
        ingredient="sitagliptin",
        label="시타글립틴",
        risk="주로 신배설. CrCl 에 따라 100→50→25mg 감량",
        name_tokens=("시타글립틴", "자누메트", "자누엠", "시타글로"),
    ),
    RenalDrug(
        ingredient="memantine",
        label="메만틴",
        risk="신배설. CrCl 5~29 에서 1일 10mg 로 감량",
        # "메모틴" 은 성분을 직접 밝히지 않는 상품명이다 — 근거는 이 튜플
        # 위 "채웠던 빈 자리" 주석 참조(급여기준 + 동일 용량 형제 제품 추론).
        name_tokens=("메만틴", "메모틴"),
    ),
    RenalDrug(
        ingredient="levetiracetam",
        label="레비티라세탐",
        risk="약 66%가 미변화체로 신배설. CrCl 구간별 감량",
        name_tokens=("레비티라세탐", "레티람", "큐팜"),
    ),
    RenalDrug(
        ingredient="pregabalin",
        label="프레가발린",
        risk="거의 전량 미변화체로 신배설. CrCl 60 미만부터 감량",
        name_tokens=("프레가발린", "프로카반"),
    ),
    RenalDrug(
        ingredient="spironolactone",
        label="스피로노락톤",
        risk="칼륨보존 이뇨제 — 신기능 저하에서 고칼륨혈증 위험",
        name_tokens=("스피로노락톤", "스피로닥톤", "알닥톤"),
    ),
    RenalDrug(
        ingredient="nsaid",
        label="NSAID(록소프로펜·아세클로페낙·세레콕시브)",
        risk="신혈류 감소로 급성 신손상 유발. 만성 신질환에서 회피 권고",
        name_tokens=(
            "록소프로펜",
            "아세클로페낙",
            "세레콕시브",
            "락소펜",
            "휴로펜",
            "룩펠",
            "아펜정",
            "쎄렉스타",
            "쎄레메드",
            "쎄레브렉스",
        ),
    ),
    RenalDrug(
        ingredient="digoxin",
        label="디곡신",
        risk="신배설 + 좁은 치료역 — 신기능 저하에서 축적·중독",
        name_tokens=("디곡신", "디고신"),
    ),
    RenalDrug(
        ingredient="aminoglycoside",
        label="아미노글리코사이드(아미카신·겐타마이신)",
        risk="직접적 신독성 + 신배설. 신기능 저하에서 투여간격 조정 필수",
        name_tokens=("아미카신", "겐타마이신", "겐타프로"),
    ),
    RenalDrug(
        ingredient="levofloxacin",
        label="레보플록사신",
        risk="주로 신배설. CrCl 50 미만부터 용량·간격 조정",
        name_tokens=("레보플록사신", "크라비트"),
    ),
    RenalDrug(
        ingredient="cimetidine",
        label="시메티딘",
        risk="주로 신배설. 신기능 저하에서 감량, 크레아티닌 분비 경쟁",
        name_tokens=("시메티딘",),
    ),
)

## 표 검증 (2026-08-31 라이브 ArangoDB) — 위양성 0건.
##
##     FOR ol IN order_lines
##       FILTER REGEX_TEST(TRIM(TO_STRING(ol.`처방코드_norm`)), "^[0-9]{9}$")
##       COLLECT code = ol.`처방코드_norm`, name = ol.`처방명_norm`
##       RETURN {code, name}
##
## 위 678행을 위 name_tokens 로 훑으면 매칭 49행이 나오고(2026-08-31 재검토로
## `메모틴` 토큰을 더한 뒤 재측정 — 이전에는 47행이었다), 49행 전부가 해당
## 성분의 제제다. 다른 성분의 약이 잘못 걸린 행은 없다.


def match_renal_cleared_drug(name: Any) -> Optional[RenalDrug]:
    """처방명이 신배설 금기 표의 어느 성분인가. 아니면 ``None``.

    판정 불가를 예외로 만들지 않는다(GC-4) — ``None``·비문자열은 ``None`` 이다.
    표 순회 순서가 곧 반환 순서다(``RENAL_CLEARED_DRUGS`` 는 튜플이다) —
    복합제가 두 성분에 걸릴 때 어느 쪽이 나올지 결정론적이어야 한다.
    """
    if name is None or isinstance(name, (list, tuple, dict, set)):
        return None
    text = str(name)
    if not text.strip():
        return None
    for drug in RENAL_CLEARED_DRUGS:
        for token in drug.name_tokens:
            if token in text:
                return drug
    return None


# ---------------------------------------------------------------------------
# 자유텍스트 파싱
# ---------------------------------------------------------------------------

_HTML_TAG = re.compile(r"<[^>]*>")

# 확진 지표. 이 데이터셋에서 관측된 표기만 담는다.
#
# `신부전` 과 `심부전`(심장)은 첫 글자가 다르다 — 두 단어가 한 노트에 나란히
# 적힌 행이 실재하므로(`심부전 신부전 갑상선 항진증`) `부전` 으로 자르면 안 된다.
# `신우신염`(신장 감염)은 여기에 걸리지 않는다. 감염은 신기능 저하가 아니다.
_CONFIRMED_PATTERNS: Tuple[str, ...] = (
    # CKD + 뒤따르는 병기·날짜까지 증거로 붙인다: CKDIV, CKD(3b, 24'.08), DM-CKD
    r"CKD\s*(?:\([^)]{0,20}\)|[IVX]{1,4}\b|[1-5][ab]?\b)?",
    r"\bESRD\b",
    r"chronic\s+kidney\s+disease",
    r"renal\s+(?:failure|insufficiency|impairment)",
    # 신부전 4/5단계, 신부전4기, 만성신부전
    r"(?:만성\s*)?신부전\s*(?:[1-5](?:\s*/\s*[1-5])?\s*(?:단계|기))?",
    r"말기\s*신부전",
    r"만성\s*신장병|만성\s*신질환|신장질환",
    r"신[장기]?기능\s*(?:저하|감소|이상)",
    r"(?:혈액|복막)?투석|\bdialysis\b",
)

_CONFIRMED_RE = re.compile(
    "|".join(f"(?:{pattern})" for pattern in _CONFIRMED_PATTERNS),
    re.IGNORECASE,
)

# GFR / eGFR 수치. `\be?GFR\b` — "eGFR" 안의 "GFR" 은 앞이 단어문자라
# `\bGFR` 로 잡히지 않는다. 두 표기를 한 패턴으로 받는다.
_GFR_RE = re.compile(r"\be?GFR\b\s*[:=]?\s*(\d{1,3}(?:\.\d+)?)", re.IGNORECASE)

# 의심 표현. 확진 지표 **바로 앞** 창 안에서만 본다.
# `h/o`(history of)는 넣지 않는다 — 그것은 과거의 확진이지 의심이 아니다.
_SUSPECT_BEFORE = re.compile(r"(?:r\s*/\s*o|rule\s+out|suspect\w*|의심|추정)\s*$", re.IGNORECASE)
_SUSPECT_AFTER = re.compile(r"^\s*(?:\?|의심|추정|r\s*/\s*o)", re.IGNORECASE)
_SUSPECT_WINDOW = 16


@dataclass(frozen=True)
class RenalStatus:
    level: RenalLevel
    evidence: str


def _normalize_note(raw: Any) -> str:
    """HTML 조각과 엔티티를 걷어낸다.

    노트 다수가 EMR 리치텍스트에서 그대로 실려 와 `<span style="...">` 와
    `&gt;` 를 달고 있다. 태그 안 속성값(`rgb(102, 185, 102)`)이 숫자를
    품고 있어서, 걷어내지 않으면 수치 파싱이 그것을 볼 수 있다.
    """
    if raw is None or isinstance(raw, (list, tuple, dict, set)):
        return ""
    text = _HTML_TAG.sub(" ", str(raw))
    return html.unescape(text)


def _is_suspected(text: str, start: int, end: int) -> bool:
    before = text[max(0, start - _SUSPECT_WINDOW) : start]
    after = text[end : end + _SUSPECT_WINDOW]
    return bool(_SUSPECT_BEFORE.search(before) or _SUSPECT_AFTER.search(after))


def parse_renal_status(notes: Any) -> RenalStatus:
    """자유텍스트 노트에서 신기능 상태를 읽는다.

    못 읽는 것이 정상이다. 못 읽었을 때 "금기 없음"이 아니라 ``undetermined``
    를 돌려주는 것이 이 함수의 계약 전부다(GC-3).
    """
    if notes is None:
        return RenalStatus("undetermined", "노트 없음")
    if isinstance(notes, (str, bytes)):
        notes = [notes]

    confirmed: List[str] = []
    suspected: List[str] = []
    saw_any_text = False

    for raw in notes:
        text = _normalize_note(raw)
        if not text.strip():
            continue
        saw_any_text = True

        for m in _CONFIRMED_RE.finditer(text):
            snippet = " ".join(m.group(0).split())
            if _is_suspected(text, m.start(), m.end()):
                # 증거에 왜 의심으로 내렸는지를 함께 싣는다 — outcome 만 보고
                # 뒤에서 "확인 못 함"의 이유를 되짚을 수 없게 되면 안 된다.
                bucket, snippet = suspected, f"r/o {snippet}"
            else:
                bucket = confirmed
            if snippet not in bucket:
                bucket.append(snippet)

        for m in _GFR_RE.finditer(text):
            try:
                value = float(m.group(1))
            except ValueError:  # pragma: no cover - 정규식이 이미 숫자만 준다
                continue
            if value >= GFR_IMPAIRED_BELOW:
                # 60 이상 한 값은 정상을 확정하지 않는다. 지표로 세지 않고
                # 넘어간다 — 상태를 확정하지 못한 것이지 정상인 것이 아니다.
                continue
            snippet = " ".join(m.group(0).split())
            bucket = suspected if _is_suspected(text, m.start(), m.end()) else confirmed
            if snippet not in bucket:
                bucket.append(snippet)

    if confirmed:
        return RenalStatus("impaired", "; ".join(confirmed))
    if suspected:
        return RenalStatus(
            "suspected",
            "; ".join(suspected) + " — rule-out 표기는 확진이 아닙니다",
        )
    if saw_any_text:
        return RenalStatus("undetermined", "노트에 신기능 지표가 없습니다")
    return RenalStatus("undetermined", "노트 없음")


# ---------------------------------------------------------------------------
# 관문
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RenalGateItem:
    rank: Optional[int]
    name: str
    prescription_code: str
    outcome: GateOutcome
    ingredient: Optional[str]
    evidence: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rank": self.rank,
            "name": self.name,
            "prescriptionCode": self.prescription_code,
            "outcome": self.outcome,
            "ingredient": self.ingredient,
            "evidence": self.evidence,
        }


@dataclass(frozen=True)
class RenalGateResult:
    status: GateOutcome
    renalStatus: RenalLevel
    renalEvidence: str
    items: Tuple[RenalGateItem, ...]
    undeterminedReason: Optional[str] = None

    def __post_init__(self) -> None:
        # verification_contract.VerificationResult 와 같은 이유: frozen=True 는
        # 전달받은 리스트가 나중에 바뀌는 것을 막지 못한다. status 와 모순되는
        # items 를 갖는 결과가 만들어질 수 있었다.
        object.__setattr__(self, "items", tuple(self.items))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "renalStatus": self.renalStatus,
            "renalEvidence": self.renalEvidence,
            "items": [i.to_dict() for i in self.items],
            "undeterminedReason": self.undeterminedReason,
        }


_ITEM_NAME_KEYS = ("name", "처방명", "prescription_name", "canonical_name")
_ITEM_CODE_KEYS = ("prescription_code", "처방코드", "code")


def _field(item: Any, keys: Sequence[str]) -> str:
    for key in keys:
        if isinstance(item, dict):
            value = item.get(key)
        else:
            value = getattr(item, key, None)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _rank(item: Any) -> Optional[int]:
    value = item.get("rank") if isinstance(item, dict) else getattr(item, "rank", None)
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _is_placeholder(name: str, code: str) -> bool:
    # ranking 을 import 하지 않는다 — 이 모듈은 순수하게 유지하고, 대신 조회층이
    # 빈 순위에 쓰는 리터럴을 여기서 직접 안다. 값이 갈라지면
    # test_placeholder_item_is_not_warned_on 이 잡는다.
    return code == "미기재" or name.startswith("데이터 부족")


def evaluate_renal_gate(*, notes: Any, items: Any) -> RenalGateResult:
    """추천 항목마다 신기능 금기를 판정한다. 차단하지 않고 경고만 한다.

    Args:
        notes: 이 환자의 ``special_notes.특이사항_norm`` 문자열들. 조회가
            실패했으면 빈 리스트를 준다 — 그 경우 표 안의 약은 ``unknown``
            이 되지 ``clear`` 가 되지 않는다.
        items: 응답에 실릴 추천 항목(dict 또는 PrescriptionItem).
    """
    renal = parse_renal_status(notes)
    rows = list(items or [])

    gate_items: List[RenalGateItem] = []
    for item in rows:
        name = _field(item, _ITEM_NAME_KEYS)
        code = _field(item, _ITEM_CODE_KEYS)

        if _is_placeholder(name, code):
            gate_items.append(
                RenalGateItem(
                    rank=_rank(item),
                    name=name,
                    prescription_code=code,
                    outcome="clear",
                    ingredient=None,
                    evidence="추천 항목이 없는 순위입니다 — 대조할 약이 없습니다.",
                )
            )
            continue

        drug = match_renal_cleared_drug(name)
        if drug is None:
            gate_items.append(
                RenalGateItem(
                    rank=_rank(item),
                    name=name,
                    prescription_code=code,
                    outcome="clear",
                    ingredient=None,
                    evidence=(
                        f"신배설 금기 표({len(RENAL_CLEARED_DRUGS)}개 성분)에 없는 "
                        f"성분입니다 — 이 표의 범위 안에서 해당 없음."
                    ),
                )
            )
            continue

        if renal.level == "impaired":
            gate_items.append(
                RenalGateItem(
                    rank=_rank(item),
                    name=name,
                    prescription_code=code,
                    outcome="warn",
                    ingredient=drug.ingredient,
                    evidence=(
                        f"{drug.label}: {drug.risk}. "
                        f"특이사항에서 확인된 신기능 지표: {renal.evidence}"
                    ),
                )
            )
            continue

        gate_items.append(
            RenalGateItem(
                rank=_rank(item),
                name=name,
                prescription_code=code,
                outcome="unknown",
                ingredient=drug.ingredient,
                evidence=(
                    f"{drug.label}: {drug.risk}. "
                    f"이 환자의 신기능을 확정하지 못했습니다 ({renal.evidence}) — "
                    f"'해당 없음'이 아닙니다."
                ),
            )
        )

    if not gate_items:
        return RenalGateResult(
            status="unknown",
            renalStatus=renal.level,
            renalEvidence=renal.evidence,
            items=(),
            undeterminedReason="판정할 추천 항목이 없습니다",
        )

    status = max(gate_items, key=lambda i: _OUTCOME_SEVERITY[i.outcome]).outcome
    return RenalGateResult(
        status=status,
        renalStatus=renal.level,
        renalEvidence=renal.evidence,
        items=tuple(gate_items),
    )
