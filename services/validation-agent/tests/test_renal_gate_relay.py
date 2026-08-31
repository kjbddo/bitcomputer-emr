"""신기능 관문(renalGate)이 prescription_api 에서 응답 최상위까지 건너온다.

`renal_gate.py` 는 warn / clear / unknown 세 결과를 낸다. 그 구분이 이 부품의
전부이므로(설계 §3.3, GC-3) 릴레이가 셋을 뭉개거나 없는 것을 만들어내면 안 된다.

`prescriptionVerification` / `prescriptionLlmStatus` 와 정확히 같은 자리, 같은
원칙이다 — prescription_api 자신의 판정이므로 validation-agent 자신의 판정과
섞지 않고 최상위 별도 필드로만 나간다.
"""
from __future__ import annotations

import app.agent as agent
import app.tools as tools
from app.agent import run_validation_agent
from app.models import ValidationAgentRequest

_WARN_GATE = {
    "status": "warn",
    "renalStatus": "impaired",
    "renalEvidence": "GFR 13",
    "items": [
        {
            "rank": 1,
            "name": "다이아벡스정500mg",
            "prescriptionCode": "641600390",
            "outcome": "warn",
            "ingredient": "메트포르민",
            "evidence": "신기능 저하(GFR 13)에서 메트포르민은 젖산산증 위험",
        }
    ],
    "undeterminedReason": None,
}


def _request() -> ValidationAgentRequest:
    return ValidationAgentRequest(
        historyId=1,
        patientId=1,
        symptoms="당뇨 추적",
        savedDiseases=[{"code": "E11", "name": "2형 당뇨병"}],
        savedPrescriptions=[{"code": "641600390", "name": "다이아벡스정500mg"}],
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


# ---------------------------------------------------------------------------
# 도구 계약
# ---------------------------------------------------------------------------

def test_finder_relays_renal_gate_verbatim(monkeypatch):
    monkeypatch.setattr(tools.httpx, "Client", _fake_httpx_client({
        "prescriptions": [{"rank": 1, "prescription_code": "641600390", "name": "다이아벡스정500mg"}],
        "renalGate": _WARN_GATE,
    }))

    result = tools.prescription_finder.invoke({
        "patient_id": "V-1", "diseases": [{"code": "E11"}], "symptoms": "당뇨",
    })

    # 항목별 evidence 까지 그대로 와야 한다 — 화면이 outcome 만 쓰면 표의 범위가
    # 사라지므로 렌더링은 evidence 를 함께 보여야 한다(renal_gate.py 모듈 주석).
    assert result["recommendationRenalGate"] == _WARN_GATE


def test_finder_reports_missing_renal_gate_as_none(monkeypatch):
    """상류가 안 주면 None 이다. clear 를 지어내지 않는다."""
    monkeypatch.setattr(tools.httpx, "Client", _fake_httpx_client({
        "prescriptions": [{"rank": 1, "prescription_code": "641600390", "name": "약"}],
    }))

    result = tools.prescription_finder.invoke({
        "patient_id": "V-1", "diseases": [{"code": "E11"}], "symptoms": "당뇨",
    })

    assert result["recommendationRenalGate"] is None


def test_finder_failure_does_not_fabricate_a_gate_result(monkeypatch):
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
        "patient_id": "V-1", "diseases": [{"code": "E11"}], "symptoms": "당뇨",
    })

    assert result["status"] == "FAILED"
    assert result["recommendationRenalGate"] is None


# ---------------------------------------------------------------------------
# 응답까지의 경로
# ---------------------------------------------------------------------------

def test_renal_gate_reaches_response_top_level(monkeypatch):
    monkeypatch.setattr(agent, "prescription_finder", _StubFinder({
        "status": "LOADED",
        "evidence": ["기존 처방 RAG에서 참고 처방 후보를 조회했습니다."],
        "candidatePrescriptions": [
            {"rank": 1, "prescription_code": "641600390", "name": "다이아벡스정500mg"}
        ],
        "recommendationLlmStatus": "real",
        "recommendationVerification": None,
        "recommendationRenalGate": _WARN_GATE,
    }))

    response = run_validation_agent(_request())

    assert response.prescriptionRenalGate == _WARN_GATE


def test_renal_gate_is_none_when_finder_never_ran():
    """conftest 기본 대역은 renalGate 를 싣지 않는다 — "확인 못 함" 이 남는다."""
    response = run_validation_agent(_request())

    assert response.prescriptionRenalGate is None


def test_renal_gate_is_not_merged_into_validation_agent_verification(monkeypatch):
    """다른 서비스의 판정을 자기 판정에 섞지 않는다(최종 리뷰 C1과 같은 원칙)."""
    monkeypatch.setattr(agent, "prescription_finder", _StubFinder({
        "status": "LOADED",
        "evidence": [],
        "candidatePrescriptions": [
            {"rank": 1, "prescription_code": "641600390", "name": "다이아벡스정500mg"}
        ],
        "recommendationLlmStatus": "real",
        "recommendationVerification": None,
        "recommendationRenalGate": _WARN_GATE,
    }))

    response = run_validation_agent(_request())

    assert "renalGate" not in (response.verification or {})
    assert "renalGate" not in response.validation
