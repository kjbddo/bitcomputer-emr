import hashlib
import pathlib

from app.verification import verify_validation
from app.models import ValidationAgentResponse




def _outcomes(result, check_id):
    return [c.outcome for c in result.checks if c.id == check_id]


def _evidence(result, check_id):
    return [c.evidence for c in result.checks if c.id == check_id]
    assert "flagged" in _outcomes(result, "candidates_from_finder")


# --- 최종 리뷰 C2: candidates_from_finder 는 응답을 자기 자신과 비교한다 ---
#
# 실제 배선(agent.py)에서 state["finder_candidates"] 와 state["candidate_prescriptions"]
# 는 같은 finder 관측값에서 나온다 — 하나는 원본 누적, 하나는 그 정규화값이다.
# 그래서 정상 입력으로는 outside 가 구조적으로 항상 공집합이라 flagged 가 나올
# 수 없고, ok 만 나온다. 이 ok 하나가 근거 검사로 집계되면 트레이스도 비고
# 근거 검사가 전부 skipped 인 응답이 "passed" 로 나간다 — GC-2 를
# 실질적으로 우회한다. candidates_from_finder 를 STRUCTURAL_CHECK_IDS 로
# 옮기면 이 ok 하나만으로는 더 이상 passed 가 나오지 않아야 한다.
def test_candidates_from_finder_alone_never_passes():
    response = {"checks": [],
                "candidatePrescriptions": [{"prescription_code": "A01"}],
                "reasoningTrace": []}
    result = verify_validation(
        finder_candidates=[{"prescription_code": "A01"}],
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
    response = {"checks": [],
                "candidatePrescriptions": [
                    {"prescription_name": "코드없는후보1", "prescription_code": ""},
                    {"prescription_name": "코드없는후보2", "prescription_code": ""},
                    {"prescription_name": "코드없는후보3", "prescription_code": ""},
                ],
                "reasoningTrace": []}
    result = verify_validation(
        finder_candidates=[{"prescription_code": "A01"}],
        response_dict=response)

    outcomes = _outcomes(result, "candidates_from_finder")
    evidence = _evidence(result, "candidates_from_finder")
    assert outcomes == ["skipped"]
    assert "3건이 모두 finder 관측값에서 옴" not in evidence[0]
    # 근거 검사가 ok 를 못 냈으므로 응답 전체는 passed 가 될 수 없다(GC-2).
    assert result.status != "passed"


def test_candidate_with_mixed_coded_and_uncoded_rows_reports_uncoded_indices():
    response = {"checks": [],
                "candidatePrescriptions": [
                    {"prescription_code": "A01"},
                    {"prescription_name": "코드없는후보", "prescription_code": ""},
                ],
                "reasoningTrace": []}
    result = verify_validation(
        finder_candidates=[{"prescription_code": "A01"}],
        response_dict=response)

    outcomes = _outcomes(result, "candidates_from_finder")
    evidence = _evidence(result, "candidates_from_finder")
    assert outcomes == ["skipped"]
    assert "[1]" in evidence[0]


def test_code_outside_finder_observation_is_still_flagged_beside_uncoded_row():
    """진짜 불일치는 코드 없는 행과 섞여 있어도 skipped 로 묻히지 않는다."""
    response = {"checks": [],
                "candidatePrescriptions": [
                    {"prescription_code": "ZZ99"},
                    {"prescription_name": "코드없는후보", "prescription_code": ""},
                ],
                "reasoningTrace": []}
    result = verify_validation(
        finder_candidates=[{"prescription_code": "A01"}],
        response_dict=response)

    assert _outcomes(result, "candidates_from_finder") == ["flagged"]
    assert "ZZ99" in _evidence(result, "candidates_from_finder")[0]


def test_malformed_row_is_still_flagged_beside_uncoded_row():
    """형식 파손도 마찬가지다 — dict 가 아닌 행은 여전히 flagged 다."""
    response = {"checks": [],
                "candidatePrescriptions": [
                    {"prescription_code": "A01"},
                    "문자열행",
                    {"prescription_name": "코드없는후보", "prescription_code": ""},
                ],
                "reasoningTrace": []}
    result = verify_validation(
        finder_candidates=[{"prescription_code": "A01"}],
        response_dict=response)

    assert _outcomes(result, "candidates_from_finder") == ["flagged"]


def test_trace_step_without_observation_is_flagged():
    response = {"checks": [],
                "candidatePrescriptions": [],
                "reasoningTrace": [{"action": "A", "observation": None}]}
    result = verify_validation(
        finder_candidates=[], response_dict=response)

    assert "flagged" in _outcomes(result, "trace_step_has_observation")


# 사전점검에서 찾은 구멍. 트레이스만 멀쩡하고 조회 데이터가 하나도 없으면
# 대조한 것이 아무것도 없다. 그때 passed 가 나오면 §5.1 이 막으려던 실패다.
def test_trace_only_never_passes():
    response = {
        "checks": [], "candidatePrescriptions": [],
        "reasoningTrace": [{"action": "A", "observation": {"status": "OK"}}],
    }
    result = verify_validation(
        finder_candidates=[], response_dict=response)

    assert _outcomes(result, "trace_step_has_observation") == ["ok"]
    assert result.status == "skipped"
    # status 가 skipped 인 케이스인데 skippedReason 이 비어 있으면 화면에는
    # "미확인"만 뜨고 이유가 안 나온다. 리뷰 Important 3.
    assert result.skippedReason == "도구 관측값이 없어 대조를 수행하지 못했습니다."




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

    def spy(*, finder_candidates, response_dict):
        seen["candidates"] = finder_candidates
        raise RuntimeError("여기서 멈춘다")

    monkeypatch.setattr(agent, "verify_validation", spy)
    result = agent._safe_verify({"finder_candidates": [{"prescription_code": "A01"}]}, {})

    assert seen["candidates"] == [{"prescription_code": "A01"}]
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
    만 폴백으로 고정해 네트워크 의존을 없앤다."""
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

    def spy(*, finder_candidates, response_dict):
        seen["finder_candidates"] = list(finder_candidates)
        return real_verify(
            finder_candidates=finder_candidates,
            response_dict=response_dict,
        )

    monkeypatch.setattr(agent, "verify_validation", spy)


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
    seen: dict = {}
    _spy_on_verify_validation(monkeypatch, seen)

    agent.run_validation_agent(_request())

    assert seen["finder_candidates"], (
        "_invoke_prescription_finder가 원본 관측값을 "
        "state['finder_candidates']에 쌓아야 한다"
    )
    assert seen["finder_candidates"][0]["prescription_code"] == "C1"


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


def test_candidate_outside_finder_is_flagged():
    response = {"checks": [],
                "candidatePrescriptions": [{"prescription_code": "Z99"}],
                "reasoningTrace": []}
    result = verify_validation(
        finder_candidates=[{"prescription_code": "A01"}],
        response_dict=response)

    assert "flagged" in _outcomes(result, "candidates_from_finder")


# --- 리뷰 Important 4: _code 의 처방코드 fallback 이 테스트되지 않던 문제 ---
def test_candidate_code_matches_via_hangul_key_fallback():
    response = {"checks": [],
                "candidatePrescriptions": [{"처방코드": "A01"}],
                "reasoningTrace": []}
    result = verify_validation(
        finder_candidates=[{"처방코드": "A01"}],
        response_dict=response)

    assert _outcomes(result, "candidates_from_finder") == ["ok"]


# --- 리뷰 MINOR: dict 가 아닌 후보 행을 "정상"으로 흘려보내던 문제 ---
def test_malformed_candidate_row_is_flagged():
    response = {"checks": [],
                "candidatePrescriptions": ["not-a-dict"],
                "reasoningTrace": []}
    result = verify_validation(
        finder_candidates=[{"prescription_code": "A01"}],
        response_dict=response)

    assert "flagged" in _outcomes(result, "candidates_from_finder")


# --- 리뷰 MINOR: discard("") 가 "죽은 코드"가 아님을 고정하는 회귀 테스트 ---
def test_finder_candidates_without_code_field_is_skipped_not_flagged():
    response = {"checks": [],
                "candidatePrescriptions": [{"prescription_code": "A01"}],
                "reasoningTrace": []}
    result = verify_validation(
        finder_candidates=[{"foo": "bar"}],
        response_dict=response)

    assert _outcomes(result, "candidates_from_finder") == ["skipped"]


def test_does_not_mutate_response():
    response = {"checks": [],
                "candidatePrescriptions": [], "reasoningTrace": []}
    import copy
    before = copy.deepcopy(response)
    verify_validation(finder_candidates=[], response_dict=response)

    assert response == before


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
