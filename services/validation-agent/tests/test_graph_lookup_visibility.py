"""F-M6: ArangoDB 처방 그래프 조회 결과가 로그에만 남지 않고 화면까지 올라온다.

`prescription_api` 는 `used_arango_top_rx` / `arango_top_rx_count` /
`used_cohort_rx` / `cohort_rx_count` 를 돌려주는데, 예전에는 Spring 로그 한
줄로만 남고 사라졌다. 그래프가 빈손이면 추천은 모델의 일반지식에만 기대게
되므로 그 사실이 의사 화면에 드러나야 한다(설계 문서 §3.2).

GC-3 fail-closed: "확인함·0건", "확인 못 함(조회 실패)", "단계 자체를 안 돌았음"
은 셋 다 다른 상태다. 하나로 뭉뚱그리지 않는다.
"""
from __future__ import annotations

import app.agent as agent
import app.tools as tools
from app.agent import run_validation_agent
from app.models import ValidationAgentRequest


def _request() -> ValidationAgentRequest:
    return ValidationAgentRequest(
        historyId=1,
        symptoms="고지혈증 추적",
        savedDiseases=[{"code": "E78", "name": "고지혈증"}],
        savedPrescriptions=[{"code": "P1", "name": "저지방식이"}],
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
    """agent 가 보는 도구 대역. conftest 의 오프라인 대역을 덮어쓴다."""

    def __init__(self, observation: dict) -> None:
        self.observation = observation

    def invoke(self, payload=None):
        return self.observation


# ---------------------------------------------------------------------------
# 도구 계약
# ---------------------------------------------------------------------------

def test_finder_relays_graph_hit_counts(monkeypatch):
    monkeypatch.setattr(tools.httpx, "Client", _fake_httpx_client({
        "prescriptions": [{"rank": 1, "prescription_code": "123456789", "name": "약"}],
        "used_arango_top_rx": True,
        "arango_top_rx_count": 7,
        "used_cohort_rx": True,
        "cohort_rx_count": 3,
    }))

    result = tools.prescription_finder.invoke({
        "patient_id": "V-1", "diseases": [{"code": "E78"}], "symptoms": "고지혈증",
    })

    lookup = result["graphLookup"]
    assert lookup["status"] == "LOADED"
    assert lookup["arangoTopRxCount"] == 7
    assert lookup["cohortRxCount"] == 3
    assert lookup["foundNothing"] is False


def test_finder_marks_empty_graph_lookup(monkeypatch):
    monkeypatch.setattr(tools.httpx, "Client", _fake_httpx_client({
        "prescriptions": [],
        "used_arango_top_rx": False,
        "arango_top_rx_count": 0,
        "used_cohort_rx": False,
        "cohort_rx_count": 0,
    }))

    result = tools.prescription_finder.invoke({
        "patient_id": "V-1", "diseases": [{"code": "E78"}], "symptoms": "고지혈증",
    })

    lookup = result["graphLookup"]
    assert lookup["status"] == "LOADED"
    assert lookup["foundNothing"] is True
    assert any("찾지 못" in line for line in lookup["evidence"])


def test_finder_failure_is_not_reported_as_zero_rows(monkeypatch):
    """조회 실패는 "0건"이 아니라 "확인 못 함"이다(GC-3)."""
    class _BoomClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args) -> bool:
            return False

        def post(self, url, json=None):
            raise RuntimeError("connection refused")

    monkeypatch.setattr(tools.httpx, "Client", _BoomClient)

    result = tools.prescription_finder.invoke({
        "patient_id": "V-1", "diseases": [{"code": "E78"}], "symptoms": "고지혈증",
    })

    lookup = result["graphLookup"]
    assert lookup["status"] == "FAILED"
    assert lookup["foundNothing"] is False


# ---------------------------------------------------------------------------
# 응답까지의 경로
# ---------------------------------------------------------------------------

def test_empty_graph_lookup_reaches_response_and_checks(monkeypatch):
    monkeypatch.setattr(agent, "prescription_finder", _StubFinder({
        "status": "LOADED",
        "evidence": ["기존 처방 RAG에서 참고 처방 후보를 조회했습니다."],
        "candidatePrescriptions": [],
        "recommendationLlmStatus": "fallback",
        "recommendationVerification": None,
        "graphLookup": {
            "status": "LOADED",
            "usedArangoTopRx": False,
            "arangoTopRxCount": 0,
            "usedCohortRx": False,
            "cohortRxCount": 0,
            "foundNothing": True,
            "evidence": ["환자 그래프에서 이 환자의 과거 처방을 찾지 못했습니다 (0건)."],
        },
    }))

    response = run_validation_agent(_request())

    lookup = response.validation["graphLookup"]
    assert lookup["foundNothing"] is True
    graph_checks = [c for c in response.checks if c.get("type") == "GRAPH_LOOKUP"]
    assert [c["status"] for c in graph_checks] == ["NO_DATA"]


def test_failed_graph_lookup_reaches_response_as_unknown(monkeypatch):
    monkeypatch.setattr(agent, "prescription_finder", _StubFinder({
        "status": "FAILED",
        "evidence": ["처방 RAG 호출 실패: boom"],
        "candidatePrescriptions": [],
        "recommendationLlmStatus": "fallback",
        "recommendationVerification": None,
        "graphLookup": {
            "status": "FAILED",
            "usedArangoTopRx": False,
            "arangoTopRxCount": 0,
            "usedCohortRx": False,
            "cohortRxCount": 0,
            "foundNothing": False,
            "evidence": ["처방 그래프를 조회하지 못했습니다: boom"],
        },
    }))

    response = run_validation_agent(_request())

    assert response.validation["graphLookup"]["status"] == "FAILED"
    graph_checks = [c for c in response.checks if c.get("type") == "GRAPH_LOOKUP"]
    assert [c["status"] for c in graph_checks] == ["UNKNOWN"]


def test_graph_lookup_absent_when_finder_reports_nothing():
    """conftest 기본 대역은 graphLookup 을 싣지 않는다.

    "확인 못 함" 은 None 으로 남고, 0건이라고 주장하는 check 는 생기지 않는다.
    """
    response = run_validation_agent(_request())

    assert response.validation["graphLookup"] is None
    assert [c for c in response.checks if c.get("type") == "GRAPH_LOOKUP"] == []
