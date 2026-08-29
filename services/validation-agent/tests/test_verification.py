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


# 사전점검에서 찾은 구멍. 트레이스만 멀쩡하고 조회 데이터가 하나도 없으면
# 대조한 것이 아무것도 없다. 그때 passed 가 나오면 §5.1 이 막으려던 실패다.
def test_trace_only_never_passes():
    response = {
        "pubmedEvidenceSummary": "", "checks": [], "candidatePrescriptions": [],
        "reasoningTrace": [{"action": "A", "observation": {"status": "OK"}}],
    }
    result = verify_validation(
        pubmed_articles=[], finder_candidates=[], response_dict=response)

    assert _outcomes(result, "trace_step_has_observation") == ["ok"]
    assert result.status == "skipped"
    # status 가 skipped 인 케이스인데 skippedReason 이 비어 있으면 화면에는
    # "미확인"만 뜨고 이유가 안 나온다. 리뷰 Important 3.
    assert result.skippedReason == "도구 관측값이 없어 대조를 수행하지 못했습니다."


# --- 리뷰 Important 1 & 2: PMID 정규식이 두 방향으로 틀렸던 문제 ---

# 오탐: PMID 마커 없는 7~8자리 숫자(용량, 날짜)를 인용으로 잘못 뽑던 문제.
def test_dosage_number_without_marker_is_not_cited():
    response = {"pubmedEvidenceSummary": "용량 1234567 mg 투여", "checks": [],
                "candidatePrescriptions": [], "reasoningTrace": []}
    result = verify_validation(
        pubmed_articles=ARTICLES, finder_candidates=[], response_dict=response)

    assert _outcomes(result, "cited_pmid_in_evidence") == ["skipped"]


def test_date_number_without_marker_is_not_cited():
    response = {"pubmedEvidenceSummary": "방문일 20260829", "checks": [],
                "candidatePrescriptions": [], "reasoningTrace": []}
    result = verify_validation(
        pubmed_articles=ARTICLES, finder_candidates=[], response_dict=response)

    assert _outcomes(result, "cited_pmid_in_evidence") == ["skipped"]


# 누락: 공백 없이 조사가 붙으면(`11111111을`) \b 가 숫자-한글 경계에서
# 작동하지 않아 정상 인용도, 위조 인용도 똑같이 "skipped"로 숨어버리던 문제.
def test_pmid_with_attached_particle_is_extracted():
    response = {"pubmedEvidenceSummary": "PMID 11111111을 보면 됨", "checks": [],
                "candidatePrescriptions": [], "reasoningTrace": []}
    result = verify_validation(
        pubmed_articles=ARTICLES, finder_candidates=[], response_dict=response)

    assert _outcomes(result, "cited_pmid_in_evidence") == ["ok"]


def test_invented_pmid_with_attached_particle_is_flagged():
    response = {"pubmedEvidenceSummary": "PMID 99999999에 따르면 됨", "checks": [],
                "candidatePrescriptions": [], "reasoningTrace": []}
    result = verify_validation(
        pubmed_articles=ARTICLES, finder_candidates=[], response_dict=response)

    assert result.status == "flagged"
    assert "flagged" in _outcomes(result, "cited_pmid_in_evidence")


# Important 5: 자릿수 경계(7~8)를 고정한다. 범위를 넓히는 뮤테이션이 있으면
# 이 두 테스트가 빨개져야 한다.
def test_pmid_pattern_rejects_six_digit_number():
    response = {"pubmedEvidenceSummary": "PMID 123456 참고", "checks": [],
                "candidatePrescriptions": [], "reasoningTrace": []}
    result = verify_validation(
        pubmed_articles=ARTICLES, finder_candidates=[], response_dict=response)

    assert _outcomes(result, "cited_pmid_in_evidence") == ["skipped"]


def test_pmid_pattern_rejects_nine_digit_number():
    response = {"pubmedEvidenceSummary": "PMID 123456789 참고", "checks": [],
                "candidatePrescriptions": [], "reasoningTrace": []}
    result = verify_validation(
        pubmed_articles=ARTICLES, finder_candidates=[], response_dict=response)

    assert _outcomes(result, "cited_pmid_in_evidence") == ["skipped"]


# --- 리뷰 Important 4: _code 의 처방코드 fallback 이 테스트되지 않던 문제 ---
def test_candidate_code_matches_via_hangul_key_fallback():
    response = {"pubmedEvidenceSummary": "", "checks": [],
                "candidatePrescriptions": [{"처방코드": "A01"}],
                "reasoningTrace": []}
    result = verify_validation(
        pubmed_articles=[], finder_candidates=[{"처방코드": "A01"}],
        response_dict=response)

    assert _outcomes(result, "candidates_from_finder") == ["ok"]


# --- 리뷰 MINOR: dict 가 아닌 후보 행을 "정상"으로 흘려보내던 문제 ---
def test_malformed_candidate_row_is_flagged():
    response = {"pubmedEvidenceSummary": "", "checks": [],
                "candidatePrescriptions": ["not-a-dict"],
                "reasoningTrace": []}
    result = verify_validation(
        pubmed_articles=[], finder_candidates=[{"prescription_code": "A01"}],
        response_dict=response)

    assert "flagged" in _outcomes(result, "candidates_from_finder")


# --- 리뷰 MINOR: discard("") 가 "죽은 코드"가 아님을 고정하는 회귀 테스트 ---
def test_finder_candidates_without_code_field_is_skipped_not_flagged():
    response = {"pubmedEvidenceSummary": "", "checks": [],
                "candidatePrescriptions": [{"prescription_code": "A01"}],
                "reasoningTrace": []}
    result = verify_validation(
        pubmed_articles=[], finder_candidates=[{"foo": "bar"}],
        response_dict=response)

    assert _outcomes(result, "candidates_from_finder") == ["skipped"]


def test_pubmed_articles_without_pmid_field_is_skipped_not_flagged():
    response = {"pubmedEvidenceSummary": "PMID 11111111 에 따르면", "checks": [],
                "candidatePrescriptions": [], "reasoningTrace": []}
    result = verify_validation(
        pubmed_articles=[{"title": "no pmid field"}], finder_candidates=[],
        response_dict=response)

    assert _outcomes(result, "cited_pmid_in_evidence") == ["skipped"]


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
