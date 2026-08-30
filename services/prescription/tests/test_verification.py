from types import SimpleNamespace

from verification import verify_prescriptions, _row_code, _row_name


def _item(rank, code, name, dosage="1일 3회", confidence=0.8):
    return SimpleNamespace(
        rank=rank,
        name=name,
        prescription_code=code,
        dosage=dosage,
        reason="근거",
        # confidence_score 는 LLM 이 채우는 값이 아니라 prescription_api.py 가
        # Arango co-occurrence 결과(confidence_by_code)로 주입하는 값이다
        # (:473-489 계산, :710-719 주입, :736 의 _safe_verify 보다 먼저 실행).
        # 그래프가 비어 있으면 주입이 없어 None 으로 남는다 — 그때는 검사가
        # skipped 다(GC-2).
        confidence_score=confidence,
    )


def _outcomes(result, check_id):
    return [c.outcome for c in result.checks if c.id == check_id]


CANDIDATES = [
    {"prescription_code": "642202450", "prescription_name": "약가", "dosage": "1일 3회"},
    {"처방코드": "653700240", "처방명": "약나", "dosage": "1일 1회"},
    {"prescription_code": "628900930", "prescription_name": "약다", "dosage": "2정"},
]


def test_all_codes_in_candidates_pass():
    items = [_item(1, "642202450", "약가"), _item(2, "653700240", "약나", "1일 1회"),
             _item(3, "628900930", "약다", "2정")]
    result = verify_prescriptions(candidates=CANDIDATES, items=items)

    assert result.status == "passed"
    assert _outcomes(result, "code_in_candidates") == ["ok", "ok", "ok"]


def test_invented_code_is_flagged():
    """진짜처럼 생겼지만 후보에 없는 코드 — 지어낸 값이므로 flagged 여야 한다.

    (a) 플레이스홀더 취급으로 잘못 완화되면(스킵) 이 테스트가 빨개진다:
    "999999999" 는 _PLACEHOLDER_VALUES 어디에도 없는, 후보에 없는 임의 코드다.
    """
    items = [_item(1, "642202450", "약가"), _item(2, "653700240", "약나", "1일 1회"),
             _item(3, "999999999", "지어낸약", "2정")]
    result = verify_prescriptions(candidates=CANDIDATES, items=items)

    assert result.status == "flagged"
    assert _outcomes(result, "code_in_candidates") == ["ok", "ok", "flagged"]


def test_name_mismatch_is_flagged():
    items = [_item(1, "642202450", "다른이름"), _item(2, "653700240", "약나", "1일 1회"),
             _item(3, "628900930", "약다", "2정")]
    result = verify_prescriptions(candidates=CANDIDATES, items=items)

    assert "flagged" in _outcomes(result, "name_matches_code")


# GC-2. 후보가 비면 통과가 아니라 미확인이다.
def test_empty_candidates_never_passes():
    items = [_item(1, "642202450", "약가"), _item(2, "653700240", "약나"), _item(3, "628900930", "약다")]
    result = verify_prescriptions(candidates=[], items=items)

    assert result.status == "skipped"
    assert result.skippedReason is not None
    assert _outcomes(result, "code_in_candidates") == ["skipped", "skipped", "skipped"]


def test_wrong_rank_set_is_flagged():
    items = [_item(1, "642202450", "약가"), _item(1, "653700240", "약나", "1일 1회"),
             _item(3, "628900930", "약다", "2정")]
    result = verify_prescriptions(candidates=CANDIDATES, items=items)

    assert _outcomes(result, "schema_top3") == ["flagged"]


# I2(§12.6 GC-8 공백): 중복 처방코드 조건에는 죽이는 테스트가 없었다.
# `and len(set(codes)) == len(codes)` 를 지워도 스위트가 전부 초록이었다
# (실측: §11.5, 실제 모델 응답의 60%에서 이 조건이 발화한다). rank 는
# {1, 2, 3} 을 온전히 채워 rank 조건과는 독립적으로 중복 조건만 검증한다.
def test_duplicate_prescription_codes_is_flagged():
    items = [_item(1, "642202450", "약가"), _item(2, "642202450", "약가"),
             _item(3, "628900930", "약다", "2정")]
    result = verify_prescriptions(candidates=CANDIDATES, items=items)

    assert _outcomes(result, "schema_top3") == ["flagged"]


# I1: schema_top3 는 code_in_candidates/name_matches_code 와 달리 플레이스홀더
# 면제가 없어서, 프롬프트 지시대로 "미기재"를 두 번 정직하게 쓴 출력을
# "코드중복"으로 flag 했다. 지어내지 말라는 지시를 따른 것을 근거 불일치로
# 보고하면 안 된다 — §11.3 이 code_in_candidates 에서 고친 바로 그 오탐이다.
def test_duplicate_placeholder_codes_not_flagged_as_duplicate():
    items = [_item(1, "미기재", "이름1"), _item(2, "미기재", "이름2"),
             _item(3, "628900930", "약다", "2정")]
    result = verify_prescriptions(candidates=CANDIDATES, items=items)

    assert _outcomes(result, "schema_top3") == ["ok"]


# 플레이스홀더 면제가 실제 코드 중복까지 가려서는 안 된다 — 진짜 중복은
# 여전히 걸려야 한다(위 test_duplicate_prescription_codes_is_flagged 가
# 순수 중복을, 이 테스트는 플레이스홀더와 섞여도 살아남는지를 본다).
def test_duplicate_real_code_still_flagged_when_mixed_with_placeholder():
    items = [_item(1, "642202450", "약가"), _item(2, "642202450", "약가"),
             _item(3, "미기재", "이름3")]
    result = verify_prescriptions(candidates=CANDIDATES, items=items)

    assert _outcomes(result, "schema_top3") == ["flagged"]


# GC-3. 검증기는 판정만 한다.
def test_does_not_mutate_output():
    items = [_item(1, "642202450", "약가")]
    before = [(i.rank, i.name, i.prescription_code, i.dosage, i.confidence_score) for i in items]
    verify_prescriptions(candidates=CANDIDATES, items=items)
    after = [(i.rank, i.name, i.prescription_code, i.dosage, i.confidence_score) for i in items]

    assert before == after


# reason 은 A 에서 검증하지 않는다(spec §6.1). 검사가 생기면 이 테스트가 알려준다.
def test_no_reason_check_in_phase_a():
    items = [_item(1, "642202450", "약가")]
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
    items = [_item(1, "642202450", "약가"), _item(2, "653700240", "약나", "1일 1회"),
             _item(3, "628900930", "약다", "2정")]
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
    items = [_item(1, "642202450", "약가"), _item(2, "", "이름없음", "1일 1회"),
             _item(3, "628900930", "약다", "2정")]
    result = verify_prescriptions(candidates=candidates, items=items)

    assert _outcomes(result, "code_in_candidates")[1] == "skipped"


# --- 플레이스홀더(모델이 근거 없음을 정직하게 신고) -----------------------
#
# 60 시나리오 실측: code_in_candidates 의 flagged 22건 전부가 리터럴 "미기재"
# 였다(prescription_agent.py 가 코드가 없을 때 지어내지 말고 쓰라고 지시하는
# 값). 지어낸 코드는 0건이었다. 정직한 거절을 근거 불일치(flagged)로 보고하면
# 안 되고, 대조할 근거가 없다는 뜻의 skipped 여야 한다.

def test_placeholder_code_mikija_is_skipped_not_flagged():
    items = [_item(1, "미기재", "약가"), _item(2, "653700240", "약나", "1일 1회"),
             _item(3, "628900930", "약다", "2정")]
    result = verify_prescriptions(candidates=CANDIDATES, items=items)

    assert _outcomes(result, "code_in_candidates")[0] == "skipped"


def test_placeholder_code_data_budget_is_skipped_not_flagged():
    items = [_item(1, "데이터 부족", "약가"), _item(2, "653700240", "약나", "1일 1회"),
             _item(3, "628900930", "약다", "2정")]
    result = verify_prescriptions(candidates=CANDIDATES, items=items)

    assert _outcomes(result, "code_in_candidates")[0] == "skipped"


def test_placeholder_code_no_dosage_data_is_skipped_not_flagged():
    items = [_item(1, "데이터에 용량 없음", "약가"), _item(2, "653700240", "약나", "1일 1회"),
             _item(3, "628900930", "약다", "2정")]
    result = verify_prescriptions(candidates=CANDIDATES, items=items)

    assert _outcomes(result, "code_in_candidates")[0] == "skipped"


def test_placeholder_code_skips_name_check_too():
    """코드가 플레이스홀더면 이름을 대조할 후보 자체가 정해지지 않으므로
    name_matches_code 도 skipped 여야 한다(flagged 로 새지 않는다)."""
    items = [_item(1, "미기재", "약가"), _item(2, "653700240", "약나", "1일 1회"),
             _item(3, "628900930", "약다", "2정")]
    result = verify_prescriptions(candidates=CANDIDATES, items=items)

    assert _outcomes(result, "name_matches_code")[0] == "skipped"


def test_placeholder_skip_evidence_says_model_declined_not_no_candidates():
    """skipped 사유가 둘 있다: (1) 조회된 후보가 아예 없음, (2) 후보는 있는데
    모델이 코드를 기재하지 않음. 이 둘을 같은 문구로 뭉개면 읽는 사람이
    구분할 수 없다."""
    items = [_item(1, "미기재", "약가"), _item(2, "653700240", "약나", "1일 1회"),
             _item(3, "628900930", "약다", "2정")]

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
    items = [_item(1, "642202450", "미기재")]
    result = verify_prescriptions(candidates=CANDIDATES, items=items)

    assert _outcomes(result, "name_matches_code") == ["skipped"]


def test_first_candidate_with_duplicate_code_wins():
    """같은 코드의 후보 행이 여러 개면 첫 번째가 이겨야 한다(setdefault 계약)."""
    candidates = [
        {"prescription_code": "642202450", "prescription_name": "첫번째"},
        {"prescription_code": "642202450", "prescription_name": "두번째"},
    ]
    items = [_item(1, "642202450", "첫번째")]
    result = verify_prescriptions(candidates=candidates, items=items)

    assert _outcomes(result, "name_matches_code") == ["ok"]


# --- confidence_in_range ----------------------------------------------------
#
# 이 검사는 커밋 9289321 에서 "프롬프트가 confidence_score 를 요구하지 않아 값이
# 구조적으로 항상 None" 이라는 이유로 제거됐다. 그 이유는 사실이 아니었다 —
# 값을 채우는 것은 LLM 이 아니라 prescription_api.py 의 Arango co-occurrence
# 주입(:473-489 계산, :710-719 주입)이고, 그 주입은 _safe_verify(:736)보다 먼저
# 실행된다. 180건 전부 skipped 였던 실측은 ArangoDB 가 완전히 비어 있고
# 시나리오의 유일한 상병코드(M2556)가 그래프에 없던 환경에서 돌았기 때문이다.
# 그래프를 적재하고 그래프에 있는 상병코드로 다시 부르면 값이 실제로 채워진다.

def test_confidence_in_range_is_ok():
    items = [_item(1, "642202450", "약가", confidence=0.149)]
    result = verify_prescriptions(candidates=CANDIDATES, items=items)

    assert _outcomes(result, "confidence_in_range") == ["ok"]


def test_confidence_out_of_range_is_flagged():
    items = [_item(1, "642202450", "약가", confidence=1.7), _item(2, "653700240", "약나", "1일 1회"),
             _item(3, "628900930", "약다", "2정")]
    result = verify_prescriptions(candidates=CANDIDATES, items=items)

    assert "flagged" in _outcomes(result, "confidence_in_range")


def test_missing_confidence_is_skipped_not_ok():
    """주입이 일어나지 않은(그래프가 비었거나 코드가 그래프에 없는) 경우.

    없는 값을 "범위 안"으로 읽으면 GC-2 위반이다 — 대조할 것이 없으면 skipped.
    """
    items = [_item(1, "642202450", "약가", confidence=None)]
    result = verify_prescriptions(candidates=CANDIDATES, items=items)

    assert _outcomes(result, "confidence_in_range") == ["skipped"]


def test_confidence_boundaries_are_in_range():
    """0.0 과 1.0 은 범위 안이다. confidence_by_code.get(code, 0.0) 폴백이
    코드가 co-occurrence 결과에 없을 때 정확히 0.0 을 넣는다."""
    items = [_item(1, "642202450", "약가", confidence=0.0), _item(2, "653700240", "약나", "1일 1회", confidence=1.0)]
    result = verify_prescriptions(candidates=CANDIDATES, items=items)

    assert _outcomes(result, "confidence_in_range") == ["ok", "ok"]


# (b) 변이 표: confidence_in_range 를 STRUCTURAL_CHECK_IDS 에서 빼면 빨개진다.
# 이 검사는 0..1 범위만 본다 — 조회된 어떤 데이터와도 대조하지 않는다. 근거
# 검사로 집계되면 Arango 조회가 전부 실패해 code/name 이 모두 skipped 인
# 응답도 "검증됨(passed)" 으로 나간다. GC-2 가 금지하는 바로 그 신호다.
def test_confidence_ok_alone_never_passes():
    # schema_top3 도 통과하도록 rank 를 {1,2,3} 으로 맞춘다 — 그래야 "구조
    # 검사는 전부 ok 인데 근거 검사는 전부 skipped" 라는 정확한 상황이 된다.
    items = [_item(1, "642202450", "약가", confidence=0.5),
             _item(2, "653700240", "약나", "1일 1회", confidence=0.5),
             _item(3, "628900930", "약다", "2정", confidence=0.5)]
    result = verify_prescriptions(candidates=[], items=items)

    assert _outcomes(result, "confidence_in_range") == ["ok", "ok", "ok"]
    assert _outcomes(result, "code_in_candidates") == ["skipped", "skipped", "skipped"]
    assert _outcomes(result, "schema_top3") == ["ok"]
    assert result.status == "skipped"


# --- Minor: 숫자 변환 방어 --------------------------------------------------

def test_non_numeric_confidence_is_flagged():
    """숫자로 변환되지 않는 값은 "판정 불가(skipped)" 가 아니라 "출력 형식이
    잘못됨(flagged)" 이다 — 범위를 벗어난 숫자와 같은 취급(GC-4)."""
    items = [_item(1, "642202450", "약가", confidence="high")]
    result = verify_prescriptions(candidates=CANDIDATES, items=items)

    assert _outcomes(result, "confidence_in_range")[0] == "flagged"


def test_non_numeric_rank_is_flagged_not_crashed():
    items = [_item("first", "642202450", "약가"), _item(2, "653700240", "약나", "1일 1회"),
             _item(3, "628900930", "약다", "2정")]
    result = verify_prescriptions(candidates=CANDIDATES, items=items)

    assert _outcomes(result, "schema_top3") == ["flagged"]


# --- code_is_medication (F-H1) ---
#
# 이 코드들은 라이브에서 실제로 화면까지 간 값이다: J18(폐렴) 요청에
# validation-agent 가 돌려준 candidatePrescriptions 세 건이 AL801(의약품
# 관리료)·AA254(재진진찰료)·KK052(정맥내점적주사)였고, 셋 다 조회된 후보에서
# 왔으므로 code_in_candidates 는 정직하게 ok 를 냈고 응답은 passed 였다.
# 그 응답에 약은 한 건도 없었다.

MED_CANDIDATES = [
    {"prescription_code": "642202450", "prescription_name": "훼로바-유서방정"},
    {"처방코드": "653700240", "처방명": "마그밀정"},
    {"prescription_code": "628900930", "prescription_name": "가모드정(내복)"},
]

FEE_CANDIDATES = [
    {"prescription_code": "AL801", "prescription_name": "외래환자 의약품관리료-1일분"},
    {"prescription_code": "AA254", "prescription_name": "재진진찰료-의원 내 의과"},
    {"prescription_code": "KK052", "prescription_name": "정맥내점적주사-100ml~500ml"},
]


def test_medication_codes_are_ok():
    items = [_item(1, "642202450", "훼로바-유서방정"),
             _item(2, "653700240", "마그밀정"),
             _item(3, "628900930", "가모드정(내복)")]
    result = verify_prescriptions(candidates=MED_CANDIDATES, items=items)

    assert _outcomes(result, "code_is_medication") == ["ok", "ok", "ok"]
    assert result.status == "passed"


def test_fee_codes_are_flagged_even_though_they_are_in_candidates():
    """F-H1 라이브 관측의 회귀 테스트.

    세 코드 전부 조회된 후보에 실재하므로 code_in_candidates 는 ok 다 —
    이 검사가 없으면 응답은 passed 로 나가고 화면에는 폐렴 환자에게
    "재진진찰료" 가 처방으로 뜬다.
    """
    items = [_item(1, "AL801", "외래환자 의약품관리료-1일분"),
             _item(2, "AA254", "재진진찰료-의원 내 의과"),
             _item(3, "KK052", "정맥내점적주사-100ml~500ml")]
    result = verify_prescriptions(candidates=FEE_CANDIDATES, items=items)

    assert _outcomes(result, "code_in_candidates") == ["ok", "ok", "ok"]
    assert _outcomes(result, "code_is_medication") == ["flagged", "flagged", "flagged"]
    assert result.status == "flagged"


def test_single_fee_code_among_medications_is_flagged():
    """항목 단위 판정이다 — 셋 중 하나만 수가여도 그 항목이 flagged 다."""
    candidates = MED_CANDIDATES + [
        {"prescription_code": "AA254", "prescription_name": "재진진찰료-의원 내 의과"}]
    items = [_item(1, "642202450", "훼로바-유서방정"),
             _item(2, "AA254", "재진진찰료-의원 내 의과"),
             _item(3, "628900930", "가모드정(내복)")]
    result = verify_prescriptions(candidates=candidates, items=items)

    assert _outcomes(result, "code_is_medication") == ["ok", "flagged", "ok"]
    assert result.status == "flagged"


def test_placeholder_code_skips_medication_check():
    """모델이 코드를 기재하지 않은 것은 "약이 아니다" 가 아니라 판정 불가다.

    §11.3·I1 이 code_in_candidates·schema_top3 에서 두 번 걷어낸 오탐이
    새 검사로 되돌아오는 것을 막는다.
    """
    items = [_item(1, "642202450", "훼로바-유서방정"),
             _item(2, "미기재", "미기재"),
             _item(3, "", "")]
    result = verify_prescriptions(candidates=MED_CANDIDATES, items=items)

    assert _outcomes(result, "code_is_medication") == ["ok", "skipped", "skipped"]


def test_code_is_medication_ok_alone_never_passes():
    """구조 검사다 — 조회 데이터와 대조하지 않는다(GC-2).

    후보가 하나도 없어 code_in_candidates·name_matches_code 가 전부
    skipped 인 응답이, 코드가 약제 코드처럼 생겼다는 이유만으로
    "검증됨" 으로 나가면 안 된다.
    """
    items = [_item(1, "642202450", "훼로바-유서방정", confidence=None),
             _item(2, "653700240", "마그밀정", confidence=None),
             _item(3, "628900930", "가모드정(내복)", confidence=None)]
    result = verify_prescriptions(candidates=[], items=items)

    assert _outcomes(result, "code_is_medication") == ["ok", "ok", "ok"]
    assert result.status == "skipped"


def test_code_is_medication_fires_without_any_candidates():
    """후보가 비어도 발화한다 — 조회 데이터가 필요 없는 검사이기 때문이다.

    시나리오가 top_rx 를 직접 주는 경로(Arango 미조회)에서도 같은 이유로
    발화한다: 후보 필터가 닿지 않는 유일한 경로다.
    """
    items = [_item(1, "AA254", "재진진찰료"), _item(2, "AL801", "의약품관리료"),
             _item(3, "KK052", "정맥내점적주사")]
    result = verify_prescriptions(candidates=[], items=items)

    assert _outcomes(result, "code_is_medication") == ["flagged"] * 3
    assert result.status == "flagged"


def test_code_is_medication_evidence_names_the_code():
    items = [_item(1, "AA254", "재진진찰료"), _item(2, "653700240", "마그밀정"),
             _item(3, "628900930", "가모드정")]
    result = verify_prescriptions(candidates=MED_CANDIDATES, items=items)
    evidence = [c.evidence for c in result.checks if c.id == "code_is_medication"]

    assert "AA254" in evidence[0]
