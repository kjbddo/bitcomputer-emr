import hashlib
import pathlib

from app.verification import verify_validation
from app.models import ValidationAgentResponse


ARTICLES = [
    {"pmid": "11111111", "title": "A", "abstract": "본문"},
    {"pmid": "22222222", "title": "B", "abstract": "본문"},
]


def _outcomes(result, check_id):
    return [c.outcome for c in result.checks if c.id == check_id]


def _evidence(result, check_id):
    return [c.evidence for c in result.checks if c.id == check_id]


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


# --- 최종 리뷰 C2: candidates_from_finder 는 응답을 자기 자신과 비교한다 ---
#
# 실제 배선(agent.py)에서 state["finder_candidates"] 와 state["candidate_prescriptions"]
# 는 같은 finder 관측값에서 나온다 — 하나는 원본 누적, 하나는 그 정규화값이다.
# 그래서 정상 입력으로는 outside 가 구조적으로 항상 공집합이라 flagged 가 나올
# 수 없고, ok 만 나온다. 이 ok 하나가 근거 검사로 집계되면 트레이스도 비고
# cited_pmid_in_evidence 도 skipped 인 응답이 "passed" 로 나간다 — GC-2 를
# 실질적으로 우회한다. candidates_from_finder 를 STRUCTURAL_CHECK_IDS 로
# 옮기면 이 ok 하나만으로는 더 이상 passed 가 나오지 않아야 한다.
def test_candidates_from_finder_alone_never_passes():
    response = {"pubmedEvidenceSummary": "", "checks": [],
                "candidatePrescriptions": [{"prescription_code": "A01"}],
                "reasoningTrace": []}
    result = verify_validation(
        pubmed_articles=[], finder_candidates=[{"prescription_code": "A01"}],
        response_dict=response)

    assert _outcomes(result, "candidates_from_finder") == ["ok"]
    assert result.status == "skipped"


# --- 최종 리뷰 C2(b)/IMP-1: 코드가 빈 후보의 취급 ---
#
# _code() 는 dict 행에 코드 키가 없거나 비어 있으면 "" 를 반환한다. 예전 구현은
# outside 계산에서 `- {""}` 로 그 행을 조용히 빼 버려, 대조되지 않은 행이
# "후보 N건이 모두 finder 관측값에서 옴" 이라는 evidence 에 그대로 포함됐다.
# 검사보다 evidence 가 더 많이 주장하는 이 브랜치의 반복 결함이다(GC-2).
#
# C2(b) 는 이를 flagged 로 드러냈으나, flagged 의 화면 문구는 "근거 불일치" 다
# — 출력이 근거와 어긋난다는 뜻이다. 코드가 없는 행은 근거와 어긋나는 것이
# 아니라 대조할 대상이 없는 것이고, 그건 skipped 의 정의다(IMP-1). 같은 행을
# prescription 검증기는 이미 skipped 로 분류하고 있어 두 서비스가 갈려 있었다.
# 진짜 불일치(관측값 밖의 코드)와 형식 파손은 그대로 flagged 로 남는다.
def test_candidates_with_empty_code_are_not_silently_counted_as_verified():
    response = {"pubmedEvidenceSummary": "", "checks": [],
                "candidatePrescriptions": [
                    {"prescription_name": "코드없는후보1", "prescription_code": ""},
                    {"prescription_name": "코드없는후보2", "prescription_code": ""},
                    {"prescription_name": "코드없는후보3", "prescription_code": ""},
                ],
                "reasoningTrace": []}
    result = verify_validation(
        pubmed_articles=[], finder_candidates=[{"prescription_code": "A01"}],
        response_dict=response)

    outcomes = _outcomes(result, "candidates_from_finder")
    evidence = _evidence(result, "candidates_from_finder")
    assert outcomes == ["skipped"]
    assert "3건이 모두 finder 관측값에서 옴" not in evidence[0]
    # 근거 검사가 ok 를 못 냈으므로 응답 전체는 passed 가 될 수 없다(GC-2).
    assert result.status != "passed"


def test_candidate_with_mixed_coded_and_uncoded_rows_reports_uncoded_indices():
    response = {"pubmedEvidenceSummary": "", "checks": [],
                "candidatePrescriptions": [
                    {"prescription_code": "A01"},
                    {"prescription_name": "코드없는후보", "prescription_code": ""},
                ],
                "reasoningTrace": []}
    result = verify_validation(
        pubmed_articles=[], finder_candidates=[{"prescription_code": "A01"}],
        response_dict=response)

    outcomes = _outcomes(result, "candidates_from_finder")
    evidence = _evidence(result, "candidates_from_finder")
    assert outcomes == ["skipped"]
    assert "[1]" in evidence[0]


def test_code_outside_finder_observation_is_still_flagged_beside_uncoded_row():
    """진짜 불일치는 코드 없는 행과 섞여 있어도 skipped 로 묻히지 않는다."""
    response = {"pubmedEvidenceSummary": "", "checks": [],
                "candidatePrescriptions": [
                    {"prescription_code": "ZZ99"},
                    {"prescription_name": "코드없는후보", "prescription_code": ""},
                ],
                "reasoningTrace": []}
    result = verify_validation(
        pubmed_articles=[], finder_candidates=[{"prescription_code": "A01"}],
        response_dict=response)

    assert _outcomes(result, "candidates_from_finder") == ["flagged"]
    assert "ZZ99" in _evidence(result, "candidates_from_finder")[0]


def test_malformed_row_is_still_flagged_beside_uncoded_row():
    """형식 파손도 마찬가지다 — dict 가 아닌 행은 여전히 flagged 다."""
    response = {"pubmedEvidenceSummary": "", "checks": [],
                "candidatePrescriptions": [
                    {"prescription_code": "A01"},
                    "문자열행",
                    {"prescription_name": "코드없는후보", "prescription_code": ""},
                ],
                "reasoningTrace": []}
    result = verify_validation(
        pubmed_articles=[], finder_candidates=[{"prescription_code": "A01"}],
        response_dict=response)

    assert _outcomes(result, "candidates_from_finder") == ["flagged"]


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


# --- 리뷰 후속(2회차): 마커 공유 다중 PMID 목록에서 두 번째 이후 id 가
# 전혀 추출되지 않던 문제. 리뷰어의 정확한 재현 케이스. ---
def test_multiple_pmids_sharing_marker_second_is_fabricated_is_flagged():
    response = {
        "pubmedEvidenceSummary": "PMID 11111111, 99999999 근거로 처방함",
        "checks": [], "candidatePrescriptions": [], "reasoningTrace": [],
    }
    result = verify_validation(
        pubmed_articles=[{"pmid": "11111111"}], finder_candidates=[],
        response_dict=response)

    assert result.status == "flagged"
    assert "flagged" in _outcomes(result, "cited_pmid_in_evidence")
    evidence = _evidence(result, "cited_pmid_in_evidence")[0]
    assert "99999999" in evidence


def test_multiple_pmids_sharing_marker_reversed_order_still_flagged():
    response = {
        "pubmedEvidenceSummary": "PMID 99999999, 11111111 근거로 처방함",
        "checks": [], "candidatePrescriptions": [], "reasoningTrace": [],
    }
    result = verify_validation(
        pubmed_articles=[{"pmid": "11111111"}], finder_candidates=[],
        response_dict=response)

    assert result.status == "flagged"
    assert "flagged" in _outcomes(result, "cited_pmid_in_evidence")


def test_multiple_pmids_with_hangul_separator_both_present_ok():
    response = {
        "pubmedEvidenceSummary": "PMID 11111111 및 22222222 근거로",
        "checks": [], "candidatePrescriptions": [], "reasoningTrace": [],
    }
    result = verify_validation(
        pubmed_articles=ARTICLES, finder_candidates=[], response_dict=response)

    assert _outcomes(result, "cited_pmid_in_evidence") == ["ok"]


# 리뷰(4회차): 위 테스트는 두 id 가 모두 known 이라 "구분자가 작동했다"와
# "구분자가 고장나 첫 id 만 봤다"를 구분하지 못한다(뮤테이션으로 및 지원을
# 통째로 지워도 그린으로 남는 것으로 확인됨). 비대칭 픽스처(하나는 known,
# 하나는 조작)로 구분자별 테스트를 다시 만든다 — flagged 와 evidence 에
# 조작된 id 가 실제로 이름이 올라오는지까지 확인해야 구분자가 두 번째
# id 까지 실제로 잡았음을 증명한다.
def test_multiple_pmids_with_hangul_separator_fabricated_is_flagged():
    response = {
        "pubmedEvidenceSummary": "PMID 11111111 및 99999999 근거로",
        "checks": [], "candidatePrescriptions": [], "reasoningTrace": [],
    }
    result = verify_validation(
        pubmed_articles=[{"pmid": "11111111"}], finder_candidates=[],
        response_dict=response)

    assert result.status == "flagged"
    assert "flagged" in _outcomes(result, "cited_pmid_in_evidence")
    evidence = _evidence(result, "cited_pmid_in_evidence")[0]
    assert "99999999" in evidence


# `·` 는 패턴 주석에 구분자로 이름이 올라 있었지만 테스트가 아예 없었다.
def test_multiple_pmids_with_middle_dot_separator_fabricated_is_flagged():
    response = {
        "pubmedEvidenceSummary": "PMID 11111111·99999999 근거로",
        "checks": [], "candidatePrescriptions": [], "reasoningTrace": [],
    }
    result = verify_validation(
        pubmed_articles=[{"pmid": "11111111"}], finder_candidates=[],
        response_dict=response)

    assert result.status == "flagged"
    assert "flagged" in _outcomes(result, "cited_pmid_in_evidence")
    evidence = _evidence(result, "cited_pmid_in_evidence")[0]
    assert "99999999" in evidence


# --- 리뷰(4회차): 구분자를 열거하는 방식 자체가 뚫린다. 열거에 없는
# 구분자(`/`, `;`, 공백 없이 붙는 조사 `와`/`과`)는 전부 조작 id 를 숨긴다.
# 구분자를 "모양"으로 정의한다: 선택적 공백 + ASCII 영숫자도 공백도 아닌
# 문자 정확히 1개 + 선택적 공백. ---
def test_multiple_pmids_with_slash_separator_fabricated_is_flagged():
    response = {
        "pubmedEvidenceSummary": "PMID 11111111/99999999 근거로 처방함",
        "checks": [], "candidatePrescriptions": [], "reasoningTrace": [],
    }
    result = verify_validation(
        pubmed_articles=[{"pmid": "11111111"}], finder_candidates=[],
        response_dict=response)

    assert result.status == "flagged"
    assert "flagged" in _outcomes(result, "cited_pmid_in_evidence")
    evidence = _evidence(result, "cited_pmid_in_evidence")[0]
    assert "99999999" in evidence


def test_multiple_pmids_with_semicolon_separator_fabricated_is_flagged():
    response = {
        "pubmedEvidenceSummary": "PMID 11111111;99999999 근거로 처방함",
        "checks": [], "candidatePrescriptions": [], "reasoningTrace": [],
    }
    result = verify_validation(
        pubmed_articles=[{"pmid": "11111111"}], finder_candidates=[],
        response_dict=response)

    assert result.status == "flagged"
    assert "flagged" in _outcomes(result, "cited_pmid_in_evidence")
    evidence = _evidence(result, "cited_pmid_in_evidence")[0]
    assert "99999999" in evidence


def test_multiple_pmids_with_attached_particle_separator_fabricated_is_flagged():
    # "와"(보통의 한국어 접속 조사)가 앞 숫자에 공백 없이 붙는 흔한 형태.
    response = {
        "pubmedEvidenceSummary": "PMID 11111111와 99999999 근거로 처방함",
        "checks": [], "candidatePrescriptions": [], "reasoningTrace": [],
    }
    result = verify_validation(
        pubmed_articles=[{"pmid": "11111111"}], finder_candidates=[],
        response_dict=response)

    assert result.status == "flagged"
    assert "flagged" in _outcomes(result, "cited_pmid_in_evidence")
    evidence = _evidence(result, "cited_pmid_in_evidence")[0]
    assert "99999999" in evidence


# 이전 라운드가 지운 오탐이 "구분자는 공백이면 충분하다"는 규칙으로
# 되살아난다: 인용 뒤에 우연히 7~8자리인 용량 숫자가 공백만 두고 붙으면
# 목록에 딸려 들어가면 안 된다. 순수 공백은 "특수문자 정확히 1개"라는
# 모양 규칙을 만족하지 못하므로 목록이 거기서 끊겨야 한다.
def test_pmid_list_does_not_swallow_whitespace_separated_dosage():
    response = {
        "pubmedEvidenceSummary": "PMID 11111111 1234567 mg 투여",
        "checks": [], "candidatePrescriptions": [], "reasoningTrace": [],
    }
    result = verify_validation(
        pubmed_articles=[{"pmid": "11111111"}], finder_candidates=[],
        response_dict=response)

    assert _outcomes(result, "cited_pmid_in_evidence") == ["ok"]
    evidence = _evidence(result, "cited_pmid_in_evidence")[0]
    assert "1234567" not in evidence


# 두 글자 이상의 틈(예: "근거")은 목록을 끊는다 — 구분자는 정확히 1문자여야
# 한다는 모양 규칙 때문이다. 산문 중간의 숫자가 우연히 이어져도 목록에
# 딸려 들어가지 않는다.
def test_pmid_list_stops_at_multi_character_gap():
    response = {
        "pubmedEvidenceSummary": "PMID 11111111 근거 99999999",
        "checks": [], "candidatePrescriptions": [], "reasoningTrace": [],
    }
    result = verify_validation(
        pubmed_articles=[{"pmid": "11111111"}], finder_candidates=[],
        response_dict=response)

    assert _outcomes(result, "cited_pmid_in_evidence") == ["ok"]
    evidence = _evidence(result, "cited_pmid_in_evidence")[0]
    assert "99999999" not in evidence


def test_pmid_list_with_hangul_separator_and_trailing_count_phrase_not_overcaptured():
    response = {
        "pubmedEvidenceSummary": "PMID 11111111, 22222222 및 기타 3건",
        "checks": [], "candidatePrescriptions": [], "reasoningTrace": [],
    }
    result = verify_validation(
        pubmed_articles=ARTICLES, finder_candidates=[], response_dict=response)

    assert _outcomes(result, "cited_pmid_in_evidence") == ["ok"]


def test_pmid_marker_without_digits_no_match_no_crash():
    response = {"pubmedEvidenceSummary": "PMID 근거 없음", "checks": [],
                "candidatePrescriptions": [], "reasoningTrace": []}
    result = verify_validation(
        pubmed_articles=ARTICLES, finder_candidates=[], response_dict=response)

    assert _outcomes(result, "cited_pmid_in_evidence") == ["skipped"]


def test_two_separate_pmid_markers_both_extracted():
    response = {
        "pubmedEvidenceSummary": "PMID 11111111 근거, 이후 PMID 99999999 도 참고",
        "checks": [], "candidatePrescriptions": [], "reasoningTrace": [],
    }
    result = verify_validation(
        pubmed_articles=[{"pmid": "11111111"}], finder_candidates=[],
        response_dict=response)

    assert result.status == "flagged"
    evidence = _evidence(result, "cited_pmid_in_evidence")[0]
    assert "99999999" in evidence


# --- 마커 무력화 뮤테이션을 잡는 회귀 테스트(리뷰 재요청): 두 속성이
# 테스트로 고정돼 있지 않아 뮤테이션이 살아남았던 문제 ---
def test_pmid_marker_embedded_in_longer_word_not_cited():
    # 리딩 lookbehind 가 없으면 "SUBPMID" 안의 "PMID" 도 매칭된다.
    response = {"pubmedEvidenceSummary": "SUBPMID 11111111 근거", "checks": [],
                "candidatePrescriptions": [], "reasoningTrace": []}
    result = verify_validation(
        pubmed_articles=ARTICLES, finder_candidates=[], response_dict=response)

    assert _outcomes(result, "cited_pmid_in_evidence") == ["skipped"]


def test_lowercase_pmid_marker_still_extracted():
    # (?i) 플래그가 없으면 소문자 "pmid" 는 매칭되지 않는다.
    response = {"pubmedEvidenceSummary": "pmid 11111111 근거", "checks": [],
                "candidatePrescriptions": [], "reasoningTrace": []}
    result = verify_validation(
        pubmed_articles=ARTICLES, finder_candidates=[], response_dict=response)

    assert _outcomes(result, "cited_pmid_in_evidence") == ["ok"]


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
# 파일 전체가 아니라 첫 모듈 docstring 이후의 본문(계약 규칙 코드)만 비교한다 —
# 두 사본의 모듈 docstring 은 각자 어떤 서비스의 사본인지 밝히는 문구라
# 의도적으로 다르며, 그 차이는 이 검사가 잡을 대상이 아니다.
def test_contract_copy_matches_prescription():
    # tests/ -> validation-agent -> services -> (repo root)
    here = pathlib.Path(__file__).resolve().parents[1] / "app" / "verification_contract.py"
    other = (pathlib.Path(__file__).resolve().parents[2]
             / "prescription" / "verification_contract.py")
    assert here.exists() and other.exists(), (here, other)
    def body(p):
        """모듈 docstring 을 제외한 본문. 두 사본의 docstring 문구 차이는
        여기서 걸러지므로 비교 대상에 들어가지 않는다."""
        text = p.read_text(encoding="utf-8")
        return text[text.index('"""', text.index('"""') + 3) + 3:]
    assert hashlib.sha256(body(here).encode()).hexdigest() == \
           hashlib.sha256(body(other).encode()).hexdigest()


# --- Task 7: 응답 배선 (app.models.ValidationAgentResponse / app.agent) ---

def test_response_model_has_verification_field():
    assert "verification" in ValidationAgentResponse.model_fields


def test_verification_defaults_to_none():
    """기본값을 만들면 검증하지 않은 것이 검증된 것처럼 보인다."""
    assert ValidationAgentResponse.model_fields["verification"].default is None


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


def test_safe_verify_flags_response_codes_outside_raw_finder_observation():
    """검증기가 실제로 대조하는 것이 관측값 원본(state["finder_candidates"])인지,
    응답에 그대로 실리는 정규화값(state["candidate_prescriptions"])인지를
    구분하는 배선 테스트. verify_validation 을 대역으로 바꾸지 않고 진짜
    구현을 그대로 통과시킨다.

    응답의 candidatePrescriptions 에는 실제 finder 관측값 밖의 코드("FORGED")를
    하나 심어 둔다. _safe_verify 가 진짜 관측값(state["finder_candidates"])과
    대조하면 이 코드는 finder 밖의 코드로 flagged 돼야 한다.

    만약 누군가 _safe_verify 의 배선을 state["finder_candidates"] 대신
    state["candidate_prescriptions"](=응답에 그대로 실리는 정규화값, 이
    테스트에서는 일부러 FORGED 까지 포함시켜 둔다)으로 바꿔치기하면, 응답이
    자기 자신과 비교돼 known_codes 에 FORGED 까지 섞여 outside 계산이 비고
    "ok" 가 나와 이 단언이 깨진다 — 즉 이 테스트는 그 바꿔치기를 red 로
    잡아내기 위한 것이다.
    """
    import app.agent as agent

    state = {
        "finder_candidates": [{"prescription_code": "REAL1"}],
        "candidate_prescriptions": [
            {"prescription_code": "REAL1"}, {"prescription_code": "FORGED"},
        ],
    }
    response_dict = {
        "pubmedEvidenceSummary": "",
        "checks": [],
        "candidatePrescriptions": [
            {"prescription_code": "REAL1"}, {"prescription_code": "FORGED"},
        ],
        "reasoningTrace": [],
    }

    result = agent._safe_verify(state, response_dict)

    assert result["status"] == "flagged"
    finder_checks = [c for c in result["checks"] if c["id"] == "candidates_from_finder"]
    assert finder_checks and finder_checks[0]["outcome"] == "flagged"


def _request():
    from app.models import ValidationAgentRequest
    return ValidationAgentRequest(
        historyId=1,
        symptoms="기침",
        savedDiseases=[{"code": "J00", "name": "감기"}],
        savedPrescriptions=[],
    )


def _real_mode(monkeypatch):
    """게이트웨이가 설정된 실행 모드. 도구 선택 루프가 사라졌으므로 결정 대역은
    없다 — 파이프라인은 provider 와 무관하게 같은 순서로 돈다. 모델 호출
    (PubMed 질의 생성/요약)만 폴백으로 고정해 네트워크 의존을 없앤다."""
    import app.agent as agent
    monkeypatch.setenv("LLM_PROVIDER", "real")
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", "http://dummy-gateway.invalid")
    monkeypatch.delenv("VALIDATION_JOB_BUDGET_SECONDS", raising=False)
    monkeypatch.setattr(agent, "create_llm", lambda: None)


def test_response_actually_carries_verification(monkeypatch):
    """모델에 필드가 있는 것과 응답이 그것을 채우는 것은 다른 말이다.
    배선이 끊겨도 필드 존재 테스트는 통과하므로 이 단언이 필요하다."""
    from app.agent import run_validation_agent

    _real_mode(monkeypatch)

    response = run_validation_agent(_request())

    assert response.verification is not None
    assert response.verification["status"] in {"passed", "flagged", "skipped"}


# --- 최종 리뷰 C1: prescription_api 자신의 항목 단위 검증(target="prescription[N]")이
# validation-agent 응답까지 도달해야 한다. validation-agent 자신의 verification
# (app/verification.py) 은 세 검사 전부 target="response" 라 절대 "prescription[N]"
# 을 만들 수 없다 — 그 값 위에서 처방 항목 배지를 찾으면 영구히 미검증이다.
# 두 verification 은 서로 다른 서비스의 다른 판정이라 섞으면 안 된다(tools.py:205-211).

def test_response_model_has_prescription_verification_field():
    assert "prescriptionVerification" in ValidationAgentResponse.model_fields


def test_prescription_verification_defaults_to_none():
    """기본값을 만들면 검증하지 않은 것이 검증된 것처럼 보인다."""
    assert ValidationAgentResponse.model_fields["prescriptionVerification"].default is None


class _FakePrescriptionFinderWithVerification:
    """prescription_api 가 자신의 항목 단위 verification(target="prescription[N]")
    을 함께 돌려주는 상황을 재현하는 대역."""

    def invoke(self, payload=None):
        return {
            "status": "LOADED",
            "evidence": ["기존 처방 RAG에서 참고 처방 후보를 조회했습니다."],
            "candidatePrescriptions": [
                {
                    "id": 1,
                    "rank": 1,
                    "prescription_code": "C1",
                    "prescription_name": "약1",
                    "reason": "",
                    "confidence_score": 0.9,
                }
            ],
            "recommendationLlmStatus": "real",
            "recommendationVerification": {
                "status": "passed",
                "checks": [
                    {
                        "id": "code_in_candidates",
                        "target": "prescription[1]",
                        "outcome": "ok",
                        "evidence": "코드 'C1' 가 후보 1건 중 있음",
                    },
                ],
                "skippedReason": None,
            },
        }


def test_prescription_verification_flows_from_finder_to_response(monkeypatch):
    """prescription_api 의 항목 단위 검증이 최상위 응답까지 도달해야 한다
    (Diagnosis.tsx 의 처방 항목 배지가 실제로 읽는 값). validation-agent 자신의
    verification 과 뒤섞이면 안 된다 — 후자는 항상 target="response" 다."""
    import app.agent as agent

    _real_mode(monkeypatch)
    monkeypatch.setattr(agent, "prescription_finder", _FakePrescriptionFinderWithVerification())

    response = agent.run_validation_agent(_request())

    assert response.prescriptionVerification is not None
    targets = [c["target"] for c in response.prescriptionVerification["checks"]]
    assert "prescription[1]" in targets

    own_targets = {c["target"] for c in (response.verification or {}).get("checks", [])}
    assert "prescription[1]" not in own_targets, (
        "validation-agent 자신의 verification 은 항상 target=\"response\" 다 — "
        "prescription[N] 이 섞여 있으면 두 검증이 잘못 합쳐진 것이다"
    )


# --- 리뷰 Important 1: cited_pmid_in_evidence 가 실제 응답 모양에서는 우연히만
# 동작하고 있었다. response_dict.get("pubmedEvidenceSummary") 는 최상위 키인데,
# _normalize_final_result 가 만드는 실제 응답에서 그 요약은
# validation.pubmedEvidenceSummary 에 중첩돼 있다. 지금까지 탐지가 되던 이유는
# 같은 텍스트가 checks[] 항목의 message 에도 우연히 중복돼 있었기 때문이다.
# checks[] 워딩이 바뀌면(PMID 마커가 빠지면) 그 우연한 이중화가 깨지고 조작된
# 인용이 조용히 skipped 로 빠진다. ---

def test_cited_pmid_read_from_nested_validation_path():
    """checks[] 에는 PMID 텍스트가 전혀 없다 — 최상위/checks 대조만으로는 이
    조작된 인용을 절대 잡을 수 없다. validation.pubmedEvidenceSummary(실제
    응답이 쓰는 중첩 경로)를 읽어야만 flagged 가 나온다."""
    response = {
        "checks": [{"type": "OTHER", "message": "인용과 무관한 메시지"}],
        "candidatePrescriptions": [],
        "reasoningTrace": [],
        "validation": {"pubmedEvidenceSummary": "PMID 99999999 에 따르면 ..."},
    }
    result = verify_validation(
        pubmed_articles=ARTICLES, finder_candidates=[], response_dict=response)

    assert result.status == "flagged"
    assert "flagged" in _outcomes(result, "cited_pmid_in_evidence")


def test_cited_pmid_nested_path_also_catches_genuine_citation():
    """반대 방향도 고정한다: 중첩 경로에 있는 정상 인용도 checks[] 없이 ok 로
    판정돼야 한다 — 중첩 경로를 아예 안 읽는 회귀뿐 아니라, 읽되 최상위와
    OR 로 합치지 않고 뒤엎어버리는 회귀도 잡는다."""
    response = {
        "checks": [],
        "candidatePrescriptions": [],
        "reasoningTrace": [],
        "validation": {"pubmedEvidenceSummary": "PMID 11111111 에 따르면 ..."},
    }
    result = verify_validation(
        pubmed_articles=ARTICLES, finder_candidates=[], response_dict=response)

    assert _outcomes(result, "cited_pmid_in_evidence") == ["ok"]


def test_top_level_pubmed_evidence_summary_still_read_for_backward_compat():
    """실제 응답 모양은 중첩이지만, 검증기는 순수 함수라 호출자가 최상위
    pubmedEvidenceSummary 를 직접 넘기는 다른 사용도 계속 지원해야 한다
    (예: 이 파일의 기존 테스트들 전부)."""
    response = {
        "pubmedEvidenceSummary": "PMID 99999999 에 따르면 ...",
        "checks": [],
        "candidatePrescriptions": [],
        "reasoningTrace": [],
    }
    result = verify_validation(
        pubmed_articles=ARTICLES, finder_candidates=[], response_dict=response)

    assert result.status == "flagged"


def test_checks_wording_change_cannot_silently_disable_pmid_detection():
    """리뷰어가 재현한 정확한 실패 시나리오를 고정한다: checks[] 의
    PUBMED_EVIDENCE 항목 message 워딩이 바뀌어 PMID 마커를 전혀 담지 않게
    되더라도(실제 서비스 코드에서 라벨/문구가 바뀔 수 있는 부분), 조작된
    인용은 validation.pubmedEvidenceSummary 를 통해 여전히 flagged 여야
    한다 — 탐지가 checks[] 안의 우연한 문자열 중복에 기대면 안 된다."""
    response = {
        "checks": [{
            "type": "PUBMED_EVIDENCE",
            "status": "REFERENCE",
            # PMID 마커를 의도적으로 빼서 checks[] 만으로는 탐지가 불가능하게 만든다.
            "message": "근거 요약: 관련 논문 2건을 참고했습니다",
        }],
        "candidatePrescriptions": [],
        "reasoningTrace": [],
        "validation": {"pubmedEvidenceSummary": "PMID 99999999 에 따르면 ..."},
    }
    result = verify_validation(
        pubmed_articles=ARTICLES, finder_candidates=[], response_dict=response)

    assert result.status == "flagged"
    assert "flagged" in _outcomes(result, "cited_pmid_in_evidence")


# --- 리뷰 Important 2: 원본 관측값 누적 지점(세 곳) 회귀 커버리지.
# 이전 태스크가 추가한 state.setdefault(...).extend(raw_...) 세 곳은 각각
# 독립적으로 되돌려도(리버트해도) 기존 스위트가 전부 초록으로 남았다 — 실제
# 도구 호출을 거치는 end-to-end 테스트가 그 state 키를 전혀 채우지 않았고,
# raw-vs-normalized 를 증명하는 테스트는 _safe_verify 를 직접 손으로 만든
# state 로 불러 그 누적 경로 자체를 건너뛰었기 때문이다. 아래 테스트들은
# verify_validation 을 스파이(진짜 구현은 그대로 통과시킴)로 감싸, 실제
# run_validation_agent 실행 경로가 state 에 무엇을 쌓았는지 가로챈다. ---

class _FakePubmedLoader:
    """`agent.pubmed_loader` 를 대체하는 대역(tests/test_llm_status.py 의
    동명 클래스 복제). 호출마다 다른 pmid 를 돌려줘, 누적과 덮어쓰기를
    테스트에서 구분할 수 있게 한다."""

    def __init__(self):
        self.calls = 0

    def invoke(self, payload=None):
        self.calls += 1
        pmid = f"1000000{self.calls}"
        return {
            "status": "LOADED",
            "evidence": [f"PubMed에서 근거 {self.calls}건을 조회했습니다."],
            "articles": [
                {
                    "pmid": pmid,
                    "title": f"Article {self.calls}",
                    "source": "Test Journal",
                    "pubdate": "2024",
                    "abstract": "abstract",
                    "abstractSnippet": "abstract",
                }
            ],
        }


class _FakePrescriptionFinder:
    """`agent.prescription_finder` 를 대체하는 대역(tests/test_llm_status.py 의
    동명 클래스 복제)."""

    def invoke(self, payload=None):
        return {
            "status": "LOADED",
            "evidence": ["기존 처방 RAG에서 참고 처방 후보를 조회했습니다."],
            "candidatePrescriptions": [
                {
                    "id": 1,
                    "rank": 1,
                    "prescription_code": "C1",
                    "prescription_name": "약1",
                    "reason": "",
                    "confidence_score": 0.9,
                }
            ],
            "recommendationLlmStatus": "real",
        }


def _spy_on_verify_validation(monkeypatch, seen):
    """`agent.verify_validation` 을 스파이로 감싼다 — 진짜 구현은 그대로
    실행하면서, 호출부가 실제로 넘긴 kwargs 만 `seen` 에 기록한다."""
    import app.agent as agent

    real_verify = agent.verify_validation

    def spy(*, pubmed_articles, finder_candidates, response_dict):
        seen["pubmed_articles"] = list(pubmed_articles)
        seen["finder_candidates"] = list(finder_candidates)
        return real_verify(
            pubmed_articles=pubmed_articles,
            finder_candidates=finder_candidates,
            response_dict=response_dict,
        )

    monkeypatch.setattr(agent, "verify_validation", spy)


def test_pubmed_loader_populates_raw_observations_in_state(monkeypatch):
    """축적 지점 1/2: `_load_pubmed_evidence` 가 실제로 도구를 호출해 얻은 원본
    관측값을 state["pubmed_articles"] 에 쌓는지, run_validation_agent 실행 경로를
    통해 확인한다. 이 라인을 지우면 seen["pubmed_articles"] 가 빈 리스트로
    남아 이 단언이 실패한다.

    루프 제거 전에는 PubMed 조회 진입점이 둘이었다(결정 루프의 빈 쿼리 분기와
    명시적 쿼리 분기). 지금은 고정 파이프라인의 한 자리뿐이라 이 테스트가 그
    경로 전체를 덮는다."""
    import app.agent as agent

    _real_mode(monkeypatch)
    monkeypatch.setattr(agent, "pubmed_loader", _FakePubmedLoader())
    monkeypatch.setattr(agent, "prescription_finder", _FakePrescriptionFinder())

    seen: dict = {}
    _spy_on_verify_validation(monkeypatch, seen)

    agent.run_validation_agent(_request())

    assert seen["pubmed_articles"], (
        "Pubmed Loader 가 원본 관측값을 state['pubmed_articles']에 쌓아야 한다"
    )
    assert seen["pubmed_articles"][0]["pmid"] == "10000001"


def test_prescription_finder_populates_state_candidates(monkeypatch):
    """축적 지점 2/2: `_invoke_prescription_finder` 가 처방 RAG 원본 관측값을
    state["finder_candidates"] 에 쌓는지, 실행 경로를 통해 확인한다."""
    import app.agent as agent

    _real_mode(monkeypatch)
    monkeypatch.setattr(agent, "prescription_finder", _FakePrescriptionFinder())

    seen: dict = {}
    _spy_on_verify_validation(monkeypatch, seen)

    agent.run_validation_agent(_request())

    assert seen["finder_candidates"], (
        "_invoke_prescription_finder가 원본 관측값을 "
        "state['finder_candidates']에 쌓아야 한다"
    )
    assert seen["finder_candidates"][0]["prescription_code"] == "C1"


def test_pubmed_articles_accumulate_not_overwrite(monkeypatch):
    """축적 의미론 고정: state["pubmed_articles"] 는 덮어써지지 않는다.

    검증기가 최신 조회 결과만 보면, 앞선 조회에서 인용된 정상 PMID 를
    "조회 결과에 없음"으로 오탐한다.

    루프가 있던 시절에는 한 실행에서 Pubmed Loader 가 두 번 결정될 수 있어
    end-to-end 로 이 의미론을 관측할 수 있었다. 고정 파이프라인은 첫 성공에서
    멈추므로(`_load_pubmed_evidence` 의 `if articles: break`) 실행 경로 하나로는
    `.extend` 와 `=` 를 구분할 수 없다 — 그래서 축적 함수를 직접 부른다."""
    import app.agent as agent

    _real_mode(monkeypatch)
    monkeypatch.setattr(agent, "pubmed_loader", _FakePubmedLoader())

    state = {"symptoms": "기침", "saved_diseases": [], "saved_prescriptions": [],
             "pubmed_articles": [{"pmid": "99999999", "title": "이전 조회"}]}
    trace: list = []

    agent._load_pubmed_evidence(trace, state, "사유", [], agent.ModelCallLedger(), "real")

    pmids = {a["pmid"] for a in state["pubmed_articles"]}
    assert "99999999" in pmids, "앞선 조회 결과가 덮어써지면 안 된다"
    assert "10000001" in pmids, "이번 조회 결과가 누적돼야 한다"
