from types import SimpleNamespace

from verification import verify_prescriptions, _row_code, _row_name, _row_dosage


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


# --- Critical: dosage_verbatim 방향 반전 -----------------------------------
# 리뷰어가 재현한 우회: 부분 문자열 포함 방향이 반대여서, 잘린 용량이
# "ok" 로 통과했다. 원본이 출력에 포함되어야 한다(출력이 원본을 담아야
# verbatim 이다) — 그 반대가 아니다.

def test_dosage_truncation_bypass_is_flagged():
    """리뷰어의 정확한 재현: source='1일 3회', output='1' 이면 flagged 여야 한다."""
    items = [_item(1, "A01", "약가", dosage="1")]
    result = verify_prescriptions(candidates=CANDIDATES, items=items)

    assert _outcomes(result, "dosage_verbatim")[0] == "flagged"


def test_dosage_superset_output_is_ok():
    """모델이 단어를 덧붙인 정당한 초과분은 통과해야 한다."""
    items = [_item(1, "A01", "약가", dosage="1일 3회 복용")]
    result = verify_prescriptions(candidates=CANDIDATES, items=items)

    assert _outcomes(result, "dosage_verbatim")[0] == "ok"


def test_dosage_exact_match_is_ok():
    items = [_item(1, "A01", "약가", dosage="1일 3회")]
    result = verify_prescriptions(candidates=CANDIDATES, items=items)

    assert _outcomes(result, "dosage_verbatim")[0] == "ok"


# --- Important: GC-8 커버리지 공백 4건 --------------------------------------

def test_dosage_korean_key_fallback():
    """후보 행에 'dosage' 없이 '용법' 만 있어도 대조할 수 있어야 한다."""
    candidates = [{"prescription_code": "A01", "prescription_name": "약가", "용법": "1일 3회"}]
    items = [_item(1, "A01", "약가", dosage="1일 3회")]
    result = verify_prescriptions(candidates=candidates, items=items)

    assert _outcomes(result, "dosage_verbatim") == ["ok"]


def test_row_helpers_reject_non_dict_rows():
    """세 _row_* 헬퍼 모두 dict 가 아닌 행에 대해 예외 없이 빈 문자열을 반환해야 한다."""
    assert _row_code("not-a-dict") == ""
    assert _row_name(123) == ""
    assert _row_dosage(None) == ""


def test_non_dict_candidate_row_does_not_crash_indexing():
    """후보 목록에 dict 가 아닌 행이 섞여도 대조가 정상적으로 진행되어야 한다."""
    candidates = CANDIDATES + ["not-a-dict-row", 12345, None]
    items = [_item(1, "A01", "약가"), _item(2, "B02", "약나", "1일 1회"),
             _item(3, "C03", "약다", "2정")]
    result = verify_prescriptions(candidates=candidates, items=items)

    assert result.status == "passed"


def test_empty_code_row_does_not_become_a_match_target():
    """빈 코드 후보 행은 색인에 들어가지 않아야 한다 — 출력의 빈 코드가
    엉뚱하게 '있음' 으로 매칭되면 안 된다."""
    candidates = [{"prescription_code": "", "prescription_name": "빈코드", "dosage": "1일 1회"}] + CANDIDATES
    items = [_item(1, "A01", "약가"), _item(2, "", "이름없음", "1일 1회"),
             _item(3, "C03", "약다", "2정")]
    result = verify_prescriptions(candidates=candidates, items=items)

    assert _outcomes(result, "code_in_candidates")[1] == "flagged"


def test_first_candidate_with_duplicate_code_wins():
    """같은 코드의 후보 행이 여러 개면 첫 번째가 이겨야 한다(setdefault 계약)."""
    candidates = [
        {"prescription_code": "A01", "prescription_name": "첫번째", "dosage": "1일 3회"},
        {"prescription_code": "A01", "prescription_name": "두번째", "dosage": "1일 1회"},
    ]
    items = [_item(1, "A01", "첫번째", dosage="1일 3회")]
    result = verify_prescriptions(candidates=candidates, items=items)

    assert _outcomes(result, "name_matches_code") == ["ok"]
    assert _outcomes(result, "dosage_verbatim") == ["ok"]


# --- Minor: 숫자 변환 방어 --------------------------------------------------

def test_non_numeric_confidence_is_flagged():
    items = [_item(1, "A01", "약가", confidence="high")]
    result = verify_prescriptions(candidates=CANDIDATES, items=items)

    assert _outcomes(result, "confidence_in_range")[0] == "flagged"


def test_non_numeric_rank_is_flagged_not_crashed():
    items = [_item("first", "A01", "약가"), _item(2, "B02", "약나", "1일 1회"),
             _item(3, "C03", "약다", "2정")]
    result = verify_prescriptions(candidates=CANDIDATES, items=items)

    assert _outcomes(result, "schema_top3") == ["flagged"]
