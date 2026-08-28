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


# 대칭 케이스: 원본에는 용량이 있지만 출력에 용량이 비어 있으면 마찬가지로
# 대조할 수 없다 — flagged(가짜 불일치)도 ok(근거 없는 통과)도 아니다.
def test_dosage_skipped_when_output_has_none():
    items = [_item(1, "A01", "약가", dosage="")]
    result = verify_prescriptions(candidates=CANDIDATES, items=items)

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


def test_dosage_reformat_superset_is_now_flagged():
    """예전에는 이 케이스(모델이 '복용'을 덧붙인 정당한 재서식)를 통과시켰다.
    하지만 포함 관계로는 이런 정당한 부가어와 '1일 3회 대신 1일 1회' 같은
    치환 문구를 구별할 수 없다 — 둘 다 원본 문자열을 통째로 담고 있다.
    프로젝트 오너의 결정: 검사 이름(verbatim)을 실제로 지키려면 공백 정규화
    후 완전 일치만 인정해야 한다. 모델이 용량 문구를 얼마나 자주/어떻게
    정당하게 재서식하는지는 아직 측정된 바 없으므로, 느슨하게 시작해
    우회를 허용하기보다 엄격하게 시작해 데이터로 완화하는 쪽을 택했다.
    그 결과 이 정당한 재서식도 지금은 flagged 된다 — 의도한 트레이드오프다."""
    items = [_item(1, "A01", "약가", dosage="1일 3회 복용")]
    result = verify_prescriptions(candidates=CANDIDATES, items=items)

    assert _outcomes(result, "dosage_verbatim")[0] == "flagged"


def test_dosage_exact_match_is_ok():
    items = [_item(1, "A01", "약가", dosage="1일 3회")]
    result = verify_prescriptions(candidates=CANDIDATES, items=items)

    assert _outcomes(result, "dosage_verbatim")[0] == "ok"


def test_dosage_substitution_phrase_is_flagged():
    """리뷰 라운드 2 재현: '1일 3회 대신 1일 1회' 는 원본 문구를 통째로
    담고 있지만 의미는 정반대(대체 지시)다. 원본이 출력에 포함되는 방향의
    포함 관계 검사는 이걸 그대로 통과시켰다."""
    items = [_item(1, "A01", "약가", dosage="1일 3회 대신 1일 1회")]
    result = verify_prescriptions(candidates=CANDIDATES, items=items)

    assert _outcomes(result, "dosage_verbatim")[0] == "flagged"


def test_dosage_negation_is_flagged():
    """'1일 3회 아님' — 원본을 부정하는 문구도 포함 관계로는 통과했다."""
    items = [_item(1, "A01", "약가", dosage="1일 3회 아님")]
    result = verify_prescriptions(candidates=CANDIDATES, items=items)

    assert _outcomes(result, "dosage_verbatim")[0] == "flagged"


def test_dosage_prohibition_is_flagged():
    """'1일 3회 금지' — 원본을 금지하는 문구도 포함 관계로는 통과했다."""
    items = [_item(1, "A01", "약가", dosage="1일 3회 금지")]
    result = verify_prescriptions(candidates=CANDIDATES, items=items)

    assert _outcomes(result, "dosage_verbatim")[0] == "flagged"


def test_dosage_internal_whitespace_run_is_ok():
    """공백 정규화: 공백이 두 칸 이상이어도 한 칸으로 뭉쳐 비교해야 한다."""
    candidates = [{"prescription_code": "A01", "prescription_name": "약가", "dosage": "1일  3회"}]
    items = [_item(1, "A01", "약가", dosage="1일 3회")]
    result = verify_prescriptions(candidates=candidates, items=items)

    assert _outcomes(result, "dosage_verbatim") == ["ok"]


def test_dosage_leading_trailing_whitespace_is_ok():
    """공백 정규화: 양쪽 끝 공백은 원본 쪽이든 출력 쪽이든 무시돼야 한다."""
    candidates = [{"prescription_code": "A01", "prescription_name": "약가", "dosage": "  1일 3회  "}]
    items = [_item(1, "A01", "약가", dosage="1일 3회")]
    result = verify_prescriptions(candidates=candidates, items=items)

    assert _outcomes(result, "dosage_verbatim") == ["ok"]

    items2 = [_item(1, "A01", "약가", dosage="  1일 3회  ")]
    result2 = verify_prescriptions(candidates=CANDIDATES, items=items2)

    assert _outcomes(result2, "dosage_verbatim") == ["ok"]


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


# NFC(완성형)와 NFD(자모 분해형)는 화면상 같은 한글인데 코드포인트가 다르다.
# Arango 적재 경로나 입력기에 따라 어느 쪽으로도 들어올 수 있다. 정규화가
# 없으면 글자 그대로 같은 용량이 flagged 로 뜬다 — 없는 불일치를 만들어내는
# 오탐이고, 그런 표시가 쌓이면 의사가 표시 자체를 무시하게 된다.
def test_dosage_nfd_source_matches_nfc_output():
    import unicodedata

    nfc = "1일 3회"
    nfd = unicodedata.normalize("NFD", nfc)
    assert nfc != nfd, "테스트 전제: 두 형태의 코드포인트가 실제로 달라야 한다"

    candidates = [{"prescription_code": "A01", "prescription_name": "약가", "dosage": nfd}]
    items = [_item(1, "A01", "약가", dosage=nfc)]
    result = verify_prescriptions(candidates=candidates, items=items)

    assert _outcomes(result, "dosage_verbatim") == ["ok"]


def test_dosage_nfc_source_matches_nfd_output():
    import unicodedata

    nfc = "1일 3회"
    nfd = unicodedata.normalize("NFD", nfc)

    candidates = [{"prescription_code": "A01", "prescription_name": "약가", "dosage": nfc}]
    items = [_item(1, "A01", "약가", dosage=nfd)]
    result = verify_prescriptions(candidates=candidates, items=items)

    assert _outcomes(result, "dosage_verbatim") == ["ok"]
