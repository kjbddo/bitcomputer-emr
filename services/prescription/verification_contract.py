"""검증 결과 계약과 집계 규칙.

순수 함수만 둔다 — I/O 도 LLM 도 전역 상태도 쓰지 않는다(GC-1).
spec: Docs/superpowers/specs/2026-08-29-runtime-verification-design.md §5
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Literal, Optional, Sequence, Tuple

CheckOutcome = Literal["ok", "flagged", "skipped"]
VerificationStatus = Literal["passed", "flagged", "skipped"]

# 구조 검사: 출력의 형태만 본다. 조회 데이터가 없어도 판정된다.
# 이 집합에 든 검사만 통과해서는 "passed" 가 되지 않는다(spec §5.1).
# 형식이 맞다는 것과 근거가 있다는 것은 다른 말이다.
#
# trace_step_has_observation 이 여기 든 이유: 그것은 "스텝에 관측값이 있나"만
# 보고 조회 데이터와 대조하지 않는다. 근거 검사로 집계하면, PubMed 도 finder 도
# 아무것도 못 가져온 응답이 트레이스만 멀쩡하면 "passed" 가 된다.
#
# candidates_from_finder 가 여기 든 이유(최종 리뷰 C2): validation-agent 의
# 실제 배선에서 이 검사가 대조하는 두 값 — 도구 관측값 원본
# (state["finder_candidates"])과 응답에 실리는 candidatePrescriptions(=같은
# 원본을 정규화한 state["candidate_prescriptions"]) — 은 같은 finder 호출
# 결과에서 나온다. 그래서 정상 입력에서는 outside 가 구조적으로 항상
# 공집합이라 flagged 가 나올 수 없고, 응답이 자기 자신과 비교되는 "발화할 수
# 없는 검사"가 된다(제거된 dosage_verbatim 과 같은 부류). 그런데 skipped 가
# 아니라 늘 ok 를 내므로, 근거 검사로 집계하면 다른 근거 검사가 전부
# skipped(트레이스도 PubMed 인용도 없음)여도 이 ok 하나로 "passed" 가 나가
# GC-2 가 실질적으로 뚫린다. 검사 자체와 malformed/코드없음 탐지는 남긴다 —
# 미래에 정규화 로직이 바뀌어 두 값이 실제로 갈라지는 회귀는 여전히 잡아야
# 하기 때문이다. 다만 그 ok 는 "형식이 안 깨졌다"는 신호일 뿐 "조회 데이터와
# 실제로 대조해 근거를 확인했다"는 신호가 아니므로, 구조 검사로 두고 이것만
# 통과해서는 passed 가 되지 않게 한다. 다시 근거 검사로 되돌리면 C2 가
# 재발한다 — 되돌리지 말 것.
#
# confidence_in_range 가 여기 든 이유: 그것은 값이 0..1 범위 안인지만 보고
# 조회된 어떤 데이터와도 대조하지 않는다. 근거 검사로 집계하면, Arango 조회가
# 전부 실패해 code_in_candidates·name_matches_code 가 모두 skipped 인 응답도
# 이 ok 하나로 "passed" 가 나간다.
#
# 이 항목은 커밋 000c725 에서 "검사 자체가 삭제됐으므로 낡은 id" 라는 이유로
# 한 번 제거됐다가 되돌아왔다. 삭제의 근거였던 "프롬프트가 confidence_score 를
# 요구하지 않아 값이 항상 None" 은 사실이 아니었다 — 값을 채우는 것은 LLM 이
# 아니라 prescription_api.py 의 Arango co-occurrence 주입이고, 그 주입은
# 검증 호출보다 먼저 실행된다(spec §11.3 [환경 조건], §11.7). 검사가 복구된
# 이상 이 집합의 항목도 함께 있어야 한다.
STRUCTURAL_CHECK_IDS = frozenset(
    {
        "schema_top3",
        "confidence_in_range",
        "trace_step_has_observation",
        "candidates_from_finder",
    }
)


@dataclass(frozen=True)
class CheckResult:
    id: str
    target: str
    outcome: CheckOutcome
    evidence: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "target": self.target,
            "outcome": self.outcome,
            "evidence": self.evidence,
        }


@dataclass(frozen=True)
class VerificationResult:
    status: VerificationStatus
    checks: Tuple[CheckResult, ...]
    skippedReason: Optional[str] = None

    def __post_init__(self) -> None:
        # checks 는 List[CheckResult] 로 전달돼도 튜플로 굳힌다. frozen=True 는
        # result.status 재할당만 막을 뿐, 전달받은 리스트 자체가 나중에 바뀌거나
        # result.checks.append(...) 로 직접 변형되는 것은 막지 못한다 — 그 경로로
        # status 와 모순되는 checks 를 갖는 결과가 만들어질 수 있었다.
        object.__setattr__(self, "checks", tuple(self.checks))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "checks": [c.to_dict() for c in self.checks],
            "skippedReason": self.skippedReason,
        }


def aggregate_status(checks: Sequence[CheckResult]) -> VerificationStatus:
    """검사 결과에서 전체 상태를 도출한다.

    설정이 아니라 이 요청에서 실제로 실행된 검사 결과만 본다(GC-5).
    """
    if any(c.outcome == "flagged" for c in checks):
        return "flagged"
    # 근거 검사가 하나라도 통과해야 passed 다. 구조 검사만으로는 안 된다.
    if any(c.outcome == "ok" and c.id not in STRUCTURAL_CHECK_IDS for c in checks):
        return "passed"
    return "skipped"
