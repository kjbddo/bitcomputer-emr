"""검증 결과 계약과 집계 규칙(validation-agent 사본).

services/prescription/verification_contract.py 와 동일해야 한다. 별도 Docker
빌드 컨텍스트라 공유 패키지 대신 복제한다. 동일성은 테스트로 고정한다.
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
# confidence_in_range 는 여기 없다: 그 검사 자체가 삭제됐다(spec §11.3,
# prescription_agent.py 프롬프트가 confidence_score 를 요구하지 않아 항상
# None 으로만 왔다). 존재하지 않는 검사 id 를 이 집합에 남겨 두면 다음
# 사람이 "이 검사가 아직 있나" 헷갈리게 만든다.
STRUCTURAL_CHECK_IDS = frozenset(
    {"schema_top3", "trace_step_has_observation", "candidates_from_finder"}
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
