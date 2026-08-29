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
