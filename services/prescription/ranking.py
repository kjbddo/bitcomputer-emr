"""추천 순위를 조회 결과가 정한다. 모델은 설명만 쓴다.

spec: Docs/superpowers/specs/2026-08-30-ai-service-redesign-design.md §3.1

순수 함수만 둔다(GC-1) — I/O 도 LLM 도 전역 상태도 쓰지 않는다.

**왜 옮기는가.** 2026-08-30 라이브 6 시나리오 실측에서 모델의 rank 순서를
`confidence_score` 와 대조했다:

    A15   일치     r1=0.5000  r2=0.5000  r3=0.5000   <- 세 값이 같아 공허
    C34   일치     r1=0.1250  r2=0.1250  r3=0.1250   <- 세 값이 같아 공허
    D50   어긋남   r1=0.2414  r2=0.0345  r3=0.1379
    E03   어긋남   r1=0.1042  r2=0.0885  r3=0.1198
    E11   어긋남   r1=0.0387  r2=0.0442  r3=0.0387
    E78   confidence 없음 (약제 후보 0건 — 가정이 아니라 실제)

confidence 가 순서를 가르는 4건 전부 모델의 순서가 confidence 와 어긋났고
진짜 일치는 0건이다. **다만 이것을 과대 해석하지 않는다** — 값이 전반적으로
낮고 동점이 흔해서 이 데이터셋에서 confidence 는 약한 순서 신호다. 근거는
"confidence 가 더 잘 고른다"가 **아니라** §3.1 이 적은 셋이다:

1. 순위가 결정론적·감사 가능해진다("40명 중 23명이 받았습니다")
2. 코드 중복이 구조적으로 불가능해진다(§11.5 가 기록한 실제 결함)
3. 피드백 전/후 비교가 모델 변동에 오염되지 않는다(§6)

**동점 파기.** confidence 내림차순 → 후보 목록에서 처음 등장한 위치 오름차순.
후보 목록 자체가 결정론적이다(방문 처방은 `처방시퀀스_norm` 순, 코호트는
빈도 내림차순). 그래서 이 파기는 임의값이 아니라 조회가 이미 매긴 순서다.
`confidence_by_code` 의 dict 순회 순서는 정렬 키에 절대 들어가지 않는다 —
AQL 결과 행 순서는 동점에서 보장되지 않으므로, 그것이 새어 들어오면 같은
데이터에 같은 질의를 해도 화면 순서가 달라진다.

**점수 없음은 0.0 이 아니다.** 조회에 없는 코드는 `None` 으로 남기고 정렬에서
점수 있는 후보들 **뒤로** 보낸다. 모름을 0.0 으로 채우면 실제로 0.0 이 조회된
후보와 구분되지 않고(M-4 가 기록한 한계 — 순위가 이 값에 걸리는 순간 한계가
아니라 결함이 된다), 모름을 위로 올리면 없는 근거를 주장하게 된다(GC-3).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Mapping, Optional, Sequence

SLATE_SIZE = 3

# 후보 행에서 실제로 공존하는 키 형태들. verification._row_code/_row_name 과
# 같은 이유로 한 가지로 통일할 수 없다 — Arango 방문 조회는 한글 키,
# 코호트 변환과 상류 서비스는 영문 키를 쓴다.
_NAME_KEYS = ("처방명", "prescription_name", "canonical_name", "name")
_CODE_KEYS = ("처방코드", "prescription_code", "code")

# 조회 후보가 없는 순위. 모델이 아니라 조회층이 직접 쓴다 — 빈 자리를 모델의
# 문장으로 채우면 그것이 곧 §11.8.2 의 퇴화(같은 약 반복)나 지어내기가 된다.
NO_CANDIDATE_NAME = "데이터 부족: 조회된 처방 후보 없음"
NO_CANDIDATE_CODE = "미기재"
NO_CANDIDATE_DOSAGE = "미기재"
NO_CANDIDATE_REASON = (
    "이 순위에 올릴 조회 후보가 없습니다. 조회 결과가 뒷받침하지 않는 처방은 "
    "채우지 않습니다."
)

# 순위가 무엇에 근거했는지. 응답 계약은 건드리지 않고 toolTrace·로그로만 남긴다.
# 항목별 진실은 각 항목의 confidence_score(None 이면 근거 없음)에 이미 있다.
RANKING_STRATEGY_CONFIDENCE = "confidence"
RANKING_STRATEGY_CANDIDATE_ORDER = "candidate_order"
RANKING_STRATEGY_NO_CANDIDATES = "no_candidates"


@dataclass(frozen=True)
class RankedCandidate:
    """조회가 확정한 한 순위. 모델은 이 값을 바꾸지 못한다."""

    rank: int
    name: str
    prescription_code: str
    confidence_score: Optional[float]
    candidate_index: int

    def to_prompt_row(self) -> dict:
        return {
            "rank": self.rank,
            "name": self.name,
            "prescription_code": self.prescription_code,
            "confidence_score": self.confidence_score,
        }


def _row_value(row: Any, keys: Sequence[str]) -> str:
    if not isinstance(row, dict):
        return ""
    for key in keys:
        value = row.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text and text != NO_CANDIDATE_CODE:
            return text
    return ""


def _lookup_confidence(
    confidence_by_code: Mapping[str, Any], code: str
) -> Optional[float]:
    """조회 결과에 실제로 있을 때만 숫자를 돌려준다.

    없으면 None(모름)이고 0.0 이 아니다. 값이 숫자로 변환되지 않아도 모름이다 —
    예외를 던지는 대신 판정 불가로 다룬다(GC-4).
    """
    if not code or code not in confidence_by_code:
        return None
    try:
        return float(confidence_by_code[code])
    except (TypeError, ValueError):
        return None


def build_ranked_slate(
    candidates: Sequence[Any],
    confidence_by_code: Mapping[str, Any],
    *,
    size: int = SLATE_SIZE,
) -> List[RankedCandidate]:
    """후보 목록과 confidence 조회 결과에서 확정 순위를 만든다.

    - 처방코드(없으면 처방명)로 중복을 접는다. 같은 코드가 order_line 여러
      행에 나오는 것은 정상이므로, 접지 않으면 한 약이 여러 순위를 차지한다.
      §11.5 가 기록한 중복 추천이 여기서 구조적으로 불가능해진다.
    - 정렬은 (점수 있음 먼저, 점수 내림차순, 후보 첫 등장 위치 오름차순).
      셋째 키가 유일하므로 이 순서는 전순서다 — 같은 입력이면 항상 같은 출력.
    """
    entries: List[tuple[int, str, str]] = []
    seen: set[str] = set()
    for index, row in enumerate(candidates or []):
        code = _row_value(row, _CODE_KEYS)
        name = _row_value(row, _NAME_KEYS)
        if not code and not name:
            # 안내용 note 한 줄({"note": "데이터 부족: ..."}) 같은 행이다.
            continue
        identity = code or name
        if identity in seen:
            continue
        seen.add(identity)
        entries.append((index, code, name or code))

    def sort_key(entry: tuple[int, str, str]) -> tuple[int, float, int]:
        index, code, _name = entry
        score = _lookup_confidence(confidence_by_code, code)
        if score is None:
            return (1, 0.0, index)
        return (0, -score, index)

    entries.sort(key=sort_key)

    out: List[RankedCandidate] = []
    for rank, (index, code, name) in enumerate(entries[:size], start=1):
        out.append(
            RankedCandidate(
                rank=rank,
                name=name,
                prescription_code=code or NO_CANDIDATE_CODE,
                confidence_score=_lookup_confidence(confidence_by_code, code),
                candidate_index=index,
            )
        )
    return out


def describe_ranking_strategy(slate: Sequence[RankedCandidate]) -> str:
    """이 순위가 무엇에 근거했는지 한 단어로.

    세 경우를 섞지 않는다:
      - confidence        조회된 점수가 하나라도 순위에 실렸다
      - candidate_order   후보는 있는데 점수가 하나도 없다(호출자 top_rx,
                          disease_codes 없음, confidence AQL 실패·빈 결과).
                          모델에게 순서를 돌려주지 않고 조회가 준 순서를 쓰되,
                          각 항목의 confidence_score 는 None 으로 남는다
      - no_candidates     올릴 후보 자체가 없다(E78)
    """
    if not slate:
        return RANKING_STRATEGY_NO_CANDIDATES
    if any(c.confidence_score is not None for c in slate):
        return RANKING_STRATEGY_CONFIDENCE
    return RANKING_STRATEGY_CANDIDATE_ORDER
