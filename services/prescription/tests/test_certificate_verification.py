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
