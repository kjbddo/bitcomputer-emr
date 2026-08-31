from types import SimpleNamespace

import certificate_api
from certificate_verification import verify_certificate


def _disease(code, name):
    return SimpleNamespace(code=code, name=name, degree=None)


DISEASES = [_disease("J00", "급성 비인두염"), _disease("E11.9", "제2형 당뇨병")]
DIAGNOSES = [SimpleNamespace(code="Z00", name="건강검진")]


def _outcomes(result, check_id):
    return [c.outcome for c in result.checks if c.id == check_id]


def test_known_code_and_term_pass():
    text = "환자는 급성 비인두염(J00)으로 통원 치료가 필요합니다."
    result = verify_certificate(diseases=DISEASES, diagnoses=DIAGNOSES, text=text)

    assert result.status == "passed"
    assert _outcomes(result, "cited_code_known") == ["ok"]
    assert _outcomes(result, "premise_term_present") == ["ok"]


def test_unknown_icd_code_is_flagged():
    text = "환자는 급성 비인두염(K52.9)으로 통원 치료가 필요합니다."
    result = verify_certificate(diseases=DISEASES, diagnoses=[], text=text)

    assert result.status == "flagged"
    assert "flagged" in _outcomes(result, "cited_code_known")


def test_no_code_in_text_is_skipped():
    text = "환자는 통원 치료가 필요합니다."
    result = verify_certificate(diseases=DISEASES, diagnoses=[], text=text)

    assert _outcomes(result, "cited_code_known") == ["skipped"]


def test_premise_term_absent_is_flagged():
    text = "환자는 안정이 필요합니다."
    result = verify_certificate(diseases=DISEASES, diagnoses=DIAGNOSES, text=text)

    assert "flagged" in _outcomes(result, "premise_term_present")


# GC-2. premise 가 비면 통과가 아니라 미확인이다.
def test_empty_premise_never_passes():
    text = "환자는 급성 비인두염으로 통원 치료가 필요합니다."
    result = verify_certificate(diseases=[], diagnoses=[], text=text)

    assert result.status == "skipped"
    assert result.skippedReason is not None


def test_dotted_icd_code_is_recognised():
    text = "제2형 당뇨병(E11.9) 소견입니다."
    result = verify_certificate(diseases=DISEASES, diagnoses=[], text=text)

    assert _outcomes(result, "cited_code_known") == ["ok"]


def test_diagnosis_name_counts_as_premise_term():
    """premise 는 diseases 와 diagnoses 를 합친 것이다. 어느 쪽 이름이든 인정한다."""
    text = "건강검진 목적의 소견입니다."
    result = verify_certificate(diseases=DISEASES, diagnoses=DIAGNOSES, text=text)

    assert _outcomes(result, "premise_term_present") == ["ok"]


def test_diagnosis_code_counts_as_known_code():
    text = "건강검진(Z00) 소견입니다."
    result = verify_certificate(diseases=DISEASES, diagnoses=DIAGNOSES, text=text)

    assert _outcomes(result, "cited_code_known") == ["ok"]


def test_response_model_has_verification_field():
    assert "verification" in certificate_api.CertificateGenerateResponse.model_fields


def test_certificate_verifier_exception_becomes_skipped(monkeypatch):
    def boom(**kwargs):
        raise RuntimeError("검증기 폭발")

    monkeypatch.setattr(certificate_api, "verify_certificate", boom)
    result = certificate_api._safe_verify_certificate(object(), "소견")

    assert result["status"] == "skipped"
    assert "RuntimeError" in (result["skippedReason"] or "")


# --- 리뷰어 반례: cited_code_known 이 반대 방향으로 둘 다 실패했다 ---
# 1) 괄호 없이 한글에 붙은 위조 코드는 인용으로 인식되지 않아 skipped 로
#    빠지고, 다른 premise 용어가 우연히 일치하면 전체가 passed 가 되어버렸다
#    (허위 통과). 2) `비타민 B12` 처럼 정상적인 의학 약어가 ICD-10 코드로
#    오인되어 flagged 되었다(허위 flag). 프로젝트 책임자의 결정: 괄호(또는
#    대괄호)로 감싼 코드만 인용으로 본다 — certificate_agent.py 가 실제로
#    `- [J00] 급성 비인두염` 형태로 코드를 제시하기 때문이다.

def test_vitamin_b12_not_flagged_as_code():
    """괄호 없는 `비타민 B12` 는 ICD-10 코드 인용이 아니다 — 이 검사 범위 밖."""
    text = "환자는 비타민 B12 결핍 소견으로 통원 치료가 필요합니다."
    result = verify_certificate(diseases=DISEASES, diagnoses=[], text=text)

    assert _outcomes(result, "cited_code_known") == ["skipped"]


def test_bracketed_unknown_code_is_flagged():
    text = "환자는 소화기 증상[K52.9]으로 통원 치료가 필요합니다."
    result = verify_certificate(diseases=DISEASES, diagnoses=[], text=text)

    assert result.status == "flagged"
    assert "flagged" in _outcomes(result, "cited_code_known")


def test_bracketed_known_code_is_ok():
    text = "환자는 급성 비인두염[J00]으로 통원 치료가 필요합니다."
    result = verify_certificate(diseases=DISEASES, diagnoses=[], text=text)

    assert _outcomes(result, "cited_code_known") == ["ok"]


def test_code_glued_to_korean_text_is_out_of_scope():
    """괄호 없이 한글에 바로 붙은 코드는 인용으로 보지 않는다. `\\b` 는 한글이
    Python 정규식에서 \\w 로 취급되어 한글-코드 경계에서 작동하지 않으므로,
    괄호 요구 없이는 이런 위조 코드를 영영 놓친다. 지금은 검사 범위 밖으로
    skipped 처리하고 "검증했다"고 암시하지 않는다(허위 통과 방지)."""
    text = "환자는 심근경색E21.9으로 통원 치료가 필요합니다."
    result = verify_certificate(diseases=DISEASES, diagnoses=[], text=text)

    assert _outcomes(result, "cited_code_known") == ["skipped"]


# --- GC-2 회귀: premise 가 있어도 code/name 이 전부 빈 문자열이면 안 된다 ---

def test_blank_code_and_name_premise_is_skipped_not_passed():
    """빈 문자열은 모든 문자열의 부분집합이다 — .discard("") 가 없으면
    diseases=[{code: "", name: ""}] 만으로도 아무 텍스트나 "통과"해버린다."""
    diseases = [SimpleNamespace(code="", name="", degree=None)]
    text = "환자는 급성 비인두염으로 통원 치료가 필요합니다."
    result = verify_certificate(diseases=diseases, diagnoses=[], text=text)

    assert result.status == "skipped"
    assert result.status != "passed"


def test_premise_with_only_name_counts_as_premise():
    """has_premise 는 code 나 name 중 하나만 있어도 참이어야 한다
    (`or` 여야 하며 `and` 로 바뀌면 안 된다)."""
    diseases = [SimpleNamespace(code="", name="급성 비인두염", degree=None)]
    text = "환자는 급성 비인두염으로 통원 치료가 필요합니다."
    result = verify_certificate(diseases=diseases, diagnoses=[], text=text)

    assert result.status == "passed"
    assert result.skippedReason is None


def test_premise_term_present_is_substring_containment_not_aboutness():
    """알려진 한계(spec §6.2, NLI 이전까지 해소되지 않음): 이 검사는 premise
    용어가 텍스트 안에 "등장"하는지만 본다. 소견이 그 상병에 "대한" 것인지는
    보장하지 않는다 — 짧은 premise 용어가 무관한 복합어의 부분 문자열로
    등장해도 ok 로 판정된다. 여기서는 "동" 이 무관한 "활동" 안에 등장한다."""
    diseases = [_disease("J00", "동")]
    text = "환자는 신체 활동에 큰 지장이 없습니다."
    result = verify_certificate(diseases=diseases, diagnoses=[], text=text)

    assert _outcomes(result, "premise_term_present") == ["ok"]


# 리뷰어가 잡은 회귀. 대문자만 받으면 소문자 인용이 findall 에서 조용히 빠져,
# 진짜 코드 하나만 걸린 채 "모두 premise 안에 있음" 이라는 적극적 거짓 진술이
# 나간다. 못 본 것을 못 봤다고 하는 것(skipped)보다 봤다고 하는 것이 나쁘다.
def test_mixed_case_citation_does_not_silently_drop_the_fabricated_one():
    text = "환자는 급성 비인두염[J00] 및 심근경색[e21.9] 의증입니다."
    result = verify_certificate(diseases=DISEASES, diagnoses=[], text=text)

    assert _outcomes(result, "cited_code_known") == ["flagged"]
    assert result.status == "flagged"


def test_lowercase_citation_of_premise_code_is_ok():
    """대소문자는 표기 차이다. [j00] 을 J00 과 다른 코드로 보면 오탐이 된다."""
    text = "환자는 급성 비인두염[j00] 소견입니다."
    result = verify_certificate(diseases=DISEASES, diagnoses=[], text=text)

    assert _outcomes(result, "cited_code_known") == ["ok"]


def test_whitespace_inside_brackets_is_still_a_citation():
    text = "환자는 급성 비인두염[ J00 ] 소견입니다."
    result = verify_certificate(diseases=DISEASES, diagnoses=[], text=text)

    assert _outcomes(result, "cited_code_known") == ["ok"]


def test_fullwidth_brackets_are_still_a_citation():
    """한글 입력기·LLM 출력에서 전각 괄호가 실제로 나온다."""
    text = "환자는 심근경색［K52.9］ 의증입니다."
    result = verify_certificate(diseases=DISEASES, diagnoses=[], text=text)

    assert _outcomes(result, "cited_code_known") == ["flagged"]
