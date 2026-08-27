"""핵심 경로와 권한 거부를 검증한다.

RBAC 은 '되는 것'보다 '안 되는 것'을 확인해야 의미가 있으므로, 권한 거부와
그 감사 기록까지 포함한다.
"""
from __future__ import annotations

import httpx
import pytest

from conftest import csrf_headers


def test_unauthenticated_patient_access_is_rejected():
    with httpx.Client(base_url="http://localhost:8080", timeout=30.0) as client:
        response = client.get("/api/patients/1")
    assert response.status_code == 401


def test_health_endpoint_is_public():
    with httpx.Client(base_url="http://localhost:8080", timeout=30.0) as client:
        assert client.get("/actuator/health").status_code == 200


@pytest.fixture()
def patient_id(doctor: httpx.Client) -> int:
    """환자를 생성(또는 이미 있으면 재사용)한다.

    실제 엔드포인트는 POST /api/patients/get_patient_id 이고(단순 POST
    /api/patients 는 존재하지 않는다), PatientDTO 는 phone 이 아니라
    phoneNumber 필드를 쓰며 identityNumber·visitNumber 가 필수다.
    identityNumber 는 유니크 제약이 있고, PatientServiceImpl.createPatient 가
    이미 존재하는 identityNumber 는 새로 만들지 않고 기존 환자를 반환하도록
    돼 있어 이 테스트를 재실행해도 매번 같은 환자로 수렴한다(멱등성).
    """
    response = doctor.post(
        "/api/patients/get_patient_id",
        headers=csrf_headers(doctor),
        json={
            "name": "E2E 환자",
            "phoneNumber": "010-0000-0000",
            "identityNumber": "E2E-IDENTITY-0001",
            "visitNumber": "E2E-VISIT-0001",
            "birth": "1990-01-01",
            "gender": "M",
        },
    )
    assert response.status_code in (200, 201), f"환자 생성 실패: {response.text}"
    body = response.json()
    return int(body["patientId"])


def test_doctor_can_create_and_read_patient(doctor: httpx.Client, patient_id: int):
    response = doctor.get(f"/api/patients/{patient_id}")
    assert response.status_code == 200
    assert response.json()["name"] == "E2E 환자"


def test_doctor_reaches_ai_recommendation(doctor: httpx.Client, patient_id: int):
    """stub provider 이므로 실제 LLM 없이 응답이 온다.

    PrescriptionRecommendRequestDTO 는 @JsonProperty 로 history_diagnose_id
    (snake_case)를 받는다 — patientId 필드는 이 DTO에 아예 없다(본문이 아니라
    history_diagnose_id 로 환자를 역참조한다).
    """
    response = doctor.post(
        "/api/agent/prescription/recommend",
        headers=csrf_headers(doctor),
        json={"history_diagnose_id": 1},
    )
    # 권한은 통과해야 한다. 데이터가 없어 400/404 가 날 수는 있으나 403 은 안 된다.
    assert response.status_code != 403, "DOCTOR 가 AI 추천에서 거부됐다"


def test_stub_engine_status_is_exposed():
    """처방 서비스가 stub 으로 돌고 있음을 응답에서 확인할 수 있어야 한다."""
    with httpx.Client(base_url="http://localhost:8001", timeout=60.0) as client:
        response = client.post(
            "/api/agent/prescription/recommend",
            json={
                "patient_id": "e2e",
                "symptoms": "기침",
                "history": "",
                "top_rx": [{"처방명": "테스트약", "처방코드": "T001"}],
                "similar_outcomes": "",
                "disease_codes": [],
                "fetch_top_rx_from_arango": False,
                "fetch_cohort_rx_from_arango": False,
            },
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["engineStatus"] == "stub"
    assert len(body["prescriptions"]) == 3


def test_receptionist_is_denied_ai_recommendation(receptionist: httpx.Client):
    response = receptionist.post(
        "/api/agent/prescription/recommend",
        headers=csrf_headers(receptionist),
        json={"history_diagnose_id": 1},
    )
    assert response.status_code == 403


def test_denied_attempt_is_audited(receptionist: httpx.Client, super_user: httpx.Client):
    receptionist.post(
        "/api/agent/prescription/recommend",
        headers=csrf_headers(receptionist),
        json={"history_diagnose_id": 1},
    )

    response = super_user.get("/api/audit/logs?page=0&size=50")
    assert response.status_code == 200

    entries = response.json()["content"]
    denied = [
        e for e in entries
        if e["outcome"] == "DENIED" and e["actorUsername"] == "e2e_receptionist"
    ]
    assert denied, "권한 거부가 감사 로그에 기록되지 않았다"
    assert denied[0]["actorRole"] == "RECEPTIONIST"


def test_patient_lookup_is_audited(doctor: httpx.Client, super_user: httpx.Client, patient_id: int):
    doctor.get(f"/api/patients/{patient_id}")

    response = super_user.get("/api/audit/logs?page=0&size=50")
    entries = response.json()["content"]

    views = [
        e for e in entries
        if e["action"] == "PATIENT_VIEW" and e["targetPatientId"] == patient_id
    ]
    assert views, "환자 조회가 감사 로그에 기록되지 않았다"
    assert views[0]["actorRole"] == "DOCTOR"
    assert views[0]["requestIp"]


def test_doctor_cannot_read_audit_log(doctor: httpx.Client):
    assert doctor.get("/api/audit/logs").status_code == 403
