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


def _sequenced_llm_decision(sequence):
    """`_llm_tool_decision` 을 대신할 결정론적 대역(tests/test_llm_status.py 복제)."""
    remaining = iter(sequence)

    def fake(state, reasoning_trace, pubmed_queries, iteration):
        return next(remaining, None)

    return fake


def _install_llm_decisions(monkeypatch):
    """tests/test_llm_status.py 의 동명 헬퍼 복제. 결정 루프의 모든 반복이
    LLM 결정이고 Prescription Finder 를 반드시 거치도록 시퀀스를 구성한다."""
    import app.agent as agent
    monkeypatch.setenv("LLM_PROVIDER", "real")
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", "http://dummy-gateway.invalid")
    monkeypatch.setattr(agent, "_create_llm", lambda: None)
    monkeypatch.setattr(
        agent,
        "_llm_tool_decision",
        _sequenced_llm_decision([
            {"thought": "x-ray 로드", "action": "X-ray Result Loader", "actionInput": {}},
            {"thought": "상병 검증", "action": "Disease Validator", "actionInput": {}},
            {"thought": "처방 검증", "action": "Prescription Validator", "actionInput": {}},
            {"thought": "처방 후보 조회", "action": "Prescription Finder", "actionInput": {}},
            {"thought": "종료", "action": "FINALIZE", "actionInput": {}},
        ]),
    )


def test_response_actually_carries_verification(monkeypatch):
    """모델에 필드가 있는 것과 응답이 그것을 채우는 것은 다른 말이다.
    배선이 끊겨도 필드 존재 테스트는 통과하므로 이 단언이 필요하다."""
    from app.agent import run_validation_agent

    _install_llm_decisions(monkeypatch)

    response = run_validation_agent(_request())

    assert response.verification is not None
    assert response.verification["status"] in {"passed", "flagged", "skipped"}
