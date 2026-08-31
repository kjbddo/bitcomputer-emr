import pytest

from verification_contract import (
    STRUCTURAL_CHECK_IDS,
    CheckResult,
    VerificationResult,
    aggregate_status,
)


def _check(check_id: str, outcome: str) -> CheckResult:
    return CheckResult(id=check_id, target="t", outcome=outcome, evidence="e")


def test_flagged_wins_over_everything():
    checks = [_check("code_in_candidates", "ok"), _check("name_matches_code", "flagged")]
    assert aggregate_status(checks) == "flagged"


def test_grounding_ok_yields_passed():
    checks = [_check("code_in_candidates", "ok"), _check("name_matches_code", "skipped")]
    assert aggregate_status(checks) == "passed"


# spec §5.1 의 핵심. 구조 검사는 조회 데이터가 없어도 판정되므로, 그것만으로
# passed 가 되면 "Arango 조회가 전부 실패했는데 rank 가 1,2,3 이라서 검증됨"
# 이라는 거짓 신호가 나간다. §2.2 의 결함이 다른 모양으로 돌아오는 것이다.
def test_structural_checks_alone_never_pass():
    checks = [_check("schema_top3", "ok"), _check("candidates_from_finder", "ok")]
    assert aggregate_status(checks) == "skipped"


def test_empty_checks_is_skipped():
    assert aggregate_status([]) == "skipped"


def test_all_skipped_is_skipped():
    checks = [_check("code_in_candidates", "skipped")]
    assert aggregate_status(checks) == "skipped"


# 구조 검사 집합이 비면 위 방어가 통째로 사라진다. 상수 자체를 고정한다.
def test_structural_ids_are_pinned():
    assert STRUCTURAL_CHECK_IDS == frozenset(
        {
            "schema_top3",
            "confidence_in_range",
            "trace_step_has_observation",
            "candidates_from_finder",
            "code_is_medication",
        }
    )


# code_is_medication 은 코드 문자열의 모양만 본다 — 조회된 어떤 데이터와도
# 대조하지 않는다. 근거 검사로 집계되면, Arango 조회가 전부 실패해
# code_in_candidates·name_matches_code 가 모두 skipped 인 응답도 "코드가
# 약제 코드처럼 생겼다"는 이유 하나로 "검증됨" 이 되어 나간다(GC-2).
def test_code_is_medication_alone_never_passes():
    checks = [_check("code_is_medication", "ok"), _check("code_in_candidates", "skipped")]
    assert aggregate_status(checks) == "skipped"


# confidence_in_range 는 0..1 범위만 본다 — 조회된 어떤 데이터와도 대조하지
# 않는다. 근거 검사로 집계되면 Arango 조회가 전부 실패해 code/name 이 전부
# skipped 인 응답도 "검증됨" 으로 나간다.
def test_confidence_in_range_alone_never_passes():
    checks = [_check("confidence_in_range", "ok"), _check("code_in_candidates", "skipped")]
    assert aggregate_status(checks) == "skipped"


def test_to_dict_shape():
    result = VerificationResult(
        status="flagged",
        checks=[_check("code_in_candidates", "flagged")],
        skippedReason=None,
    )
    assert result.to_dict() == {
        "status": "flagged",
        "checks": [
            {
                "id": "code_in_candidates",
                "target": "t",
                "outcome": "flagged",
                "evidence": "e",
            }
        ],
        "skippedReason": None,
    }


def test_checkresult_is_immutable():
    check = _check("code_in_candidates", "ok")
    with pytest.raises(Exception):
        check.outcome = "flagged"  # type: ignore[misc]


def test_verificationresult_is_immutable():
    result = VerificationResult(
        status="passed",
        checks=[_check("code_in_candidates", "ok")],
        skippedReason=None,
    )
    with pytest.raises(Exception):
        result.status = "flagged"  # type: ignore[misc]


def test_mutating_source_list_does_not_change_result():
    source = [_check("code_in_candidates", "ok")]
    result = VerificationResult(status="passed", checks=source, skippedReason=None)
    source.append(_check("name_matches_code", "flagged"))
    assert result.status == "passed"
    assert len(result.checks) == 1
    assert result.to_dict()["checks"] == [
        {
            "id": "code_in_candidates",
            "target": "t",
            "outcome": "ok",
            "evidence": "e",
        }
    ]
