"""medication_codes 의 분류 규칙 테스트.

여기 쓰인 코드·처방명은 지어낸 값이 아니라 라이브 ArangoDB
(bitcomputer_graph, order_lines 6,809행)에서 그대로 뽑은 실제 행이다.
분류가 데이터셋의 성질에 맞는지를 보는 테스트이므로 표본이 실재해야 한다.
"""
import pytest

from medication_codes import (
    MEDICATION_CODE_AQL_PREDICATE,
    MEDICATION_CODE_REGEX,
    is_medication_code,
)

# order_lines 에서 뽑은 실제 약제 행 (처방코드_norm, 처방명_norm).
REAL_MEDICATION_ROWS = [
    ("628900930", "가모드정(내복)"),
    ("653700240", "마그밀정(수산화마그네슘)_(0.5g/1정)"),
    ("642202450", "훼로바-유서방정"),
    ("642201340", "씬지로이드정0.1mg"),
    ("628900390", "라베라정10mg"),
    # 접두 '6' 이 아닌 약제. "6 으로 시작하면 약" 규칙은 이 행들을 놓친다.
    ("073000850", "리플록신정500mg(내복)"),
    ("074200080", "둘코락스좌약(비사코딜)_(10mg/1개)"),
    ("051600131", "라미실크림1%(외용)"),
    ("052400511", "메게이트현탁액(메게스트롤아세테이트)(B)"),
]

# order_lines 에서 뽑은 실제 비약제 행. 수가(진찰료·방문료), 검사 결과 성분,
# 처치·재료가 섞여 있다.
REAL_NON_MEDICATION_ROWS = [
    ("2CHOK20", "촉탁진료20%재진(건강보험)"),
    ("2CHOK8", "촉탁진료8%재진(건강보험 )"),
    ("MCH", "MCH"),
    ("MCHC", "MCHC"),
    ("EOS", "eos"),
    ("LYM", "Lym"),
    ("BAS", "Bas"),
    ("E6541", "심전도검사-심전도기록및판독[표준12유도]"),
    ("M0060", "유치 카테터 설치"),
    ("G2101", "흉부[직접]1매"),
]

# F-H1 의 라이브 관측(J18 폐렴)에서 실제로 화면까지 간 세 코드.
LIVE_FEE_CODES = ["AL801", "AA254", "KK052", "AA254090"]


@pytest.mark.parametrize("code,name", REAL_MEDICATION_ROWS)
def test_real_medication_rows_are_medication(code, name):
    assert is_medication_code(code) is True, name


@pytest.mark.parametrize("code,name", REAL_NON_MEDICATION_ROWS)
def test_real_non_medication_rows_are_not_medication(code, name):
    assert is_medication_code(code) is False, name


@pytest.mark.parametrize("code", LIVE_FEE_CODES)
def test_live_observed_fee_codes_are_not_medication(code):
    """F-H1 이 라이브에서 관측한 수가 코드들 — 이것이 통과하면 안 된다."""
    assert is_medication_code(code) is False


def test_placeholder_and_empty_are_not_medication():
    for value in ("", "   ", "미기재", "데이터 부족", None):
        assert is_medication_code(value) is False


def test_non_string_input_does_not_crash():
    # GC-4: 예외 대신 판정으로. 숫자 642202450 은 문자열로 굳혀 판정한다.
    assert is_medication_code(642202450) is True
    assert is_medication_code(["642202450"]) is False


def test_surrounding_whitespace_is_trimmed():
    assert is_medication_code("  642202450  ") is True


def test_length_boundaries():
    assert is_medication_code("64220245") is False   # 8자리
    assert is_medication_code("6422024501") is False  # 10자리
    assert is_medication_code("642202450") is True    # 9자리


def test_nine_characters_with_a_letter_is_not_medication():
    """길이만 맞고 숫자가 아니면 약제 코드가 아니다.

    W32950011 은 order_lines 에 실재하는 9자 코드지만 숫자가 아니다.
    (라에넥주사액 — 문서화된 위음성 3행 중 하나)
    """
    assert is_medication_code("W32950011") is False


def test_aql_predicate_and_python_share_one_regex():
    """AQL 필터와 파이썬 판정이 서로 다른 규칙으로 갈라지면,
    조회에서 걸러진 것과 검사가 잡는 것이 어긋난다."""
    assert "@med_code_re" in MEDICATION_CODE_AQL_PREDICATE
    assert MEDICATION_CODE_REGEX == r"^[0-9]{9}$"
