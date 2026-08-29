from types import SimpleNamespace

from verification import verify_prescriptions, _row_code, _row_name


def _item(rank, code, name, dosage="1일 3회"):
    return SimpleNamespace(
        rank=rank,
        name=name,
        prescription_code=code,
        dosage=dosage,
        reason="근거",
        # confidence_score 는 PrescriptionItem 모델에 남아 있지만 프롬프트가
        # 채우라고 요구하지 않는 필드다(confidence_in_range 검사 제거 사유).
        # 검증기가 더 이상 읽지 않으므로 고정값으로 존재만 시킨다.
        confidence_score=None,
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
    """진짜처럼 생겼지만 후보에 없는 코드 — 지어낸 값이므로 flagged 여야 한다.

    (a) 플레이스홀더 취급으로 잘못 완화되면(스킵) 이 테스트가 빨개진다:
    "Z99" 는 _PLACEHOLDER_VALUES 어디에도 없는, 후보에 없는 임의 코드다.
    """
    items = [_item(1, "A01", "약가"), _item(2, "B02", "약나", "1일 1회"),
             _item(3, "Z99", "지어낸약", "2정")]
    result = verify_prescriptions(candidates=CANDIDATES, items=items)

    assert result.status == "flagged"
    assert _outcomes(result, "code_in_candidates") == ["ok", "ok", "flagged"]


def test_name_mismatch_is_flagged():
    items = [_item(1, "A01", "다른이름"), _item(2, "B02", "약나", "1일 1회"),
             _item(3, "C03", "약다", "2정")]
    result = verify_prescriptions(candidates=CANDIDATES, items=items)

    assert "flagged" in _outcomes(result, "name_matches_code")


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


# I2(§12.6 GC-8 공백): 중복 처방코드 조건에는 죽이는 테스트가 없었다.
# `and len(set(codes)) == len(codes)` 를 지워도 스위트가 전부 초록이었다
# (실측: §11.5, 실제 모델 응답의 60%에서 이 조건이 발화한다). rank 는
# {1, 2, 3} 을 온전히 채워 rank 조건과는 독립적으로 중복 조건만 검증한다.
def test_duplicate_prescription_codes_is_flagged():
    items = [_item(1, "A01", "약가"), _item(2, "A01", "약가"),
             _item(3, "C03", "약다", "2정")]
    result = verify_prescriptions(candidates=CANDIDATES, items=items)

    assert _outcomes(result, "schema_top3") == ["flagged"]


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


# --- Important: GC-8 커버리지 공백 --------------------------------------

def test_row_helpers_reject_non_dict_rows():
    """_row_* 헬퍼는 dict 가 아닌 행에 대해 예외 없이 빈 문자열을 반환해야 한다."""
    assert _row_code("not-a-dict") == ""
    assert _row_name(123) == ""


def test_non_dict_candidate_row_does_not_crash_indexing():
    """후보 목록에 dict 가 아닌 행이 섞여도 대조가 정상적으로 진행되어야 한다."""
    candidates = CANDIDATES + ["not-a-dict-row", 12345, None]
    items = [_item(1, "A01", "약가"), _item(2, "B02", "약나", "1일 1회"),
             _item(3, "C03", "약다", "2정")]
    result = verify_prescriptions(candidates=candidates, items=items)

    assert result.status == "passed"


def test_empty_code_row_does_not_become_a_match_target():
    """빈 코드 후보 행은 색인에 들어가지 않아야 한다 — 출력의 빈 코드가
    엉뚱하게 '있음' 으로 매칭되면 안 된다.

    출력의 빈 코드 자체는 이제 플레이스홀더로 취급되어 flagged 가 아니라
    skipped 다("모델이 코드를 기재하지 않음") — 이는 근거 불일치가 아니라
    낼 근거가 없다는 정직한 신고다. 이 테스트가 지키는 것은 그것이 실수로
    '있음'(ok) 이 되지 않는다는 점: 빈 코드 후보 행이 색인에 들어가 있었다면
    빈 출력 코드가 그 행과 매칭되어 ok 가 나왔을 것이다.
    """
    candidates = [{"prescription_code": "", "prescription_name": "빈코드", "dosage": "1일 1회"}] + CANDIDATES
    items = [_item(1, "A01", "약가"), _item(2, "", "이름없음", "1일 1회"),
             _item(3, "C03", "약다", "2정")]
    result = verify_prescriptions(candidates=candidates, items=items)

    assert _outcomes(result, "code_in_candidates")[1] == "skipped"


# --- 플레이스홀더(모델이 근거 없음을 정직하게 신고) -----------------------
#
# 60 시나리오 실측: code_in_candidates 의 flagged 22건 전부가 리터럴 "미기재"
# 였다(prescription_agent.py 가 코드가 없을 때 지어내지 말고 쓰라고 지시하는
# 값). 지어낸 코드는 0건이었다. 정직한 거절을 근거 불일치(flagged)로 보고하면
# 안 되고, 대조할 근거가 없다는 뜻의 skipped 여야 한다.

def test_placeholder_code_mikija_is_skipped_not_flagged():
    items = [_item(1, "미기재", "약가"), _item(2, "B02", "약나", "1일 1회"),
             _item(3, "C03", "약다", "2정")]
    result = verify_prescriptions(candidates=CANDIDATES, items=items)

    assert _outcomes(result, "code_in_candidates")[0] == "skipped"


def test_placeholder_code_data_budget_is_skipped_not_flagged():
    items = [_item(1, "데이터 부족", "약가"), _item(2, "B02", "약나", "1일 1회"),
             _item(3, "C03", "약다", "2정")]
    result = verify_prescriptions(candidates=CANDIDATES, items=items)

    assert _outcomes(result, "code_in_candidates")[0] == "skipped"


def test_placeholder_code_no_dosage_data_is_skipped_not_flagged():
    items = [_item(1, "데이터에 용량 없음", "약가"), _item(2, "B02", "약나", "1일 1회"),
             _item(3, "C03", "약다", "2정")]
    result = verify_prescriptions(candidates=CANDIDATES, items=items)

    assert _outcomes(result, "code_in_candidates")[0] == "skipped"


def test_placeholder_code_skips_name_check_too():
    """코드가 플레이스홀더면 이름을 대조할 후보 자체가 정해지지 않으므로
    name_matches_code 도 skipped 여야 한다(flagged 로 새지 않는다)."""
    items = [_item(1, "미기재", "약가"), _item(2, "B02", "약나", "1일 1회"),
             _item(3, "C03", "약다", "2정")]
    result = verify_prescriptions(candidates=CANDIDATES, items=items)

    assert _outcomes(result, "name_matches_code")[0] == "skipped"


def test_placeholder_skip_evidence_says_model_declined_not_no_candidates():
    """skipped 사유가 둘 있다: (1) 조회된 후보가 아예 없음, (2) 후보는 있는데
    모델이 코드를 기재하지 않음. 이 둘을 같은 문구로 뭉개면 읽는 사람이
    구분할 수 없다."""
    items = [_item(1, "미기재", "약가"), _item(2, "B02", "약나", "1일 1회"),
             _item(3, "C03", "약다", "2정")]

    declined = verify_prescriptions(candidates=CANDIDATES, items=items)
    declined_check = [c for c in declined.checks if c.id == "code_in_candidates"][0]
    declined_evidence = declined_check.evidence

    no_candidates = verify_prescriptions(candidates=[], items=items)
    no_candidates_check = [c for c in no_candidates.checks if c.id == "code_in_candidates"][0]
    no_candidates_evidence = no_candidates_check.evidence

    assert declined_check.outcome == "skipped"
    assert no_candidates_check.outcome == "skipped"
    assert declined_evidence != no_candidates_evidence
    assert "후보가 없" not in declined_evidence
    assert "미기재" in declined_evidence or "플레이스홀더" in declined_evidence


def test_placeholder_name_with_matched_code_is_skipped_not_flagged():
    """코드는 실제 후보와 일치하는데 이름 필드만 플레이스홀더인 드문 경우.

    코드가 이미 매칭됐다고 해서 이름 비교를 곧장 문자열 동등 비교로 넘기면
    '모델이 이름을 기재하지 않음'이 '이름이 후보와 다름'(flagged)으로
    잘못 보고된다.
    """
    items = [_item(1, "A01", "미기재")]
    result = verify_prescriptions(candidates=CANDIDATES, items=items)

    assert _outcomes(result, "name_matches_code") == ["skipped"]


def test_first_candidate_with_duplicate_code_wins():
    """같은 코드의 후보 행이 여러 개면 첫 번째가 이겨야 한다(setdefault 계약)."""
    candidates = [
        {"prescription_code": "A01", "prescription_name": "첫번째"},
        {"prescription_code": "A01", "prescription_name": "두번째"},
    ]
    items = [_item(1, "A01", "첫번째")]
    result = verify_prescriptions(candidates=candidates, items=items)

    assert _outcomes(result, "name_matches_code") == ["ok"]


# --- Minor: 숫자 변환 방어 --------------------------------------------------

def test_non_numeric_rank_is_flagged_not_crashed():
    items = [_item("first", "A01", "약가"), _item(2, "B02", "약나", "1일 1회"),
             _item(3, "C03", "약다", "2정")]
    result = verify_prescriptions(candidates=CANDIDATES, items=items)

    assert _outcomes(result, "schema_top3") == ["flagged"]
