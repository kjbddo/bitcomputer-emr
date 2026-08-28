# B1 런타임 검증층 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 세 서비스가 자기 출력의 각 주장이 실제로 조회해온 데이터로 추적되는지 결정론적으로 대조하고, 그 결과를 의사 화면에 항목 단위로 표시한다.

**Architecture:** 각 서비스에 I/O 없는 순수 함수 검증 모듈을 둔다. 검증기는 요청이 아니라 조회 결과를 받고, 출력을 변형하지 않으며, 대조할 근거가 없으면 `passed` 가 아니라 `skipped` 를 낸다. 결과는 `verification` 필드로 응답에 실려 Java DTO 를 거쳐 웹까지 간다. NLI 2차 판정은 마지막에 기본 off 플래그로 붙인다.

**Tech Stack:** Python 3.11 (FastAPI, pydantic v2, pytest), Java 23 (Spring Boot, Jackson, Lombok), Next.js 15 (React 19, vitest 4 + jsdom, yarn 4)

**Spec:** `Docs/superpowers/specs/2026-08-29-runtime-verification-design.md`

## Global Constraints

- **GC-1: 검증기는 순수 함수다.** I/O·LLM·전역 상태를 쓰지 않는다. Task 1~10 에서 예외 없음.
- **GC-2: 근거 없음은 통과가 아니다.** 대조할 데이터가 없으면 `skipped`. `passed` 로 떨어지는 경로를 만들지 않는다.
- **GC-3: 검증기는 출력을 변형하지 않는다.**
- **GC-4: 검증 실패가 본 응답을 실패시키지 않는다.** 검증기 예외는 `skipped` 로 흡수한다.
- **GC-5: 상태는 실행 경로에서 나온다.** 설정이나 플래그 값에서 도출하지 않는다.
- **GC-6: 기존 필드를 건드리지 않는다.** `llmStatus`, `engineStatus`, `checks[]`, `reasoningTrace[].source` 모두 그대로 둔다.
- **GC-7: 파이썬 필드 추가와 Java DTO 확장은 같은 태스크에서 한다.**
- **GC-8: 각 검사는 그것을 무력화했을 때 빨개지는 테스트를 갖는다.**

## 환경

- `yarn` 이 PATH 에 없다. `cd apps/web && node .yarn/releases/yarn-4.12.0.cjs vitest run` 형태로 실행한다.
- 뮤테이션 테스트에 `git checkout --` 나 `git stash` 를 쓰지 않는다. 파일을 복사해 백업하고 복사로 되돌린 뒤 `git status --porcelain` 으로 확인한다.
- 현재 통과 수: llm-gateway 48 · validation-agent 33 · prescription 105 · web 150 · api 167(사전 실패 3건, 무관)

## File Structure

| 파일 | 책임 |
|---|---|
| `services/prescription/verification_contract.py` | `CheckResult`·`VerificationResult`·`aggregate_status`. prescription 과 certificate 가 공유(같은 디렉터리·같은 빌드 컨텍스트) |
| `services/prescription/verification.py` | 처방 추천 검사 5종 |
| `services/prescription/certificate_verification.py` | 진단서 검사 2종 |
| `services/validation-agent/app/verification_contract.py` | 같은 계약. 별도 서비스라 복제한다 |
| `services/validation-agent/app/verification.py` | 검증 에이전트 검사 3종 |
| `apps/web/src/utils/verificationNotice.ts` | 표시 판정. `llmStatus.ts` 옆에 둔다 |

**계약을 두 서비스에 복제하는 이유:** `services/prescription/` 과 `services/validation-agent/` 는 별도 Docker 빌드 컨텍스트다. 공유 패키지를 만들면 두 이미지 모두의 빌드를 바꿔야 하고, 계약이 6개 필드짜리 dataclass 두 개뿐이라 그 비용이 이득을 넘는다. 대신 Task 6 에서 두 파일이 동일한지 확인하는 테스트를 둔다.

---

## Task 개요

| # | 내용 | 산출물 |
|---|---|---|
| 1 | 검증 계약과 집계 규칙 | `verification_contract.py`, 집계 테스트 |
| 2 | prescription 검사 5종 | `verification.py` |
| 3 | prescription_api 배선 | 응답에 `verification` |
| 4 | certificate 검사 2종 + 배선 | `certificate_verification.py` |
| 5 | certificate Java DTO 3개 확장 | 화면까지 도달 |
| 6 | validation-agent 계약·검사 3종 | `app/verification.py` |
| 7 | validation-agent 배선 + 처방 검증 결과 전달 | `tools.py`, `agent.py` |
| 8 | validation-agent Java DTO 확장 | 동기 경로 보존 |
| 9 | 웹 공용 표시 헬퍼 + 처방 표 | `verificationNotice.ts` |
| 10 | 웹 진단서 모달 + 검증 이유 목록 | 표시 완결 |
| 11 | B(NLI) 플래그, 기본 off | 별도 예산·별도 caller |
| 12 | 실측과 spec 갱신 | 검증층이 실제로 무엇을 잡는지 |

Task 11 은 spec §3.2 대로 A 와 독립 출시 가능하다. Task 10 까지로 한 번 끊어도 된다.

---

### Task 1: 검증 계약과 집계 규칙

집계 규칙이 이 플랜에서 가장 위험한 로직이다. 여기서 틀리면 나머지 열 개 태스크가 전부 거짓 신호를 실어 나른다.

**Files:**
- Create: `services/prescription/verification_contract.py`
- Test: `services/prescription/tests/test_verification_contract.py`

**Interfaces:**
- Produces: `CheckResult(id, target, outcome, evidence)`, `VerificationResult(status, checks, skippedReason)`, `aggregate_status(checks) -> str`, `STRUCTURAL_CHECK_IDS`, `VerificationResult.to_dict()`

- [ ] **Step 1: 실패하는 테스트 작성**

`services/prescription/tests/test_verification_contract.py`:

```python
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
    checks = [_check("code_in_candidates", "ok"), _check("dosage_verbatim", "flagged")]
    assert aggregate_status(checks) == "flagged"


def test_grounding_ok_yields_passed():
    checks = [_check("code_in_candidates", "ok"), _check("dosage_verbatim", "skipped")]
    assert aggregate_status(checks) == "passed"


# spec §5.1 의 핵심. 구조 검사는 조회 데이터가 없어도 판정되므로, 그것만으로
# passed 가 되면 "Arango 조회가 전부 실패했는데 rank 가 1,2,3 이라서 검증됨"
# 이라는 거짓 신호가 나간다. §2.2 의 결함이 다른 모양으로 돌아오는 것이다.
def test_structural_checks_alone_never_pass():
    checks = [_check("schema_top3", "ok"), _check("confidence_in_range", "ok")]
    assert aggregate_status(checks) == "skipped"


def test_empty_checks_is_skipped():
    assert aggregate_status([]) == "skipped"


def test_all_skipped_is_skipped():
    checks = [_check("code_in_candidates", "skipped")]
    assert aggregate_status(checks) == "skipped"


# 구조 검사 집합이 비면 위 방어가 통째로 사라진다. 상수 자체를 고정한다.
def test_structural_ids_are_pinned():
    assert STRUCTURAL_CHECK_IDS == frozenset({"schema_top3", "confidence_in_range"})


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
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `cd services/prescription && python -m pytest tests/test_verification_contract.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'verification_contract'`

- [ ] **Step 3: 계약 구현**

`services/prescription/verification_contract.py`:

```python
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
STRUCTURAL_CHECK_IDS = frozenset({"schema_top3", "confidence_in_range"})


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
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd services/prescription && python -m pytest tests/test_verification_contract.py -q`
Expected: PASS (8개)

- [ ] **Step 5: 뮤테이션으로 테스트가 실제로 실패하는지 확인**

파일을 복사해 백업한 뒤 아래를 각각 적용하고, 복사로 되돌린다.

1. `aggregate_status` 의 구조 검사 제외 조건을 지운다: `if any(c.outcome == "ok" for c in checks)`
   → `test_structural_checks_alone_never_pass` 가 FAIL 해야 한다.
2. `STRUCTURAL_CHECK_IDS = frozenset()` 로 비운다
   → `test_structural_ids_are_pinned` 와 `test_structural_checks_alone_never_pass` 가 FAIL 해야 한다.
3. `flagged` 분기를 지운다
   → `test_flagged_wins_over_everything` 이 FAIL 해야 한다.

각 뮤테이션 후 복원하고 `git status --porcelain` 이 비었는지 확인한다.

- [ ] **Step 6: 커밋**

```bash
git add services/prescription/verification_contract.py services/prescription/tests/test_verification_contract.py
git commit -m "feat(verification): 검증 결과 계약과 집계 규칙"
```

---

### Task 2: prescription 검사 5종

**Files:**
- Create: `services/prescription/verification.py`
- Test: `services/prescription/tests/test_verification.py`

**Interfaces:**
- Consumes: Task 1 의 `CheckResult`, `VerificationResult`, `aggregate_status`
- Produces: `verify_prescriptions(*, candidates: List[Any], items: List[Any]) -> VerificationResult`

`candidates` 는 `prescription_api` 의 `effective_top_rx` 다 — Arango 조회와 코호트 병합을 마친 후보 행 목록. 행은 dict 이고 처방코드가 `prescription_code` 또는 `처방코드` 키에, 처방명이 `prescription_name` 또는 `처방명` 키에 들어 있다(두 형태가 실제로 공존한다).

`items` 는 `PrescriptionItem` 목록이다: `rank`, `name`, `prescription_code`, `dosage`, `reason`, `confidence_score`.

- [ ] **Step 1: 실패하는 테스트 작성**

`services/prescription/tests/test_verification.py`:

```python
from types import SimpleNamespace

from verification import verify_prescriptions


def _item(rank, code, name, dosage="1일 3회", confidence=0.8):
    return SimpleNamespace(
        rank=rank,
        name=name,
        prescription_code=code,
        dosage=dosage,
        reason="근거",
        confidence_score=confidence,
    )


def _outcomes(result, check_id):
    return [c.outcome for c in result.checks if c.id == check_id]


CANDIDATES = [
    {"prescription_code": "A01", "prescription_name": "약가", "dosage": "1일 3회"},
    {"처방코드": "B02", "처방명": "약나", "dosage": "1일 1회"},
    {"prescription_code": "C03", "prescription_name": "약다", "dosage": "2정"},
]


def test_all_codes_in_candidates_pass():
    items = [_item(1, "A01", "약가"), _item(2, "B02", "약나", "1일 1회"),
             _item(3, "C03", "약다", "2정")]
    result = verify_prescriptions(candidates=CANDIDATES, items=items)

    assert result.status == "passed"
    assert _outcomes(result, "code_in_candidates") == ["ok", "ok", "ok"]


def test_invented_code_is_flagged():
    items = [_item(1, "A01", "약가"), _item(2, "B02", "약나", "1일 1회"),
             _item(3, "Z99", "지어낸약", "2정")]
    result = verify_prescriptions(candidates=CANDIDATES, items=items)

    assert result.status == "flagged"
    assert "flagged" in _outcomes(result, "code_in_candidates")


def test_name_mismatch_is_flagged():
    items = [_item(1, "A01", "다른이름"), _item(2, "B02", "약나", "1일 1회"),
             _item(3, "C03", "약다", "2정")]
    result = verify_prescriptions(candidates=CANDIDATES, items=items)

    assert "flagged" in _outcomes(result, "name_matches_code")


def test_dosage_not_in_source_is_flagged():
    items = [_item(1, "A01", "약가", dosage="1일 99회"), _item(2, "B02", "약나", "1일 1회"),
             _item(3, "C03", "약다", "2정")]
    result = verify_prescriptions(candidates=CANDIDATES, items=items)

    assert "flagged" in _outcomes(result, "dosage_verbatim")


# §2.2 의 조용한 누락을 고치는 지점. 원본에 용량 정보가 없으면 판정할 수 없다.
# 기존 휴리스틱은 이 경우 증가도 이슈 기록도 없이 그냥 사라졌다.
def test_dosage_skipped_when_source_has_none():
    candidates = [{"prescription_code": "A01", "prescription_name": "약가"}]
    items = [_item(1, "A01", "약가", dosage="1일 3회")]
    result = verify_prescriptions(candidates=candidates, items=items)

    assert _outcomes(result, "dosage_verbatim") == ["skipped"]


# GC-2. 후보가 비면 통과가 아니라 미확인이다.
def test_empty_candidates_never_passes():
    items = [_item(1, "A01", "약가"), _item(2, "B02", "약나"), _item(3, "C03", "약다")]
    result = verify_prescriptions(candidates=[], items=items)

    assert result.status == "skipped"
    assert result.skippedReason is not None
    assert _outcomes(result, "code_in_candidates") == ["skipped", "skipped", "skipped"]


def test_wrong_rank_set_is_flagged():
    items = [_item(1, "A01", "약가"), _item(1, "B02", "약나", "1일 1회"),
             _item(3, "C03", "약다", "2정")]
    result = verify_prescriptions(candidates=CANDIDATES, items=items)

    assert _outcomes(result, "schema_top3") == ["flagged"]


def test_confidence_out_of_range_is_flagged():
    items = [_item(1, "A01", "약가", confidence=1.7), _item(2, "B02", "약나", "1일 1회"),
             _item(3, "C03", "약다", "2정")]
    result = verify_prescriptions(candidates=CANDIDATES, items=items)

    assert "flagged" in _outcomes(result, "confidence_in_range")


# GC-3. 검증기는 판정만 한다.
def test_does_not_mutate_output():
    items = [_item(1, "A01", "약가")]
    before = [(i.rank, i.name, i.prescription_code, i.dosage, i.confidence_score) for i in items]
    verify_prescriptions(candidates=CANDIDATES, items=items)
    after = [(i.rank, i.name, i.prescription_code, i.dosage, i.confidence_score) for i in items]

    assert before == after


# reason 은 A 에서 검증하지 않는다(spec §6.1). 검사가 생기면 이 테스트가 알려준다.
def test_no_reason_check_in_phase_a():
    items = [_item(1, "A01", "약가")]
    result = verify_prescriptions(candidates=CANDIDATES, items=items)

    assert not [c for c in result.checks if "reason" in c.id]
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `cd services/prescription && python -m pytest tests/test_verification.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'verification'`

- [ ] **Step 3: 검증기 구현**

`services/prescription/verification.py`:

```python
"""처방 추천 출력을 조회 결과와 대조한다.

순수 함수만 둔다(GC-1). 출력을 변형하지 않는다(GC-3).
근거가 없으면 통과가 아니라 미확인이다(GC-2).

spec: Docs/superpowers/specs/2026-08-29-runtime-verification-design.md §6.1
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from verification_contract import CheckResult, VerificationResult, aggregate_status


def _row_code(row: Any) -> str:
    """후보 행의 처방코드. 두 키 형태가 실제로 공존한다."""
    if not isinstance(row, dict):
        return ""
    value = row.get("prescription_code")
    if value is None:
        value = row.get("처방코드")
    return str(value).strip() if value is not None else ""


def _row_name(row: Any) -> str:
    if not isinstance(row, dict):
        return ""
    value = row.get("prescription_name")
    if value is None:
        value = row.get("처방명")
    return str(value).strip() if value is not None else ""


def _row_dosage(row: Any) -> str:
    if not isinstance(row, dict):
        return ""
    value = row.get("dosage")
    if value is None:
        value = row.get("용법")
    return str(value).strip() if value is not None else ""


def _index_candidates(candidates: Sequence[Any]) -> Dict[str, Dict[str, str]]:
    index: Dict[str, Dict[str, str]] = {}
    for row in candidates:
        code = _row_code(row)
        if not code:
            continue
        index.setdefault(code, {"name": _row_name(row), "dosage": _row_dosage(row)})
    return index


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def verify_prescriptions(*, candidates: Sequence[Any], items: Sequence[Any]) -> VerificationResult:
    index = _index_candidates(candidates)
    has_candidates = bool(index)
    checks: List[CheckResult] = []

    # 구조 검사 — 조회 데이터 없이도 판정된다.
    ranks = sorted(int(getattr(i, "rank", 0) or 0) for i in items)
    codes = [_text(getattr(i, "prescription_code", "")) for i in items]
    schema_ok = ranks == [1, 2, 3] and len(set(codes)) == len(codes)
    checks.append(
        CheckResult(
            id="schema_top3",
            target="response",
            outcome="ok" if schema_ok else "flagged",
            evidence=f"rank={ranks} 코드중복={len(codes) - len(set(codes))}건",
        )
    )

    for item in items:
        rank = _text(getattr(item, "rank", ""))
        target = f"prescription[{rank}]"
        code = _text(getattr(item, "prescription_code", ""))
        name = _text(getattr(item, "name", ""))
        dosage = _text(getattr(item, "dosage", ""))
        confidence = getattr(item, "confidence_score", None)

        if not has_candidates:
            checks.append(CheckResult(
                id="code_in_candidates", target=target, outcome="skipped",
                evidence="조회된 후보가 없어 대조할 수 없음"))
            checks.append(CheckResult(
                id="name_matches_code", target=target, outcome="skipped",
                evidence="조회된 후보가 없어 대조할 수 없음"))
            checks.append(CheckResult(
                id="dosage_verbatim", target=target, outcome="skipped",
                evidence="조회된 후보가 없어 대조할 수 없음"))
        else:
            matched = index.get(code)
            checks.append(CheckResult(
                id="code_in_candidates", target=target,
                outcome="ok" if matched else "flagged",
                evidence=f"코드 {code!r} 가 후보 {len(index)}건 중 " +
                         ("있음" if matched else "없음")))

            if matched is None:
                checks.append(CheckResult(
                    id="name_matches_code", target=target, outcome="skipped",
                    evidence="코드가 후보에 없어 이름을 대조할 수 없음"))
                checks.append(CheckResult(
                    id="dosage_verbatim", target=target, outcome="skipped",
                    evidence="코드가 후보에 없어 용량을 대조할 수 없음"))
            else:
                expected_name = matched["name"]
                if not expected_name:
                    checks.append(CheckResult(
                        id="name_matches_code", target=target, outcome="skipped",
                        evidence="후보 행에 처방명이 없어 대조할 수 없음"))
                else:
                    checks.append(CheckResult(
                        id="name_matches_code", target=target,
                        outcome="ok" if expected_name == name else "flagged",
                        evidence=f"후보 {expected_name!r} vs 출력 {name!r}"))

                source_dosage = matched["dosage"]
                if not source_dosage:
                    # §2.2 의 조용한 누락을 고치는 지점.
                    checks.append(CheckResult(
                        id="dosage_verbatim", target=target, outcome="skipped",
                        evidence="후보 행에 용량 정보가 없어 대조할 수 없음"))
                elif not dosage:
                    checks.append(CheckResult(
                        id="dosage_verbatim", target=target, outcome="skipped",
                        evidence="출력에 용량이 없어 대조할 수 없음"))
                else:
                    checks.append(CheckResult(
                        id="dosage_verbatim", target=target,
                        outcome="ok" if dosage in source_dosage or dosage == source_dosage else "flagged",
                        evidence=f"후보 {source_dosage!r} vs 출력 {dosage!r}"))

        if confidence is None:
            checks.append(CheckResult(
                id="confidence_in_range", target=target, outcome="skipped",
                evidence="confidence_score 없음"))
        else:
            in_range = 0.0 <= float(confidence) <= 1.0
            checks.append(CheckResult(
                id="confidence_in_range", target=target,
                outcome="ok" if in_range else "flagged",
                evidence=f"confidence_score={confidence}"))

    skipped_reason: Optional[str] = None
    if not has_candidates:
        skipped_reason = "조회된 처방 후보가 없어 근거 대조를 수행하지 못했습니다."

    return VerificationResult(
        status=aggregate_status(checks),
        checks=checks,
        skippedReason=skipped_reason,
    )
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd services/prescription && python -m pytest tests/test_verification.py -q`
Expected: PASS (10개)

- [ ] **Step 5: 뮤테이션 확인 (GC-8)**

각 검사마다 하나씩, 파일 복사 백업/복원 방식으로 적용한다.

1. `code_in_candidates` 를 항상 `"ok"` 로 → `test_invented_code_is_flagged` FAIL
2. `name_matches_code` 를 항상 `"ok"` 로 → `test_name_mismatch_is_flagged` FAIL
3. `dosage_verbatim` 의 후보 용량 없음 분기를 `"ok"` 로 → `test_dosage_skipped_when_source_has_none` FAIL
4. `not has_candidates` 분기에서 `"skipped"` 대신 `"ok"` 로 → `test_empty_candidates_never_passes` FAIL
5. `schema_ok` 를 항상 True 로 → `test_wrong_rank_set_is_flagged` FAIL
6. `confidence_in_range` 를 항상 `"ok"` 로 → `test_confidence_out_of_range_is_flagged` FAIL

여섯 개 전부 RED 인지 표로 보고한다. 하나라도 초록이면 그 검사는 지워도 아무도 모른다는 뜻이다.

- [ ] **Step 6: 커밋**

```bash
git add services/prescription/verification.py services/prescription/tests/test_verification.py
git commit -m "feat(prescription): 처방 추천 출력의 근거 대조 검사 5종"
```

---

### Task 3: prescription_api 배선

**Files:**
- Modify: `services/prescription/prescription_api.py`
- Test: `services/prescription/tests/test_verification_wiring.py`

**Interfaces:**
- Consumes: Task 2 의 `verify_prescriptions(*, candidates, items) -> VerificationResult`
- Produces: `PrescriptionRecommendResponse.verification: Optional[Dict[str, Any]]`

- [ ] **Step 1: 실패하는 테스트 작성**

`services/prescription/tests/test_verification_wiring.py`:

```python
import prescription_api


def test_response_model_has_verification_field():
    assert "verification" in prescription_api.PrescriptionRecommendResponse.model_fields


# GC-4. 검증기가 터져도 본 응답은 성공해야 한다.
def test_verifier_exception_becomes_skipped(monkeypatch):
    def boom(**kwargs):
        raise RuntimeError("검증기 폭발")

    monkeypatch.setattr(prescription_api, "verify_prescriptions", boom)

    result = prescription_api._safe_verify(candidates=[], items=[])

    assert result["status"] == "skipped"
    assert "RuntimeError" in (result["skippedReason"] or "")


def test_safe_verify_passes_through_normal_result():
    result = prescription_api._safe_verify(
        candidates=[{"prescription_code": "A01", "prescription_name": "약가"}],
        items=[],
    )
    assert result["status"] == "skipped"
    assert isinstance(result["checks"], list)
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `cd services/prescription && python -m pytest tests/test_verification_wiring.py -q`
Expected: FAIL — `verification` 필드도 `_safe_verify` 도 없다.

- [ ] **Step 3: 응답 모델에 필드 추가**

`services/prescription/prescription_api.py` 의 `PrescriptionRecommendResponse` 에서
`llmStatus: Literal["real", "stub"]` 바로 아래에 추가한다:

```python
    # 출력이 조회 결과로 추적되는지. llmStatus 와 다른 축이다 —
    # llmStatus 는 "모델이 돌았나", 이건 "돈 결과에 근거가 있나"다(spec §7.1).
    verification: Optional[Dict[str, Any]] = None
```

- [ ] **Step 4: import 와 안전 래퍼 추가**

같은 파일 상단 import 블록에 추가한다:

```python
from verification import verify_prescriptions
```

그리고 `recommend` 함수 정의 바로 위에 추가한다:

```python
def _safe_verify(*, candidates: Any, items: Any) -> Dict[str, Any]:
    """검증을 돌리되 절대 본 응답을 실패시키지 않는다(GC-4).

    검증기에서 예외가 나면 skipped 로 흡수한다. 검증이 실패했는데 passed 로
    떨어지면 검증층이 있는 이유가 사라지므로, 실패는 반드시 skipped 다.
    """
    try:
        return verify_prescriptions(candidates=candidates, items=items).to_dict()
    except Exception as exc:  # noqa: BLE001
        logger.exception("처방 검증 실패, skipped 로 처리")
        return {
            "status": "skipped",
            "checks": [],
            "skippedReason": f"검증기 예외: {type(exc).__name__}",
        }
```

- [ ] **Step 5: 응답 조립부 배선**

`prescription_api.py:700` 근처의 `return PrescriptionRecommendResponse(` 블록에서
`llmStatus=llm_status,` 다음 줄에 추가한다:

```python
        verification=_safe_verify(candidates=effective_top_rx, items=items),
```

`effective_top_rx` 는 Arango 조회와 코호트 병합을 마친 최종 후보 목록이다.
**`req.top_rx` 를 넘기면 안 된다** — 요청은 호출자가 주장하는 것이고, 검증은
서비스가 실제로 조회한 것에 대조해야 한다(spec §4.1).

- [ ] **Step 6: 테스트 통과 확인**

Run: `cd services/prescription && python -m pytest tests/test_verification_wiring.py -q`
Expected: PASS (3개)

Run: `cd services/prescription && python -m pytest -q`
Expected: 기존 105 + 신규(계약 8 + 검사 10 + 배선 3) = 126 통과

- [ ] **Step 7: 뮤테이션 확인**

1. `verification=_safe_verify(...)` 줄을 지운다 → `test_response_model_has_verification_field` 는 통과하지만 아무 테스트도 배선을 안 잡는다는 뜻이다. **배선을 잡는 테스트를 추가한다**:

```python
def test_recommend_wires_effective_top_rx_not_request(monkeypatch):
    """검증기에 요청이 아니라 조회 결과가 간다(spec §4.1).

    이걸 안 잡으면 req.top_rx 를 넘기는 회귀가 조용히 들어온다 — 그러면
    "요청에 적혀 있으니 근거 있음"이 되어 검증이 무의미해진다.
    """
    seen = {}

    def spy(*, candidates, items):
        seen["candidates"] = candidates
        raise RuntimeError("여기서 멈춘다")

    monkeypatch.setattr(prescription_api, "verify_prescriptions", spy)
    prescription_api._safe_verify(candidates=["조회결과"], items=[])

    assert seen["candidates"] == ["조회결과"]
```

2. `_safe_verify` 의 `except` 블록에서 `"skipped"` 를 `"passed"` 로 → `test_verifier_exception_becomes_skipped` FAIL

- [ ] **Step 8: 커밋**

```bash
git add services/prescription/prescription_api.py services/prescription/tests/test_verification_wiring.py
git commit -m "feat(prescription): 응답에 verification 필드 배선"
```

---

### Task 4: certificate 검사 2종과 배선

**Files:**
- Create: `services/prescription/certificate_verification.py`
- Modify: `services/prescription/certificate_api.py`
- Test: `services/prescription/tests/test_certificate_verification.py`

**Interfaces:**
- Consumes: Task 1 의 계약
- Produces: `verify_certificate(*, diseases: List[Any], prescription_names: List[str], text: str) -> VerificationResult`
- Produces: `CertificateGenerateResponse.verification: Optional[Dict[str, Any]]`

`diseases` 는 `CertificateGenerateRequest.diseases` — `DiseaseInfo{code, name, degree}` 목록이다.

- [ ] **Step 1: 실패하는 테스트 작성**

`services/prescription/tests/test_certificate_verification.py`:

```python
from types import SimpleNamespace

from certificate_verification import verify_certificate


def _disease(code, name):
    return SimpleNamespace(code=code, name=name, degree=None)


DISEASES = [_disease("J00", "급성 비인두염"), _disease("E11.9", "제2형 당뇨병")]


def _outcomes(result, check_id):
    return [c.outcome for c in result.checks if c.id == check_id]


def test_known_code_and_term_pass():
    text = "환자는 급성 비인두염(J00)으로 통원 치료가 필요합니다."
    result = verify_certificate(diseases=DISEASES, prescription_names=["약가"], text=text)

    assert result.status == "passed"
    assert _outcomes(result, "cited_code_known") == ["ok"]
    assert _outcomes(result, "premise_term_present") == ["ok"]


def test_unknown_icd_code_is_flagged():
    text = "환자는 급성 비인두염(K52.9)으로 통원 치료가 필요합니다."
    result = verify_certificate(diseases=DISEASES, prescription_names=[], text=text)

    assert result.status == "flagged"
    assert "flagged" in _outcomes(result, "cited_code_known")


def test_no_code_in_text_is_skipped():
    text = "환자는 통원 치료가 필요합니다."
    result = verify_certificate(diseases=DISEASES, prescription_names=[], text=text)

    assert _outcomes(result, "cited_code_known") == ["skipped"]


def test_premise_term_absent_is_flagged():
    text = "환자는 안정이 필요합니다."
    result = verify_certificate(diseases=DISEASES, prescription_names=["약가"], text=text)

    assert "flagged" in _outcomes(result, "premise_term_present")


# GC-2. premise 가 비면 통과가 아니라 미확인이다.
def test_empty_premise_never_passes():
    text = "환자는 급성 비인두염으로 통원 치료가 필요합니다."
    result = verify_certificate(diseases=[], prescription_names=[], text=text)

    assert result.status == "skipped"
    assert result.skippedReason is not None


def test_dotted_icd_code_is_recognised():
    text = "제2형 당뇨병(E11.9) 소견입니다."
    result = verify_certificate(diseases=DISEASES, prescription_names=[], text=text)

    assert _outcomes(result, "cited_code_known") == ["ok"]


def test_prescription_name_counts_as_premise_term():
    text = "약가 투여를 지속할 것을 권고합니다."
    result = verify_certificate(diseases=DISEASES, prescription_names=["약가"], text=text)

    assert _outcomes(result, "premise_term_present") == ["ok"]
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `cd services/prescription && python -m pytest tests/test_certificate_verification.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'certificate_verification'`

- [ ] **Step 3: 검증기 구현**

`services/prescription/certificate_verification.py`:

```python
"""진단서 소견을 premise 와 대조한다.

자유 산문이라 결정론적으로 잡을 수 있는 것이 얇다. 잡히는 것은 "없는 상병코드를
인용했다"와 "근거로 삼았다는 상병을 한 번도 언급하지 않았다" 두 가지다.
문장 단위 함의 판정은 B(NLI)의 몫이다(spec §6.2).
"""
from __future__ import annotations

import re
from typing import Any, List, Optional, Sequence

from verification_contract import CheckResult, VerificationResult, aggregate_status

# ICD-10 형태. "코드처럼 생긴 것"을 애매하게 두면 검사가 무엇을 하는지
# 아무도 말할 수 없게 된다(spec §6.2).
ICD10_PATTERN = re.compile(r"\b[A-Z]\d{2}(?:\.\d+)?\b")


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def verify_certificate(
    *,
    diseases: Sequence[Any],
    prescription_names: Sequence[str],
    text: str,
) -> VerificationResult:
    known_codes = {_text(getattr(d, "code", "")) for d in diseases}
    known_codes.discard("")
    known_terms = {_text(getattr(d, "name", "")) for d in diseases}
    known_terms |= {_text(n) for n in prescription_names}
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

    cited = ICD10_PATTERN.findall(text or "")
    if not cited:
        checks.append(CheckResult(
            id="cited_code_known", target="certificate", outcome="skipped",
            evidence="소견에 ICD-10 형태 토큰이 없음"))
    else:
        unknown = [c for c in cited if c not in known_codes]
        checks.append(CheckResult(
            id="cited_code_known", target="certificate",
            outcome="flagged" if unknown else "ok",
            evidence=(f"소견의 코드 {cited} 중 premise 밖: {unknown}" if unknown
                      else f"소견의 코드 {cited} 가 모두 premise 안에 있음")))

    if not known_terms:
        checks.append(CheckResult(
            id="premise_term_present", target="certificate", outcome="skipped",
            evidence="premise 에 상병명·처방명이 없어 대조할 수 없음"))
    else:
        present = [t for t in sorted(known_terms) if t in (text or "")]
        checks.append(CheckResult(
            id="premise_term_present", target="certificate",
            outcome="ok" if present else "flagged",
            evidence=(f"소견이 언급한 premise 용어: {present}" if present
                      else "소견이 premise 의 상병명·처방명을 하나도 언급하지 않음")))

    return VerificationResult(
        status=aggregate_status(checks), checks=checks, skippedReason=skipped_reason)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd services/prescription && python -m pytest tests/test_certificate_verification.py -q`
Expected: PASS (7개)

- [ ] **Step 5: certificate_api 에 배선**

`services/prescription/certificate_api.py` 의 `CertificateGenerateResponse` 에서
`llmStatus: Literal["real", "stub"]` 아래에 추가한다:

```python
    verification: Optional[Dict[str, Any]] = None
```

import 를 추가한다:

```python
from certificate_verification import verify_certificate
```

`generate_certificate` 의 응답 조립부에서 `llmStatus=` 다음 줄에 추가한다:

```python
        verification=_safe_verify_certificate(req, medical_certificate),
```

그리고 안전 래퍼를 응답 조립 함수 위에 둔다:

```python
def _safe_verify_certificate(req: Any, text: str) -> Dict[str, Any]:
    """검증을 돌리되 본 응답을 실패시키지 않는다(GC-4)."""
    try:
        names = [
            _text_or_empty(getattr(p, "name", ""))
            for p in (getattr(req, "prescriptions", None) or [])
        ]
        return verify_certificate(
            diseases=getattr(req, "diseases", None) or [],
            prescription_names=[n for n in names if n],
            text=text,
        ).to_dict()
    except Exception as exc:  # noqa: BLE001
        logger.exception("진단서 검증 실패, skipped 로 처리")
        return {
            "status": "skipped",
            "checks": [],
            "skippedReason": f"검증기 예외: {type(exc).__name__}",
        }


def _text_or_empty(value: Any) -> str:
    return str(value).strip() if value is not None else ""
```

`CertificateGenerateRequest` 에 `prescriptions` 필드가 없으면 `getattr` 이 빈 목록을
돌려주므로 상병명만으로 판정한다 — 필드 존재 여부를 먼저 읽고 확인한다.

- [ ] **Step 6: 배선 테스트 추가**

`services/prescription/tests/test_certificate_verification.py` 에 추가한다:

```python
import certificate_api


def test_response_model_has_verification_field():
    assert "verification" in certificate_api.CertificateGenerateResponse.model_fields


def test_certificate_verifier_exception_becomes_skipped(monkeypatch):
    def boom(**kwargs):
        raise RuntimeError("검증기 폭발")

    monkeypatch.setattr(certificate_api, "verify_certificate", boom)
    result = certificate_api._safe_verify_certificate(object(), "소견")

    assert result["status"] == "skipped"
    assert "RuntimeError" in (result["skippedReason"] or "")
```

- [ ] **Step 7: 전체 확인**

Run: `cd services/prescription && python -m pytest -q`
Expected: 이전 126 + 9 = 135 통과

- [ ] **Step 8: 뮤테이션 확인**

1. `cited_code_known` 의 `unknown` 판정을 항상 빈 목록으로 → `test_unknown_icd_code_is_flagged` FAIL
2. `premise_term_present` 를 항상 `"ok"` 로 → `test_premise_term_absent_is_flagged` FAIL
3. `not has_premise` 분기에서 `"skipped"` 대신 `"ok"` 로 → `test_empty_premise_never_passes` FAIL
4. `ICD10_PATTERN` 에서 `(?:\.\d+)?` 를 지운다 → `test_dotted_icd_code_is_recognised` FAIL

- [ ] **Step 9: 커밋**

```bash
git add services/prescription/certificate_verification.py services/prescription/certificate_api.py services/prescription/tests/test_certificate_verification.py
git commit -m "feat(certificate): 소견을 premise 와 대조하는 검사 2종"
```

---

### Task 5: certificate Java DTO 3개 확장

GC-7 대로 파이썬 필드 추가와 Java DTO 확장을 붙여서 한다. Task 10·11 에서 확인된 함정이다 —
`@JsonIgnoreProperties(ignoreUnknown = true)` 가 붙은 DTO 는 모르는 필드를 조용히 버린다.

**Files:**
- Modify: `apps/api/src/main/java/com/example/bitcomputer/model/CertificateAgentResponse.java`
- Modify: `apps/api/src/main/java/com/example/bitcomputer/model/GenerateCertificateResponseDTO.java`
- Modify: `apps/api/src/main/java/com/example/bitcomputer/serviceImpl/AgentDocumentServiceImpl.java`
- Test: `apps/api/src/test/java/com/example/bitcomputer/model/CertificateAgentResponseTest.java` (기존 파일에 추가)

**Interfaces:**
- Consumes: Task 4 의 `verification` JSON 객체
- Produces: `GenerateCertificateResponseDTO.verification: Map<String, Object>`

- [ ] **Step 1: 실패하는 테스트 작성**

`apps/api/src/test/java/com/example/bitcomputer/model/CertificateAgentResponseTest.java` 에 추가:

```java
    /**
     * @JsonIgnoreProperties(ignoreUnknown = true) 때문에 DTO 가 모르는 필드는
     * 왕복에서 사라진다. 값까지 단언해야 "필드가 선언돼 있다"가 아니라
     * "상류 값이 살아남았다"를 검증한다.
     */
    @Test
    void roundTripPreservesVerification() throws Exception {
        String upstream = "{"
                + "\"medicalCertificate\":\"소견\","
                + "\"llmStatus\":\"real\","
                + "\"verification\":{\"status\":\"flagged\",\"checks\":["
                + "{\"id\":\"cited_code_known\",\"target\":\"certificate\","
                + "\"outcome\":\"flagged\",\"evidence\":\"K52.9\"}],"
                + "\"skippedReason\":null}"
                + "}";

        CertificateAgentResponse parsed =
                objectMapper.readValue(upstream, CertificateAgentResponse.class);
        String roundTripped = objectMapper.writeValueAsString(parsed);

        assertThat(parsed.getVerification()).isNotNull();
        assertThat(roundTripped).contains("\"status\":\"flagged\"");
        assertThat(roundTripped).contains("\"id\":\"cited_code_known\"");
    }

    /** 상류가 필드를 안 주면 "검증됨"으로 기울면 안 된다. null 이 미검증이다. */
    @Test
    void missingVerificationIsNull() throws Exception {
        CertificateAgentResponse parsed = objectMapper.readValue(
                "{\"medicalCertificate\":\"소견\"}", CertificateAgentResponse.class);

        assertThat(parsed.getVerification()).isNull();
    }
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `cd apps/api && ./gradlew test --tests "*CertificateAgentResponseTest*"`
Expected: FAIL — `getVerification()` 이 없어 컴파일 에러

- [ ] **Step 3: DTO 두 개에 필드 추가**

`CertificateAgentResponse.java` 의 `llmStatus` 필드 아래:

```java
    /**
     * 소견이 조회 결과로 추적되는지. llmStatus 와 다른 축이다 —
     * llmStatus 는 "모델이 돌았나", 이건 "돈 결과에 근거가 있나"다.
     *
     * <p>상류가 안 주면 null 이고, 웹은 null 을 "미검증"으로 렌더한다.
     * 여기서 기본값을 만들면 검증하지 않은 것이 검증된 것처럼 보인다.
     */
    @JsonProperty("verification")
    private Map<String, Object> verification;
```

`java.util.Map` import 를 추가한다.

`GenerateCertificateResponseDTO.java` 에:

```java
    /** 소견이 조회 결과로 추적되는지: {status, checks[], skippedReason}. */
    private Map<String, Object> verification;
```

`java.util.Map` import 를 추가한다.

- [ ] **Step 4: 서비스 배선**

`AgentDocumentServiceImpl.java` 의 `generateCertificate` 에서 `agentResponse` 를 이미
`Optional<CertificateAgentResponse>` 로 잡고 있다(Task 11 에서 그렇게 바꿨다).
`resolveCertificateLlmStatus(...)` 호출 다음 줄에 추가한다:

```java
        Map<String, Object> verification = agentResponse
                .map(CertificateAgentResponse::getVerification)
                .orElse(null);
```

`buildGenerateResponse` 호출을 바꾼다:

```java
        return buildGenerateResponse(username, medicalCertificate, llmStatus, verification);
```

`generateTestCertificate` 의 같은 블록도 같은 형태로 바꾼다.

`buildGenerateResponse` 시그니처와 본문:

```java
    private GenerateCertificateResponseDTO buildGenerateResponse(
            String username,
            String medicalCertificate,
            String llmStatus,
            Map<String, Object> verification) {
        Employee employee = employeeRepository.findByUsername(username);
        Role role = employee != null ? employee.getRole() : Role.DEFAULT;
        String accessToken = jwtTokenProvider.generateAccessToken(username, role);
        String refreshToken = jwtTokenProvider.generateRefreshToken(username);

        GenerateCertificateResponseDTO response = new GenerateCertificateResponseDTO();
        response.setGrantType("Bearer");
        response.setAccessToken(accessToken);
        response.setRefreshToken(refreshToken);
        response.setMedicalCertificate(medicalCertificate);
        response.setLlmStatus(llmStatus);
        response.setVerification(verification);
        return response;
    }
```

- [ ] **Step 5: 배선 테스트 추가**

`apps/api/src/test/java/com/example/bitcomputer/serviceImpl/AgentDocumentServiceImplCertificateTest.java`
(Task 11 에서 만든 파일)에 추가한다:

```java
    @Test
    void generateCertificatePassesVerificationThrough() {
        Map<String, Object> verification = Map.of("status", "flagged");
        CertificateAgentResponse agentResponse = CertificateAgentResponse.builder()
                .medicalCertificate("소견")
                .llmStatus("real")
                .verification(verification)
                .build();
        when(certificateAgentClient.generate(any())).thenReturn(Optional.of(agentResponse));

        GenerateCertificateResponseDTO result = service.generateTestCertificate(
                "J00", "P1", "약가", "user");

        assertThat(result.getVerification()).isEqualTo(verification);
    }

    /** 에이전트 문장을 못 써서 템플릿으로 떨어지면 검증 결과도 없어야 한다. */
    @Test
    void templateFallbackHasNoVerification() {
        when(certificateAgentClient.generate(any())).thenReturn(Optional.empty());

        GenerateCertificateResponseDTO result = service.generateTestCertificate(
                "J00", "P1", "약가", "user");

        assertThat(result.getVerification()).isNull();
    }
```

`generateTestCertificate` 의 실제 시그니처를 읽고 인자를 맞춘다.

- [ ] **Step 6: 테스트 통과 확인**

Run: `cd apps/api && ./gradlew test`
Expected: 실패는 사전 존재 3건뿐(`PatientServiceImplTest$Create` ×2, `WaitingServiceImplTest$RegisterWaitingTest` ×1). 새 실패가 있으면 멈춘다.

- [ ] **Step 7: 뮤테이션 확인**

1. `response.setVerification(verification);` 을 지운다 → `generateCertificatePassesVerificationThrough` FAIL
2. `CertificateAgentResponse` 의 `verification` 필드를 지운다 → `roundTripPreservesVerification` FAIL

- [ ] **Step 8: 커밋**

```bash
git add apps/api/src/main/java/com/example/bitcomputer/model/CertificateAgentResponse.java apps/api/src/main/java/com/example/bitcomputer/model/GenerateCertificateResponseDTO.java apps/api/src/main/java/com/example/bitcomputer/serviceImpl/AgentDocumentServiceImpl.java apps/api/src/test/java/com/example/bitcomputer/model/CertificateAgentResponseTest.java apps/api/src/test/java/com/example/bitcomputer/serviceImpl/AgentDocumentServiceImplCertificateTest.java
git commit -m "feat(api): 진단서 verification 을 화면까지 전달"
```

---

### Task 6: validation-agent 계약과 검사 3종

**Files:**
- Create: `services/validation-agent/app/verification_contract.py`
- Create: `services/validation-agent/app/verification.py`
- Test: `services/validation-agent/tests/test_verification.py`

**Interfaces:**
- Produces: `verify_validation(*, pubmed_articles, finder_candidates, response_dict) -> VerificationResult`

`pubmed_articles` 는 `tools.py` 의 PubMed 툴이 돌려주는 `articles` 목록이다 —
각 항목이 `{"pmid", "title", "source", "pubdate", "abstract", "abstractSnippet"}`.

- [ ] **Step 1: 계약 파일 복제**

`services/prescription/verification_contract.py` 의 내용을
`services/validation-agent/app/verification_contract.py` 로 그대로 복사한다.
docstring 첫 줄만 다음으로 바꾼다:

```python
"""검증 결과 계약과 집계 규칙(validation-agent 사본).

services/prescription/verification_contract.py 와 동일해야 한다. 별도 Docker
빌드 컨텍스트라 공유 패키지 대신 복제한다. 동일성은 테스트로 고정한다.
"""
```

- [ ] **Step 2: 실패하는 테스트 작성**

`services/validation-agent/tests/test_verification.py`:

```python
import hashlib
import pathlib

from app.verification import verify_validation


ARTICLES = [
    {"pmid": "11111111", "title": "A", "abstract": "본문"},
    {"pmid": "22222222", "title": "B", "abstract": "본문"},
]


def _outcomes(result, check_id):
    return [c.outcome for c in result.checks if c.id == check_id]


def test_cited_pmid_present_passes():
    response = {
        "pubmedEvidenceSummary": "PMID 11111111 에 따르면 ...",
        "checks": [],
        "candidatePrescriptions": [],
        "reasoningTrace": [{"action": "A", "observation": {"status": "OK"}}],
    }
    result = verify_validation(
        pubmed_articles=ARTICLES, finder_candidates=[], response_dict=response)

    assert _outcomes(result, "cited_pmid_in_evidence") == ["ok"]


# 지어낸 논문 인용은 의료 맥락에서 가장 위험한 할루시네이션 부류다.
def test_invented_pmid_is_flagged():
    response = {
        "pubmedEvidenceSummary": "PMID 99999999 에 따르면 ...",
        "checks": [],
        "candidatePrescriptions": [],
        "reasoningTrace": [],
    }
    result = verify_validation(
        pubmed_articles=ARTICLES, finder_candidates=[], response_dict=response)

    assert result.status == "flagged"
    assert "flagged" in _outcomes(result, "cited_pmid_in_evidence")


def test_no_pmid_cited_is_skipped():
    response = {"pubmedEvidenceSummary": "근거 없음", "checks": [],
                "candidatePrescriptions": [], "reasoningTrace": []}
    result = verify_validation(
        pubmed_articles=ARTICLES, finder_candidates=[], response_dict=response)

    assert _outcomes(result, "cited_pmid_in_evidence") == ["skipped"]


# GC-2. 조회된 논문이 없으면 통과가 아니라 미확인이다.
def test_no_articles_never_passes_pmid_check():
    response = {"pubmedEvidenceSummary": "PMID 11111111", "checks": [],
                "candidatePrescriptions": [], "reasoningTrace": []}
    result = verify_validation(
        pubmed_articles=[], finder_candidates=[], response_dict=response)

    assert _outcomes(result, "cited_pmid_in_evidence") == ["skipped"]


def test_candidate_outside_finder_is_flagged():
    response = {"pubmedEvidenceSummary": "", "checks": [],
                "candidatePrescriptions": [{"prescription_code": "Z99"}],
                "reasoningTrace": []}
    result = verify_validation(
        pubmed_articles=[], finder_candidates=[{"prescription_code": "A01"}],
        response_dict=response)

    assert "flagged" in _outcomes(result, "candidates_from_finder")


def test_trace_step_without_observation_is_flagged():
    response = {"pubmedEvidenceSummary": "", "checks": [],
                "candidatePrescriptions": [],
                "reasoningTrace": [{"action": "A", "observation": None}]}
    result = verify_validation(
        pubmed_articles=[], finder_candidates=[], response_dict=response)

    assert "flagged" in _outcomes(result, "trace_step_has_observation")


def test_does_not_mutate_response():
    response = {"pubmedEvidenceSummary": "PMID 11111111", "checks": [],
                "candidatePrescriptions": [], "reasoningTrace": []}
    import copy
    before = copy.deepcopy(response)
    verify_validation(pubmed_articles=ARTICLES, finder_candidates=[], response_dict=response)

    assert response == before


# 계약이 두 서비스에 복제돼 있다. 어긋나면 두 서비스가 다른 집계 규칙을 쓰게 된다.
def test_contract_copy_matches_prescription():
    # tests/ -> validation-agent -> services -> (repo root)
    here = pathlib.Path(__file__).resolve().parents[1] / "app" / "verification_contract.py"
    other = (pathlib.Path(__file__).resolve().parents[2]
             / "prescription" / "verification_contract.py")
    assert here.exists() and other.exists(), (here, other)
    def body(p):
        text = p.read_text(encoding="utf-8")
        return text[text.index('"""', text.index('"""') + 3) + 3:]
    assert hashlib.sha256(body(here).encode()).hexdigest() == \
           hashlib.sha256(body(other).encode()).hexdigest()
```

- [ ] **Step 3: 테스트가 실패하는지 확인**

Run: `cd services/validation-agent && python -m pytest tests/test_verification.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.verification'`

- [ ] **Step 4: 검증기 구현**

`services/validation-agent/app/verification.py`:

```python
"""검증 에이전트 출력을 도구 관측값과 대조한다.

순수 함수만 둔다(GC-1). 출력을 변형하지 않는다(GC-3).
spec: Docs/superpowers/specs/2026-08-29-runtime-verification-design.md §6.3
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence

from app.verification_contract import CheckResult, VerificationResult, aggregate_status

PMID_PATTERN = re.compile(r"\b\d{7,8}\b")


def _code(row: Any) -> str:
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
    known_pmids.discard("")
    cited_text = " ".join([
        str(response_dict.get("pubmedEvidenceSummary") or ""),
        " ".join(str(c) for c in (response_dict.get("checks") or [])),
    ])
    cited = set(PMID_PATTERN.findall(cited_text))

    if not known_pmids:
        checks.append(CheckResult(
            id="cited_pmid_in_evidence", target="response", outcome="skipped",
            evidence="조회된 PubMed 논문이 없어 인용을 대조할 수 없음"))
    elif not cited:
        checks.append(CheckResult(
            id="cited_pmid_in_evidence", target="response", outcome="skipped",
            evidence="응답에 PMID 인용이 없음"))
    else:
        unknown = sorted(cited - known_pmids)
        checks.append(CheckResult(
            id="cited_pmid_in_evidence", target="response",
            outcome="flagged" if unknown else "ok",
            evidence=(f"조회 결과에 없는 PMID: {unknown}" if unknown
                      else f"인용 PMID {sorted(cited)} 가 모두 조회 결과에 있음")))

    # --- candidates_from_finder ---
    known_codes = {_code(r) for r in finder_candidates}
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
        outside = sorted({_code(r) for r in returned} - known_codes - {""})
        checks.append(CheckResult(
            id="candidates_from_finder", target="response",
            outcome="flagged" if outside else "ok",
            evidence=(f"finder 관측값 밖의 코드: {outside}" if outside
                      else f"후보 {len(returned)}건이 모두 finder 관측값에서 옴")))

    # --- trace_step_has_observation (구조 검사가 아니다: 관측 기록 대조다) ---
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

    if all(c.outcome == "skipped" for c in checks):
        skipped_reason = "도구 관측값이 없어 대조를 수행하지 못했습니다."

    return VerificationResult(
        status=aggregate_status(checks), checks=checks, skippedReason=skipped_reason)
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `cd services/validation-agent && python -m pytest tests/test_verification.py -q`
Expected: PASS (8개)

- [ ] **Step 6: 뮤테이션 확인**

1. `cited_pmid_in_evidence` 의 `unknown` 을 항상 빈 목록으로 → `test_invented_pmid_is_flagged` FAIL
2. `known_pmids` 가 빌 때 `"skipped"` 대신 `"ok"` 로 → `test_no_articles_never_passes_pmid_check` FAIL
3. `candidates_from_finder` 의 `outside` 를 항상 빈 목록으로 → `test_candidate_outside_finder_is_flagged` FAIL
4. `trace_step_has_observation` 의 `missing` 을 항상 빈 목록으로 → `test_trace_step_without_observation_is_flagged` FAIL
5. `app/verification_contract.py` 의 `STRUCTURAL_CHECK_IDS` 를 비운다 → `test_contract_copy_matches_prescription` FAIL

- [ ] **Step 7: 커밋**

```bash
git add services/validation-agent/app/verification_contract.py services/validation-agent/app/verification.py services/validation-agent/tests/test_verification.py
git commit -m "feat(validation-agent): 도구 관측값 대조 검사 3종"
```

---

### Task 7: validation-agent 배선과 처방 검증 결과 전달

처방 경로는 Java DTO 를 거치지 않는다. `PrescriptionAgentClient` 는 죽은 코드이고,
살아 있는 경로는 web → Java → RabbitMQ → validation-agent → `prescription_api` 다.
따라서 `prescription_api` 의 `verification` 은 `tools.py` 가 실어 날라야 화면에 도달한다.
Task 11 의 `recommendationLlmStatus` 와 같은 형태다.

**Files:**
- Modify: `services/validation-agent/app/tools.py`
- Modify: `services/validation-agent/app/agent.py`
- Modify: `services/validation-agent/app/models.py`
- Test: `services/validation-agent/tests/test_verification.py` (추가)

**Interfaces:**
- Consumes: Task 6 의 `verify_validation(...)`
- Produces: `ValidationAgentResponse.verification: Optional[Dict[str, Any]]`

- [ ] **Step 1: 실패하는 테스트 작성**

`services/validation-agent/tests/test_verification.py` 에 추가:

```python
from app.models import ValidationAgentResponse


def test_response_model_has_verification_field():
    assert "verification" in ValidationAgentResponse.model_fields


def test_verification_defaults_to_none():
    """기본값을 만들면 검증하지 않은 것이 검증된 것처럼 보인다."""
    assert ValidationAgentResponse.model_fields["verification"].default is None
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `cd services/validation-agent && python -m pytest tests/test_verification.py -q`
Expected: FAIL — `verification` 필드 없음

- [ ] **Step 3: 응답 모델에 필드 추가**

`services/validation-agent/app/models.py` 의 `ValidationAgentResponse` 에서
`llmStatus` 아래에 추가한다:

```python
    # 출력이 도구 관측값으로 추적되는지. llmStatus 와 다른 축이다.
    # 기본값을 두지 않는 이유는 llmStatus 와 같다 — 없는 것을 있는 것처럼
    # 보이게 하면 안 된다. 웹은 None 을 "미검증"으로 렌더한다.
    verification: Optional[Dict[str, Any]] = None
```

- [ ] **Step 4: tools.py 가 처방 검증 결과를 실어 보낸다**

`services/validation-agent/app/tools.py` 의 `prescription_finder` 성공 반환 블록에
키를 추가한다(`recommendationLlmStatus` 바로 아래):

```python
        # prescription_api 자신의 검증 결과. 이 스텝의 근거 정보이지
        # 검증 에이전트 자신의 판정이 아니다 — 최상위에 섞지 않는다.
        "recommendationVerification": body.get("verification"),
```

실패 반환 블록에도 같은 키를 넣되 값은 `None` 이다:

```python
        "recommendationVerification": None,
```

- [ ] **Step 5: agent.py 가 검증기를 부른다**

`run_validation_agent` 의 응답 조립부에서, `llmStatus` 를 넣는 줄 근처에 추가한다:

```python
        "verification": _safe_verify(state, response_payload),
```

그리고 모듈에 안전 래퍼를 추가한다:

```python
def _safe_verify(state: Any, response_payload: Dict[str, Any]) -> Dict[str, Any]:
    """검증을 돌리되 본 응답을 실패시키지 않는다(GC-4)."""
    try:
        return verify_validation(
            pubmed_articles=state.get("pubmed_articles") or [],
            finder_candidates=state.get("finder_candidates") or [],
            response_dict=response_payload,
        ).to_dict()
    except Exception as exc:  # noqa: BLE001
        logger.warning("검증 실패, skipped 로 처리: %s", type(exc).__name__)
        return {
            "status": "skipped",
            "checks": [],
            "skippedReason": f"검증기 예외: {type(exc).__name__}",
        }
```

`state` 에 `pubmed_articles` 와 `finder_candidates` 가 없으면, 각 도구 호출 지점에서
관측값의 `articles` / `candidatePrescriptions` 를 state 에 보관하도록 추가한다.
**요청이 아니라 관측값을 보관해야 한다(spec §4.1).**

import 를 추가한다:

```python
from app.verification import verify_validation
```

- [ ] **Step 6: 배선 테스트 추가**

```python
def test_agent_verification_uses_observations_not_request(monkeypatch):
    """검증기에 도구 관측값이 간다. 요청을 넘기면 검증이 무의미해진다."""
    import app.agent as agent

    seen = {}

    def spy(*, pubmed_articles, finder_candidates, response_dict):
        seen["articles"] = pubmed_articles
        raise RuntimeError("여기서 멈춘다")

    monkeypatch.setattr(agent, "verify_validation", spy)
    result = agent._safe_verify({"pubmed_articles": [{"pmid": "1"}]}, {})

    assert seen["articles"] == [{"pmid": "1"}]
    assert result["status"] == "skipped"
```

- [ ] **Step 7: 전체 확인**

Run: `cd services/validation-agent && python -m pytest -q`
Expected: 기존 33 + 신규 11 = 44 통과

- [ ] **Step 8: 뮤테이션 확인**

1. `_safe_verify` 의 `except` 에서 `"skipped"` 를 `"passed"` 로 → 배선 테스트 FAIL
2. `"verification": _safe_verify(...)` 줄을 지운다 → 모델 필드 테스트는 여전히 통과한다. 응답에 실제로 실리는지 확인하는 테스트를 함께 넣는다:

```python
def test_response_actually_carries_verification(monkeypatch):
    """모델에 필드가 있는 것과 응답이 그것을 채우는 것은 다른 말이다.
    배선이 끊겨도 필드 존재 테스트는 통과하므로 이 단언이 필요하다."""
    _install_llm_decisions(monkeypatch)

    response = run_validation_agent(_request())

    assert response.verification is not None
    assert response.verification["status"] in {"passed", "flagged", "skipped"}
```

`_install_llm_decisions` 와 `_request` 는 `tests/test_llm_status.py` 의 기존 헬퍼다. 그 파일에서 import 하거나 같은 형태로 복제한다.

- [ ] **Step 9: 커밋**

```bash
git add services/validation-agent/app/models.py services/validation-agent/app/tools.py services/validation-agent/app/agent.py services/validation-agent/tests/test_verification.py
git commit -m "feat(validation-agent): 응답에 verification 배선, 처방 검증 결과 전달"
```

---

### Task 8: validation-agent Java DTO 확장

**Files:**
- Modify: `apps/api/src/main/java/com/example/bitcomputer/model/ValidationAgentResponse.java`
- Test: `apps/api/src/test/java/com/example/bitcomputer/model/ValidationAgentResponseTest.java`

**Interfaces:**
- Produces: `ValidationAgentResponse.verification: Map<String, Object>`

- [ ] **Step 1: 실패하는 테스트 작성**

기존 `ValidationAgentResponseTest.java` 에 추가:

```java
    @Test
    void roundTripPreservesVerification() throws Exception {
        String upstream = "{"
                + "\"overallStatus\":\"PASS\",\"summary\":\"ok\","
                + "\"verification\":{\"status\":\"flagged\",\"checks\":[],"
                + "\"skippedReason\":null}"
                + "}";

        ValidationAgentResponse parsed =
                objectMapper.readValue(upstream, ValidationAgentResponse.class);
        String roundTripped = objectMapper.writeValueAsString(parsed);

        assertThat(parsed.getVerification()).isNotNull();
        assertThat(roundTripped).contains("\"status\":\"flagged\"");
    }

    @Test
    void missingVerificationIsNull() throws Exception {
        ValidationAgentResponse parsed = objectMapper.readValue(
                "{\"overallStatus\":\"PASS\",\"summary\":\"s\"}", ValidationAgentResponse.class);

        assertThat(parsed.getVerification()).isNull();
    }
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `cd apps/api && ./gradlew test --tests "*ValidationAgentResponseTest*"`
Expected: FAIL — `getVerification()` 없음

- [ ] **Step 3: 필드 추가**

`ValidationAgentResponse.java` 의 `llmStatus` 아래:

```java
    /** 출력이 도구 관측값으로 추적되는지: {status, checks[], skippedReason}. */
    private Map<String, Object> verification;
```

`java.util.Map` 은 이미 import 돼 있다(다른 필드가 쓴다).

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd apps/api && ./gradlew test`
Expected: 실패는 사전 존재 3건뿐

- [ ] **Step 5: 뮤테이션 확인**

`verification` 필드를 지운다 → `roundTripPreservesVerification` FAIL

- [ ] **Step 6: 커밋**

```bash
git add apps/api/src/main/java/com/example/bitcomputer/model/ValidationAgentResponse.java apps/api/src/test/java/com/example/bitcomputer/model/ValidationAgentResponseTest.java
git commit -m "fix(api): 동기 검증 경로가 verification 을 버리지 않게"
```

---

### Task 9: 웹 공용 표시 헬퍼와 처방 표

**Files:**
- Create: `apps/web/src/utils/verificationNotice.ts`
- Create: `apps/web/src/utils/__tests__/verificationNotice.test.ts`
- Modify: `apps/web/src/services/history.ts`
- Modify: `apps/web/src/components/Diagnosis.tsx`
- Modify: `apps/web/src/components/__tests__/Diagnosis.test.tsx`

**Interfaces:**
- Produces: `verificationNotice(status) -> {label, tone} | null`, `itemVerificationOutcome(verification, target) -> "ok"|"flagged"|"skipped"`

- [ ] **Step 1: 실패하는 테스트 작성**

`apps/web/src/utils/__tests__/verificationNotice.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { itemVerificationOutcome, verificationNotice } from "../verificationNotice";

describe("verificationNotice", () => {
  it("passed 면 아무것도 표시하지 않는다", () => {
    expect(verificationNotice("passed")).toBeNull();
  });

  it("flagged 와 skipped 는 다른 문구를 쓴다", () => {
    const flagged = verificationNotice("flagged");
    const skipped = verificationNotice("skipped");
    expect(flagged!.label).toContain("근거 불일치");
    expect(skipped!.label).toContain("미검증");
    expect(flagged!.label).not.toBe(skipped!.label);
  });

  it("flagged 가 skipped 보다 강한 tone 을 쓴다", () => {
    expect(verificationNotice("flagged")!.tone).toBe("danger");
    expect(verificationNotice("skipped")!.tone).toBe("warning");
  });

  // fail-closed. 필드가 없는 응답을 "검증됨"으로 읽으면 이 표시가 존재할 이유가 사라진다.
  it("값이 없거나 계약 밖이면 미검증으로 본다", () => {
    expect(verificationNotice(undefined)).not.toBeNull();
    expect(verificationNotice(null)).not.toBeNull();
    expect(verificationNotice("PASSED")).not.toBeNull();
    expect(verificationNotice("bogus")).not.toBeNull();
  });
});

describe("itemVerificationOutcome", () => {
  const verification = {
    status: "flagged",
    checks: [
      { id: "code_in_candidates", target: "prescription[1]", outcome: "ok", evidence: "" },
      { id: "dosage_verbatim", target: "prescription[2]", outcome: "flagged", evidence: "" },
      { id: "code_in_candidates", target: "prescription[3]", outcome: "skipped", evidence: "" },
    ],
  };

  it("항목에 flagged 가 있으면 flagged", () => {
    expect(itemVerificationOutcome(verification, "prescription[2]")).toBe("flagged");
  });

  it("항목이 전부 ok 면 ok", () => {
    expect(itemVerificationOutcome(verification, "prescription[1]")).toBe("ok");
  });

  it("항목이 skipped 만 있으면 skipped", () => {
    expect(itemVerificationOutcome(verification, "prescription[3]")).toBe("skipped");
  });

  it("해당 항목의 검사가 없으면 skipped", () => {
    expect(itemVerificationOutcome(verification, "prescription[9]")).toBe("skipped");
  });

  it("verification 자체가 없으면 skipped", () => {
    expect(itemVerificationOutcome(undefined, "prescription[1]")).toBe("skipped");
  });
});
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `cd apps/web && node .yarn/releases/yarn-4.12.0.cjs vitest run src/utils/__tests__/verificationNotice.test.ts`
Expected: FAIL — 모듈 없음

- [ ] **Step 3: 헬퍼 구현**

`apps/web/src/utils/verificationNotice.ts`:

```ts
// verification 은 "출력이 조회 결과로 추적되나"다. llmStatus("모델이 돌았나")와
// 다른 축이므로 같은 자리에 같은 모양으로 쌓지 않는다(spec §7.1).
//
// "passed" 정확 일치만 무표시다. 값이 없거나 계약 밖이면 미검증으로 본다 —
// 이 프로젝트의 다른 모든 경계와 같은 방향(fail-closed)이다.

export type VerificationOutcome = "ok" | "flagged" | "skipped";

export type VerificationCheck = {
  id: string;
  target: string;
  outcome: string;
  evidence: string;
};

export type Verification = {
  status?: string | null;
  checks?: VerificationCheck[] | null;
  skippedReason?: string | null;
};

export function verificationNotice(
  status: string | null | undefined
): { label: string; tone: "danger" | "warning" } | null {
  if (status === "passed") return null;
  if (status === "flagged") {
    return { label: "근거 불일치", tone: "danger" };
  }
  return { label: "미검증", tone: "warning" };
}

// 항목 단위 표시(spec §7.2). 전역 배지 하나로 뭉치면 어느 처방이 문제인지
// 알 수 없고, 그건 표시하지 않는 것과 크게 다르지 않다.
export function itemVerificationOutcome(
  verification: Verification | null | undefined,
  target: string
): VerificationOutcome {
  const checks = verification?.checks;
  if (!Array.isArray(checks)) return "skipped";
  const mine = checks.filter((c) => c && c.target === target);
  if (mine.length === 0) return "skipped";
  if (mine.some((c) => c.outcome === "flagged")) return "flagged";
  if (mine.every((c) => c.outcome === "ok")) return "ok";
  return "skipped";
}
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd apps/web && node .yarn/releases/yarn-4.12.0.cjs vitest run src/utils/__tests__/verificationNotice.test.ts`
Expected: PASS (10개)

- [ ] **Step 5: 타입 추가**

`apps/web/src/services/history.ts` 의 `ValidationJobResponse["result"]` 에 추가한다:

```ts
    verification?: Verification | null;
```

`import type { Verification } from "@/utils/verificationNotice";` 를 추가한다.

- [ ] **Step 6: 처방 표에 항목 단위 표시**

`apps/web/src/components/Diagnosis.tsx` 에서 `aiVerification` state 를 `aiRecommendations`,
`aiLlmStatus` 와 **같은 생명주기**로 추가한다. `setAiRecommendations` 를 부르는 세 지점
(성공 두 곳, 리셋 한 곳) 전부에서 함께 갱신한다 — 배지가 자기가 설명하는 데이터와
다른 생명주기를 가지면 그 자체가 결함이다(Task 10 리뷰에서 확인된 함정).

추천 표의 각 행에 다음을 렌더한다:

```tsx
{(() => {
  const outcome = itemVerificationOutcome(aiVerification, `prescription[${item.rank}]`);
  if (outcome === "ok") return null;
  const notice = verificationNotice(outcome === "flagged" ? "flagged" : "skipped");
  return <Badge tone={notice!.tone}>{notice!.label}</Badge>;
})()}
```

표 헤더에 요약 한 줄:

```tsx
{aiRecommendations.length > 0 && (
  <span className={styles.verificationSummary}>
    {`검증: ${aiRecommendations.length}건 중 ${
      aiRecommendations.filter(
        (r) => itemVerificationOutcome(aiVerification, `prescription[${r.rank}]`) !== "ok"
      ).length
    }건 미확인`}
  </span>
)}
```

`Diagnosis.module.css` 에 여백만 주는 클래스를 추가한다. 색 리터럴을 쓰지 않는다
(`no-hardcoded-color` 가드가 막는다):

```css
.verificationSummary {
  font-size: var(--font-size-xs);
  color: var(--text-muted);
  margin-left: var(--space-2);
}
```

- [ ] **Step 7: 렌더 경로 테스트 추가**

`apps/web/src/components/__tests__/Diagnosis.test.tsx` 에 추가한다. 기존 파일의
`mockJobWithTrace` 관례를 그대로 따른다.

```tsx
it("근거 불일치인 처방 행에 표시가 붙는다", async () => {
  mockJobWithVerification("job-v-1", {
    status: "flagged",
    checks: [
      { id: "code_in_candidates", target: "prescription[1]", outcome: "flagged", evidence: "" },
    ],
  });

  renderDiagnosis();
  fireEvent.click(screen.getByRole("button", { name: "AI 처방 추천" }));

  expect(await screen.findByText("근거 불일치")).toBeInTheDocument();
});

it("verification 이 없으면 미검증으로 표시한다", async () => {
  mockJobWithVerification("job-v-2", undefined);

  renderDiagnosis();
  fireEvent.click(screen.getByRole("button", { name: "AI 처방 추천" }));

  expect(await screen.findByText("미검증")).toBeInTheDocument();
});

it("모달을 닫아도 패널의 검증 표시가 남는다", async () => {
  mockJobWithVerification("job-v-3", {
    status: "flagged",
    checks: [
      { id: "code_in_candidates", target: "prescription[1]", outcome: "flagged", evidence: "" },
    ],
  });

  renderDiagnosis();
  fireEvent.click(screen.getByRole("button", { name: "AI 처방 추천" }));
  await screen.findByRole("dialog");
  fireEvent.click(screen.getByRole("button", { name: "확인" }));

  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  expect(screen.getByText("근거 불일치")).toBeInTheDocument();
});
```

`mockJobWithVerification` 은 기존 `mockJobWithTrace` 를 본떠 이 파일 안에 만든다.

- [ ] **Step 8: 전체 확인**

Run: `cd apps/web && node .yarn/releases/yarn-4.12.0.cjs vitest run`
Expected: 150 + 13 = 163 통과

Run: `cd apps/web && node .yarn/releases/yarn-4.12.0.cjs tsc --noEmit`
Expected: 출력 없음

- [ ] **Step 9: 뮤테이션 확인**

1. `verificationNotice` 의 `"passed"` 분기를 `"flagged"` 로 → fail-closed 테스트 FAIL
2. `itemVerificationOutcome` 이 항상 `"ok"` 를 반환하게 → 렌더 테스트 FAIL
3. 패널의 배지를 지운다 → "모달을 닫아도" 테스트 FAIL
4. `flagged` 와 `skipped` 의 label 을 같게 → "다른 문구를 쓴다" 테스트 FAIL

- [ ] **Step 10: 커밋**

```bash
git add apps/web/src/utils/verificationNotice.ts apps/web/src/utils/__tests__/verificationNotice.test.ts apps/web/src/services/history.ts apps/web/src/components/Diagnosis.tsx apps/web/src/components/Diagnosis.module.css apps/web/src/components/__tests__/Diagnosis.test.tsx
git commit -m "feat(web): 처방 추천에 항목 단위 검증 표시"
```

---

### Task 10: 웹 진단서 모달과 검증 이유 목록

**Files:**
- Modify: `apps/web/src/services/agent.ts`
- Modify: `apps/web/src/components/MedicalCertificate.tsx`
- Modify: `apps/web/src/components/__tests__/MedicalCertificate.test.tsx`
- Modify: `apps/web/src/components/Diagnosis.tsx`
- Modify: `apps/web/src/components/__tests__/Diagnosis.test.tsx`

- [ ] **Step 1: 웹 타입에 필드 추가**

`apps/web/src/services/agent.ts` 의 `DocumentGenerateResponse` 에:

```ts
  verification?: Verification | null;
```

`import type { Verification } from "@/utils/verificationNotice";` 를 추가한다.

- [ ] **Step 2: 실패하는 테스트 작성**

`apps/web/src/components/__tests__/MedicalCertificate.test.tsx` 에 추가:

```tsx
it("진단서 검증이 flagged 면 미리보기에 근거 불일치가 뜬다", async () => {
  vi.mocked(generateDocumentCertificateByHistory).mockResolvedValue({
    grantType: "Bearer", accessToken: "a", refreshToken: "r",
    medicalCertificate: "소견",
    llmStatus: "real",
    verification: {
      status: "flagged",
      checks: [{ id: "cited_code_known", target: "certificate", outcome: "flagged", evidence: "K52.9" }],
    },
  });
  renderWithAppliedDiagnosis();
  fireEvent.click(screen.getByRole("button", { name: /AI/ }));

  const dialog = await screen.findByRole("dialog");
  expect(await within(dialog).findByText("근거 불일치")).toBeInTheDocument();
});

it("verification 이 없으면 미검증으로 표시한다", async () => {
  vi.mocked(generateDocumentCertificateByHistory).mockResolvedValue({
    grantType: "Bearer", accessToken: "a", refreshToken: "r",
    medicalCertificate: "소견", llmStatus: "real",
  });
  renderWithAppliedDiagnosis();
  fireEvent.click(screen.getByRole("button", { name: /AI/ }));

  const dialog = await screen.findByRole("dialog");
  expect(await within(dialog).findByText("미검증")).toBeInTheDocument();
});

it("passed 면 검증 표시가 없다", async () => {
  vi.mocked(generateDocumentCertificateByHistory).mockResolvedValue({
    grantType: "Bearer", accessToken: "a", refreshToken: "r",
    medicalCertificate: "소견", llmStatus: "real",
    verification: { status: "passed", checks: [] },
  });
  renderWithAppliedDiagnosis();
  fireEvent.click(screen.getByRole("button", { name: /AI/ }));

  const dialog = await screen.findByRole("dialog");
  await within(dialog).findByLabelText("AI 생성 소견 미리보기");
  expect(within(dialog).queryByText("미검증")).toBeNull();
  expect(within(dialog).queryByText("근거 불일치")).toBeNull();
});
```

- [ ] **Step 3: 테스트가 실패하는지 확인**

Run: `cd apps/web && node .yarn/releases/yarn-4.12.0.cjs vitest run src/components/__tests__/MedicalCertificate.test.tsx`
Expected: FAIL — 표시가 없다

- [ ] **Step 4: 미리보기 모달에 표시**

`MedicalCertificate.tsx` 의 `handleAiGenerate` 에서 상태를 함께 담는다:

```tsx
      setAiPreviewModal({ text, llmStatus: res.llmStatus, verification: res.verification });
```

`aiPreviewModal` state 타입에 `verification?: Verification | null` 을 추가한다.

모달 본문의 `llmStatus` 배지 블록 아래(같은 줄이 아니라 별도 줄)에 추가한다:

```tsx
{(() => {
  const notice = verificationNotice(aiPreviewModal.verification?.status);
  return notice ? (
    <div className={styles.aiPreviewNotice}>
      <span className={styles.aiPreviewNoticeLabel}>근거</span>
      <Badge tone={notice.tone}>{notice.label}</Badge>
    </div>
  ) : null;
})()}
```

`근거` 접두어가 `llmStatus` 의 `모델` 접두어와 짝을 이뤄 두 신호를 구분한다(spec §7.1).

`MedicalCertificate.module.css` 에 `.aiPreviewNoticeLabel` 을 추가한다:

```css
.aiPreviewNoticeLabel {
  font-size: var(--font-size-xs);
  color: var(--text-muted);
  margin-right: var(--space-2);
}
```

- [ ] **Step 5: 검증 이유 목록에 표시**

`Diagnosis.tsx` 의 검증 모달에서 `modalReason` 문단 아래, `validationReasons` 목록 위에
다음을 렌더한다:

```tsx
{(() => {
  const notice = verificationNotice(validationModal.result?.verification?.status);
  return notice ? (
    <div className={styles.modalVerification}>
      <span className={styles.modalVerificationLabel}>근거</span>
      <Badge tone={notice.tone}>{notice.label}</Badge>
    </div>
  ) : null;
})()}
```

`modalCardHead` 안에 넣지 않는다 — 거기에는 이미 `overallStatus` 배지와 `모델` 배지가
있고, 세 번째 배지를 같은 줄에 쌓으면 셋 다 안 읽힌다(spec §7.1).

`Diagnosis.module.css` 에 추가한다:

```css
.modalVerification {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: var(--space-3);
}

.modalVerificationLabel {
  font-size: var(--font-size-xs);
  color: var(--text-muted);
}
```

테스트를 함께 추가한다:

```tsx
it("검증 모달에 근거 표시가 뜬다", async () => {
  mockJobWithVerification("job-v-4", { status: "flagged", checks: [] });

  renderDiagnosis();
  fireEvent.click(screen.getByRole("button", { name: "AI 처방 추천" }));

  const dialog = await screen.findByRole("dialog");
  expect(await within(dialog).findByText("근거")).toBeInTheDocument();
  expect(within(dialog).getByText("근거 불일치")).toBeInTheDocument();
});
```

- [ ] **Step 6: 테스트 통과 확인**

Run: `cd apps/web && node .yarn/releases/yarn-4.12.0.cjs vitest run`
Expected: 163 + 3 + (Diagnosis 추가분) 통과

Run: `cd apps/web && node .yarn/releases/yarn-4.12.0.cjs tsc --noEmit`
Expected: 출력 없음

- [ ] **Step 7: 뮤테이션 확인**

1. 진단서 모달의 배지를 지운다 → 세 테스트 중 둘 FAIL
2. `근거` 접두어를 지운다 → 이를 고정하는 테스트가 없으면 추가한다(Task 11 리뷰에서 `모델` 접두어가 무테스트로 남아 지적된 선례가 있다)

- [ ] **Step 8: 커밋**

```bash
git add apps/web/src/services/agent.ts apps/web/src/components/MedicalCertificate.tsx apps/web/src/components/MedicalCertificate.module.css apps/web/src/components/Diagnosis.tsx apps/web/src/components/__tests__/MedicalCertificate.test.tsx apps/web/src/components/__tests__/Diagnosis.test.tsx
git commit -m "feat(web): 진단서와 검증 결과에 근거 표시"
```

---

### Task 11: B(NLI) 플래그, 기본 off

spec §3.2 대로 A 와 독립 출시 가능하다. Task 10 까지로 끊어도 된다.

**범위를 진단서로 좁힌다.** spec §8.2 는 세 호출자(`prescription-api-nli`,
`certificate-api-nli`, `validation-agent-nli`)를 열거하지만 이 태스크는 진단서만 한다.
근거: 진단서는 자유 산문이라 결정론적 검사로 얻는 것이 얇고(spec §6.2) NLI 구현이
이미 있다. 처방은 항목이 구조화돼 있어 집합 대조가 이미 강하고, 검증 에이전트의
PMID 대조도 마찬가지다. 나머지 두 호출자는 spec §11 의 비용·지연 실측 뒤에
판단한다 — 측정 없이 세 서비스에 2차 호출을 붙이면 비용이 세 배가 되는데
그 값이 얼마인지 아무도 모른다.

**Files:**
- Modify: `services/prescription/certificate_verification.py`
- Modify: `services/prescription/certificate_api.py`
- Modify: `infra/.env.example`
- Modify: `infra/docker-compose.yml`
- Test: `services/prescription/tests/test_certificate_nli.py`

**Interfaces:**
- Produces: `verify_certificate_nli(*, premise: str, text: str, call_llm) -> List[CheckResult]`

`call_llm` 은 주입되는 호출 함수다 — 검증기 자체는 순수 함수로 남고, I/O 는 호출자가 넣는다.

- [ ] **Step 1: 실패하는 테스트 작성**

`services/prescription/tests/test_certificate_nli.py`:

```python
from certificate_verification import verify_certificate_nli


def test_entailed_sentences_pass():
    def fake_llm(premise, hypothesis):
        return "ENTAILMENT"

    checks = verify_certificate_nli(
        premise="급성 비인두염(J00) 진단", text="환자는 급성 비인두염입니다.",
        call_llm=fake_llm)

    assert [c.outcome for c in checks] == ["ok"]


def test_contradiction_is_flagged():
    def fake_llm(premise, hypothesis):
        return "CONTRADICTION"

    checks = verify_certificate_nli(
        premise="급성 비인두염(J00) 진단", text="환자는 골절 상태입니다.",
        call_llm=fake_llm)

    assert [c.outcome for c in checks] == ["flagged"]


# GC-2 의 NLI 판. 2차 호출이 실패하면 통과가 아니라 미확인이다.
# 검증기가 자기 실패를 통과로 바꾸면 검증층이 있는 이유가 사라진다.
def test_llm_failure_is_skipped_not_ok():
    def boom(premise, hypothesis):
        raise TimeoutError("30초 초과")

    checks = verify_certificate_nli(
        premise="급성 비인두염(J00) 진단", text="환자는 급성 비인두염입니다.",
        call_llm=boom)

    assert [c.outcome for c in checks] == ["skipped"]
    assert "TimeoutError" in checks[0].evidence


def test_unknown_verdict_is_skipped():
    def weird(premise, hypothesis):
        return "아무말"

    checks = verify_certificate_nli(
        premise="p", text="환자는 급성 비인두염입니다.", call_llm=weird)

    assert [c.outcome for c in checks] == ["skipped"]


def test_empty_premise_returns_no_checks():
    checks = verify_certificate_nli(premise="", text="문장.", call_llm=lambda p, h: "ENTAILMENT")
    assert checks == []
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `cd services/prescription && python -m pytest tests/test_certificate_nli.py -q`
Expected: FAIL — `verify_certificate_nli` 없음

- [ ] **Step 3: NLI 검사 구현**

`services/prescription/certificate_verification.py` 에 추가한다:

```python
SENTENCE_SPLIT = re.compile(r"(?<=[.!?。])|\n+")

# 모델이 돌려주는 판정 문자열. 이 셋 밖의 값은 판정 실패로 본다 —
# 알 수 없는 응답을 통과로 읽으면 검증층이 스스로를 무력화한다.
_VERDICT_OK = "ENTAILMENT"
_VERDICT_BAD = {"CONTRADICTION", "NEUTRAL"}


def verify_certificate_nli(*, premise: str, text: str, call_llm) -> List[CheckResult]:
    """소견 각 문장이 premise 에서 함의되는지 모델에게 묻는다.

    검증기는 순수 함수로 남는다 — I/O 는 `call_llm` 으로 주입받는다(GC-1).
    호출 실패·타임아웃·알 수 없는 판정은 전부 skipped 다. 절대 ok 가 아니다.
    """
    if not premise.strip():
        return []

    sentences = [s.strip() for s in SENTENCE_SPLIT.split(text or "") if s and s.strip()]
    checks: List[CheckResult] = []
    for index, sentence in enumerate(sentences):
        target = f"sentence[{index}]"
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
```

`nli_entailment` 은 근거 검사다 — `STRUCTURAL_CHECK_IDS` 에 넣지 않는다.

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd services/prescription && python -m pytest tests/test_certificate_nli.py -q`
Expected: PASS (5개)

- [ ] **Step 5: 플래그와 호출 함수 배선**

`certificate_api.py` 에 추가한다:

```python
NLI_ENABLED = os.environ.get("LLM_VERIFICATION_NLI", "off").strip().lower() == "on"
NLI_TIMEOUT_SECONDS = float(os.environ.get("LLM_VERIFICATION_NLI_TIMEOUT_SECONDS", "30"))
```

NLI 호출은 게이트웨이를 거치고 `X-LLM-Caller: certificate-api-nli` 헤더를 쓴다.
**재시도하지 않는다.** 게이트웨이 총예산 136.5초에 NLI 예산이 더해지면 호출자
타임아웃 180초를 넘어 사다리가 뒤집힌다(spec §8.4).

`_safe_verify_certificate` 안에서, 결정론적 검사 결과에 NLI 검사를 이어 붙인다.
`NLI_ENABLED` 가 false 면 아무것도 붙이지 않는다.

- [ ] **Step 6: 환경 변수 등록**

`infra/.env.example` 에 추가한다(순서 규칙에 맞춰 `LLM_GATEWAY_TIMEOUT_SECONDS` 근처):

```
# 진단서 소견의 문장별 함의 판정을 2차 LLM 호출로 수행할지.
# 켜면 요청마다 게이트웨이 호출이 하나 더 붙는다. 비용은 X-LLM-Caller 가
# *-nli 로 분리돼 계측된다. spec §11 의 실측 전에는 off 로 둔다.
# off | on
LLM_VERIFICATION_NLI=off
# NLI 2차 호출의 총 예산. 재시도하지 않는다 — 게이트웨이 총예산(136.5s)에
# 이것이 더해져도 호출자 타임아웃(180s)을 넘지 않아야 한다.
LLM_VERIFICATION_NLI_TIMEOUT_SECONDS=30
```

`infra/docker-compose.yml` 의 `certificate-api` 블록에 두 변수를 추가한다.

- [ ] **Step 7: 기본이 off 인지 고정하는 테스트**

```python
def test_nli_is_off_by_default(monkeypatch):
    """기본으로 켜지면 모든 요청의 비용과 지연이 조용히 늘어난다."""
    monkeypatch.delenv("LLM_VERIFICATION_NLI", raising=False)
    import importlib
    import certificate_api
    importlib.reload(certificate_api)

    assert certificate_api.NLI_ENABLED is False
```

- [ ] **Step 8: 전체 확인**

Run: `cd services/prescription && python -m pytest -q`
Expected: 135 + 6 = 141 통과

- [ ] **Step 9: 뮤테이션 확인**

1. `except` 분기의 `"skipped"` 를 `"ok"` 로 → `test_llm_failure_is_skipped_not_ok` FAIL
2. 알 수 없는 판정을 `"ok"` 로 → `test_unknown_verdict_is_skipped` FAIL
3. 기본값 `"off"` 를 `"on"` 으로 → `test_nli_is_off_by_default` FAIL

- [ ] **Step 10: 커밋**

```bash
git add services/prescription/certificate_verification.py services/prescription/certificate_api.py services/prescription/tests/test_certificate_nli.py infra/.env.example infra/docker-compose.yml
git commit -m "feat(certificate): NLI 2차 판정을 기본 off 플래그로 추가"
```

---

### Task 12: 실측과 spec 갱신

spec §11 의 네 항목은 가정이다. 앞의 열한 태스크는 검증층을 만들었을 뿐,
그것이 실제로 무엇을 잡는지는 아직 아무도 모른다.

**전제:** 앞 두 항목은 LLM 키 없이 측정 가능하다(`LLM_PROVIDER=stub` + 실제 Arango).
뒤 두 항목은 유효한 `LLM_API_KEY` 가 필요하다.

**Files:**
- Create: `services/prescription/scripts/measure_verification.py`
- Modify: `Docs/superpowers/specs/2026-08-29-runtime-verification-design.md` (§11 결과 기록)

- [ ] **Step 1: 측정 스크립트 작성**

`services/prescription/scripts/measure_verification.py`:

```python
"""검증층이 실제로 무엇을 잡는지 센다.

앞 두 항목(flagged/skipped 비율)은 LLM 키 없이 stub 모드로 측정된다.
결과를 spec §11 에 기록한다. 키를 로그에 남기지 않는다.
"""
from __future__ import annotations

import collections
import json
import sys

import httpx

BASE = "http://localhost:8001"


def main(scenario_path: str) -> None:
    with open(scenario_path, encoding="utf-8") as handle:
        scenarios = [json.loads(line) for line in handle if line.strip()]

    status_counts: collections.Counter = collections.Counter()
    check_counts: collections.Counter = collections.Counter()

    with httpx.Client(timeout=180.0) as client:
        for scenario in scenarios:
            response = client.post(
                f"{BASE}/api/agent/prescription/recommend", json=scenario["request"])
            if response.status_code != 200:
                status_counts["http_error"] += 1
                continue
            verification = response.json().get("verification") or {}
            status_counts[verification.get("status", "missing")] += 1
            for check in verification.get("checks", []):
                check_counts[(check.get("id"), check.get("outcome"))] += 1

    print("verification.status 분포:")
    for key, count in status_counts.most_common():
        print(f"  {key}: {count}")
    print("검사별 결과:")
    for (check_id, outcome), count in sorted(check_counts.items()):
        print(f"  {check_id}/{outcome}: {count}")


if __name__ == "__main__":
    main(sys.argv[1])
```

- [ ] **Step 2: 시나리오로 측정**

Run:
```bash
cd services/prescription && python scripts/measure_verification.py evals/scenarios/<시나리오파일>
```

`evals/scenarios/` 의 실제 파일명을 먼저 확인한다.

- [ ] **Step 3: 결과를 판정한다**

- `code_in_candidates` 의 `flagged` 가 0% 면, 검사가 무의미하거나(모델이 절대
  지어내지 않음) 후보 집합이 너무 넓다는 뜻이다. 후보 집합 구성을 다시 본다.
- `skipped` 비율이 높으면 검증층이 이름만 있고 대부분 판정하지 못한다는 뜻이다.
  그 경우 조회 데이터를 더 확보하는 것이 검사를 늘리는 것보다 먼저다.

- [ ] **Step 4: spec §11 에 결과 기록**

측정한 숫자와 판정을 spec §11 의 해당 항목에 `- [x]` 로 바꿔 적는다.
숫자 없이 "확인함"이라고 적지 않는다.

- [ ] **Step 5: 커밋**

```bash
git add services/prescription/scripts/measure_verification.py Docs/superpowers/specs/2026-08-29-runtime-verification-design.md
git commit -m "test(verification): 검증층 실측과 spec 갱신"
```

**NLI 비용·지연 두 항목은 유효한 `LLM_API_KEY` 가 생긴 뒤에 측정한다.** 그때까지
spec §11 에 미확인으로 남긴다. 측정 없이 `LLM_VERIFICATION_NLI=on` 을 기본으로
돌리지 않는다.

---

## 완료 확인

```bash
cd services/prescription && python -m pytest -q
cd ../validation-agent && python -m pytest -q
cd ../llm-gateway && python -m pytest -q
```

기대: prescription 141 · validation-agent 44 · llm-gateway 48

```bash
cd apps/web && node .yarn/releases/yarn-4.12.0.cjs vitest run
cd apps/web && node .yarn/releases/yarn-4.12.0.cjs tsc --noEmit
```

기대: 166+ 통과, tsc 무출력

```bash
cd apps/api && ./gradlew test
```

기대: 실패는 사전 존재 3건뿐(`PatientServiceImplTest$Create` ×2, `WaitingServiceImplTest$RegisterWaitingTest` ×1)

```bash
grep -rn "reason_supported\|has_enough_top_rx" services/prescription/verification.py services/prescription/certificate_verification.py
```

기대: 출력 없음. §2.1·§2.2 의 결함을 이식하지 않았다는 확인이다.

수동 확인:
- `docker compose up -d` 후 처방 추천을 돌리면 추천 표에 항목 단위 검증 표시가 뜬다
- Arango 를 내린 상태로 추천하면 `verification.status` 가 `skipped` 이고 화면에 "미검증"이 뜬다(`passed` 가 아니다)
- `LLM_VERIFICATION_NLI` 를 지운 채 진단서를 생성하면 NLI 검사가 붙지 않는다
