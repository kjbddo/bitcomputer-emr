"""검증 결과 계약과 집계 규칙.

순수 함수만 둔다 — I/O 도 LLM 도 전역 상태도 쓰지 않는다(GC-1).
spec: Docs/superpowers/specs/2026-08-29-runtime-verification-design.md §5
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional, Sequence

CheckOutcome = Literal["ok", "flagged", "skipped"]
VerificationStatus = Literal["passed", "flagged", "skipped"]

# 구조 검사: 출력의 형태만 본다. 조회 데이터가 없어도 판정된다.
# 이 집합에 든 검사만 통과해서는 "passed" 가 되지 않는다(spec §5.1).
# 형식이 맞다는 것과 근거가 있다는 것은 다른 말이다.
#
# trace_step_has_observation 이 여기 든 이유: 그것은 "스텝에 관측값이 있나"만
# 보고 조회 데이터와 대조하지 않는다. 근거 검사로 집계하면, PubMed 도 finder 도
# 아무것도 못 가져온 응답이 트레이스만 멀쩡하면 "passed" 가 된다.
STRUCTURAL_CHECK_IDS = frozenset(
    {"schema_top3", "confidence_in_range", "trace_step_has_observation"}
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
    checks: List[CheckResult]
    skippedReason: Optional[str] = None

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
