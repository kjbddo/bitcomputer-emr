"""추천이 0건인 응답은 릴레이를 지나며 "실패" 로 바뀌지 않는다.

spec: Docs/superpowers/specs/2026-08-30-ai-service-redesign-design.md §3.2

`prescription_api` 는 이제 조회가 뒷받침하는 만큼만 추천한다. E78(고지혈증)은
PR #9 필터 이후 실제로 약제 후보가 0건이라 `prescriptions: []` 가 정상 답이다.
이 서비스는 그 답을 그대로 전달해야 한다 — 빈 목록을 호출 실패와 같은 모양으로
만들면 "우리 데이터가 뒷받침하지 않는다" 는 신호가 "뭔가 고장 났다" 로 바뀐다.

세 상태를 계속 구분한다(GC-3):
    LOADED  + foundNothing=True   조회했고 정말 0건이다
    FAILED  + foundNothing=False  조회하지 못했다
    graphLookup=None              후보 조회 단계를 아예 돌지 않았다
"""
from __future__ import annotations

import app.agent as agent
import app.tools as tools
from app.agent import run_validation_agent
from app.models import ValidationAgentRequest
from app.trace import downgrade_by_payload_source


def _request() -> ValidationAgentRequest:
    return ValidationAgentRequest(
        historyId=1,
        symptoms="건강검진에서 콜레스테롤 높다고 들었다",
        savedDiseases=[{"code": "E78", "name": "고지혈증"}],
        savedPrescriptions=[],
    )


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


def _fake_httpx_client(payload: dict):
    class _Client:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args) -> bool:
            return False

        def post(self, url, json=None):
            return _FakeResponse(payload)

    return _Client


class _StubFinder:
    def __init__(self, observation: dict) -> None:
        self.observation = observation

    def invoke(self, payload=None):
        return self.observation


_E78_BODY = {
    "prescriptions": [],
    "used_arango_top_rx": False,
    "arango_top_rx_count": 0,
    "used_cohort_rx": False,
    "cohort_rx_count": 0,
    # 후보가 0건이라 prescription_api 가 모델을 호출하지 않았다(설계 §3.2).
    "llmStatus": "skipped",
    "verification": {
        "status": "skipped",
        "checks": [],
        "skippedReason": "조회된 처방 후보가 없어 근거 대조를 수행하지 못했습니다.",
    },
    "renalGate": {"status": "unknown", "renalStatus": "undetermined", "items": []},
}


# ---------------------------------------------------------------------------
# 도구 계약
# ---------------------------------------------------------------------------

def test_empty_recommendation_is_loaded_not_failed(monkeypatch):
    monkeypatch.setattr(tools.httpx, "Client", _fake_httpx_client(_E78_BODY))

    result = tools.prescription_finder.invoke({
        "patient_id": "V-1", "diseases": [{"code": "E78"}], "symptoms": "고지혈증",
    })

    assert result["status"] == "LOADED"
    assert result["candidatePrescriptions"] == []
    # 실패 경로와 같은 모양이 되면 안 된다: 실패는 graphLookup.status=FAILED 이고
    # foundNothing 을 주장하지 않는다.
    assert result["graphLookup"]["status"] == "LOADED"
    assert result["graphLookup"]["foundNothing"] is True


def test_empty_recommendation_relays_skipped_llm_status(monkeypatch):
    """모델을 부르지 않은 사실이 화면까지 간다 — "real" 로 바뀌지 않는다."""
    monkeypatch.setattr(tools.httpx, "Client", _fake_httpx_client(_E78_BODY))

    result = tools.prescription_finder.invoke({
        "patient_id": "V-1", "diseases": [{"code": "E78"}], "symptoms": "고지혈증",
    })

    assert result["recommendationLlmStatus"] == "skipped"
    assert result["recommendationVerification"]["status"] == "skipped"
    assert result["recommendationVerification"]["skippedReason"]


def test_skipped_payload_source_does_not_promote_a_step_to_llm():
    """"skipped" 는 모델이 돌았다는 뜻이 아니다 — 스텝 출처는 fail-closed 다."""
    assert downgrade_by_payload_source("rule", "skipped") == "fallback"


# ---------------------------------------------------------------------------
# 응답까지의 경로
# ---------------------------------------------------------------------------

def _e78_observation() -> dict:
    return {
        "status": "LOADED",
        "evidence": ["기존 처방 RAG에서 참고 처방 후보를 조회했습니다."],
        "candidatePrescriptions": [],
        "recommendationLlmStatus": "skipped",
        "recommendationVerification": _E78_BODY["verification"],
        "recommendationRenalGate": _E78_BODY["renalGate"],
        "graphLookup": {
            "status": "LOADED",
            "usedArangoTopRx": False,
            "arangoTopRxCount": 0,
            "usedCohortRx": False,
            "cohortRxCount": 0,
            "foundNothing": True,
            "evidence": ["같은 상병 코호트의 처방을 그래프에서 찾지 못했습니다 (0건)."],
        },
    }


def test_empty_recommendation_reaches_the_response_as_an_empty_list(monkeypatch):
    monkeypatch.setattr(agent, "prescription_finder", _StubFinder(_e78_observation()))

    response = run_validation_agent(_request())

    assert response.recommendedPrescriptions == []
    assert response.candidatePrescriptions == []


def test_empty_recommendation_is_distinguishable_from_a_failed_lookup(monkeypatch):
    """0건과 조회 실패는 응답에서 서로 다른 check 로 나온다.

    둘 다 `recommendedPrescriptions == []` 이므로, 목록 길이만 보면 구분할 수
    없다. 구분을 지고 있는 것은 graphLookup 이다 — 화면이 그것을 읽는다.
    """
    monkeypatch.setattr(agent, "prescription_finder", _StubFinder(_e78_observation()))
    found_nothing = run_validation_agent(_request())

    failed_observation = dict(_e78_observation())
    failed_observation["status"] = "FAILED"
    failed_observation["graphLookup"] = {
        "status": "FAILED",
        "usedArangoTopRx": False,
        "arangoTopRxCount": 0,
        "usedCohortRx": False,
        "cohortRxCount": 0,
        "foundNothing": False,
        "evidence": ["처방 그래프를 조회하지 못했습니다: boom"],
    }
    monkeypatch.setattr(agent, "prescription_finder", _StubFinder(failed_observation))
    failed = run_validation_agent(_request())

    assert failed.recommendedPrescriptions == found_nothing.recommendedPrescriptions == []
    assert [c["status"] for c in found_nothing.checks if c.get("type") == "GRAPH_LOOKUP"] == [
        "NO_DATA"
    ]
    assert [c["status"] for c in failed.checks if c.get("type") == "GRAPH_LOOKUP"] == [
        "UNKNOWN"
    ]


def test_empty_recommendation_carries_prescription_llm_status_to_the_response(monkeypatch):
    monkeypatch.setattr(agent, "prescription_finder", _StubFinder(_e78_observation()))

    response = run_validation_agent(_request())

    assert response.prescriptionLlmStatus == "skipped"
    assert response.prescriptionVerification["status"] == "skipped"
