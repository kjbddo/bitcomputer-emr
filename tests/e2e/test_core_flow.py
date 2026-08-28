"""핵심 경로와 권한 거부를 검증한다.

RBAC 은 '되는 것'보다 '안 되는 것'을 확인해야 의미가 있으므로, 권한 거부와
그 감사 기록까지 포함한다.

주의: 아래 엔드포인트 경로/필드명은 실제 컨트롤러·DTO(Task 8~11)를 기준으로
맞췄다. task-15-brief.md 초안은 몇 곳에서 실제 API 형태와 달랐다:

- 환자 생성은 `POST /api/patients` 가 아니라 `POST /api/patients/get_patient_id`
  이고, 요청 필드는 PatientDTO 기준 name/phoneNumber/identityNumber/
  visitNumber/birth/gender 이다 (phone 이 아니라 phoneNumber, id 만이 아니라
  identityNumber/visitNumber 도 필수). 응답은 항상 {"patientId": <int>} 이다.
- AI 추천(`POST /api/agent/prescription/recommend`)의 Spring 쪽 요청 DTO
  (PrescriptionRecommendRequestDTO)는 `@JsonProperty` 로 history_id /
  history_diagnose_id 등 snake_case 를 쓴다. 이 엔드포인트는 즉시
  추천 목록을 돌려주는 것이 아니라 ValidationJob(jobId/historyId/status)
  을 큐에 발행하는 비동기 트리거다 — "prescriptions"/"engineStatus" 는
  이 엔드포인트가 아니라 Python prescription-api(8001)의 stub 응답 스키마다.
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
    response = doctor.post(
        "/api/patients/get_patient_id",
        headers=csrf_headers(doctor),
        json={
            "name": "E2E 환자",
            "phoneNumber": "010-0000-0000",
            "identityNumber": "E2E-CORE-FLOW-01",
            "visitNumber": "E2E-CORE-FLOW-01-V1",
            "birth": "1990-01-01",
            "gender": "M",
        },
    )
    assert response.status_code in (200, 201), f"환자 생성 실패: {response.text}"
    return int(response.json()["patientId"])


def test_doctor_can_create_and_read_patient(doctor: httpx.Client, patient_id: int):
    response = doctor.get(f"/api/patients/{patient_id}")
    assert response.status_code == 200
    assert response.json()["name"] == "E2E 환자"


@pytest.fixture()
def doctor_employee_id(doctor: httpx.Client) -> int:
    """AI 추천이 필요로 하는 History 를 만들려면 담당 의사(employeeId)가 필요하다."""
    response = doctor.get("/api/patients/doctors")
    assert response.status_code == 200, f"의사 목록 조회 실패: {response.text}"
    matches = [d for d in response.json() if d["username"] == "e2e_doctor"]
    assert matches, "e2e_doctor 계정이 의사 목록에 없다"
    return int(matches[0]["id"])


@pytest.fixture()
def history_id(doctor: httpx.Client, patient_id: int, doctor_employee_id: int) -> int:
    """AI 추천은 history_id 로 진료 기록을 찾으므로, 실제 History 를 만들어 둔다."""
    response = doctor.post(
        "/api/histories/write_history",
        headers=csrf_headers(doctor),
        json={
            "employeeId": doctor_employee_id,
            "patientId": patient_id,
            "deptId": 1,
            "symptomDetail": "기침",
            "memo": "E2E 테스트용 진료",
            "entryDate": "2026-08-27",
        },
    )
    assert response.status_code == 200, f"진료 기록 생성 실패: {response.text}"
    return int(response.json()["id"])


def test_doctor_reaches_ai_recommendation(doctor: httpx.Client, history_id: int):
    """실제 History 를 넘겨 DOCTOR 가 권한상 AI 추천에 도달함을 확인한다.

    stub provider 이므로 실제 LLM 없이 응답이 온다. 권한은 통과해야 한다.
    """
    response = doctor.post(
        "/api/agent/prescription/recommend",
        headers=csrf_headers(doctor),
        json={"history_id": history_id},
    )
    assert response.status_code != 403, "DOCTOR 가 AI 추천에서 거부됐다"
    assert response.status_code == 200, (
        f"실제 History 를 넘겼는데도 200 이 아니다({response.status_code}): "
        f"{response.text}"
    )
    body = response.json()
    assert body["historyId"] == history_id
    assert body["status"] == "PENDING"
    assert body["jobId"]


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
        json={"history_id": 1},
    )
    assert response.status_code == 403


def test_denied_attempt_is_audited(receptionist: httpx.Client, super_user: httpx.Client):
    receptionist.post(
        "/api/agent/prescription/recommend",
        headers=csrf_headers(receptionist),
        json={"history_id": 1},
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


# ── Task 7: 부서 관리 ──────────────────────────────────────────────


def test_admin_can_create_dept_and_see_it_in_list(super_user: httpx.Client):
    """부서를 만들고 목록에서 확인한다."""
    name = "E2E진료과"

    created = super_user.post(
        "/api/admin/depts",
        headers=csrf_headers(super_user),
        json={"dept": name},
    )
    # 이미 있으면 409 — 재실행 가능해야 하므로 둘 다 허용한다
    assert created.status_code in (201, 409), created.text

    listed = super_user.get("/api/depts")
    assert listed.status_code == 200
    assert any(d["dept"] == name for d in listed.json())


def test_duplicate_dept_name_is_rejected(super_user: httpx.Client):
    name = "E2E중복과"
    super_user.post("/api/admin/depts", headers=csrf_headers(super_user), json={"dept": name})

    again = super_user.post(
        "/api/admin/depts",
        headers=csrf_headers(super_user),
        json={"dept": name},
    )
    assert again.status_code == 409


def test_create_dept_blank_name_is_rejected(super_user: httpx.Client):
    response = super_user.post(
        "/api/admin/depts",
        headers=csrf_headers(super_user),
        json={"dept": "   "},
    )
    assert response.status_code == 400


def test_admin_can_rename_dept(super_user: httpx.Client):
    """부서명을 바꾸고 응답에 반영되는지 확인한다.

    더러운 DB에서도 재실행 가능하도록, 두 이름 중 현재 존재하는 쪽을 찾아
    반대쪽으로 토글한다(매번 실행할 때마다 A→B, 다음번엔 B→A).
    """
    name_a = "E2E변경전과"
    name_b = "E2E변경후과"

    depts = super_user.get("/api/depts").json()
    current = next((d for d in depts if d["dept"] in (name_a, name_b)), None)

    if current is None:
        created = super_user.post(
            "/api/admin/depts",
            headers=csrf_headers(super_user),
            json={"dept": name_a},
        )
        assert created.status_code in (201, 409), created.text
        depts = super_user.get("/api/depts").json()
        current = next(d for d in depts if d["dept"] == name_a)

    target_name = name_b if current["dept"] == name_a else name_a

    response = super_user.put(
        f"/api/admin/depts/{current['id']}",
        headers=csrf_headers(super_user),
        json={"dept": target_name},
    )
    assert response.status_code == 200, response.text
    assert response.json()["dept"] == target_name


def test_rename_dept_blank_name_is_rejected(super_user: httpx.Client):
    depts = super_user.get("/api/depts").json()
    assert depts, "부서 목록이 비어 있다"
    target_id = depts[0]["id"]

    response = super_user.put(
        f"/api/admin/depts/{target_id}",
        headers=csrf_headers(super_user),
        json={"dept": "   "},
    )
    assert response.status_code == 400


def test_rename_unknown_dept_id_returns_404(super_user: httpx.Client):
    response = super_user.put(
        "/api/admin/depts/999999",
        headers=csrf_headers(super_user),
        json={"dept": "존재하지않는부서수정시도"},
    )
    assert response.status_code == 404


def test_unassigned_dept_exists_as_fallback(super_user: httpx.Client):
    """UNASSIGNED 는 부서 없는 직원의 대체값으로 쓰이는 실제 부서 행이다."""
    depts = super_user.get("/api/depts").json()
    assert any(d["dept"] == "UNASSIGNED" for d in depts), "UNASSIGNED 부서가 없다"


def test_doctor_cannot_create_dept(doctor: httpx.Client):
    response = doctor.post(
        "/api/admin/depts",
        headers=csrf_headers(doctor),
        json={"dept": "의사가만든과"},
    )
    assert response.status_code == 403


def test_doctor_denied_dept_creation_is_audited(doctor: httpx.Client, super_user: httpx.Client):
    """/api/admin/** 거부는 SecurityConfig 필터 단계(RestAccessDeniedHandler)에서
    나므로 컨트롤러의 @AuditPatientAccess 경로가 아니라 ACCESS_DENIED 로 감사에
    남는다. 403 응답만이 아니라 그 결과가 감사 로그에 실제로 남는지까지 확인한다.
    """
    response = doctor.post(
        "/api/admin/depts",
        headers=csrf_headers(doctor),
        json={"dept": "감사확인용과"},
    )
    assert response.status_code == 403

    audit = super_user.get(
        "/api/audit/logs",
        params={
            "actorUsername": "e2e_doctor",
            "action": "ACCESS_DENIED",
            "outcome": "DENIED",
            "size": 50,
        },
    )
    assert audit.status_code == 200
    rows = audit.json()["content"]
    assert rows, "관리자 권한 거부가 감사 로그에 기록되지 않았다"
    assert all(r["actorUsername"] == "e2e_doctor" for r in rows)
    assert all(r["action"] == "ACCESS_DENIED" for r in rows)
    assert all(r["outcome"] == "DENIED" for r in rows)


def test_denied_admin_audit_access_is_audited(receptionist: httpx.Client, super_user: httpx.Client):
    """/api/audit/** 도 SUPER_USER 전용이다 — RECEPTIONIST 의 거부된 시도 자체가
    감사에 남는 것까지 확인해 '거부 → 감사 기록' 순환을 닫는다.
    """
    response = receptionist.get("/api/audit/logs")
    assert response.status_code == 403

    audit = super_user.get(
        "/api/audit/logs",
        params={
            "actorUsername": "e2e_receptionist",
            "action": "ACCESS_DENIED",
            "outcome": "DENIED",
            "size": 50,
        },
    )
    rows = audit.json()["content"]
    assert rows, "감사 로그 조회 거부가 감사 로그에 기록되지 않았다"
    assert any(r["detail"] == "GET /api/audit/logs" for r in rows)


def test_missing_csrf_token_is_rejected_and_audited(super_user: httpx.Client):
    """CSRF_REJECTED 는 outcome 이 아니라 action 값이다 — CSRF 헤더 없이 뮤테이션을
    보내면 403 이 오고, 감사 로그에는 outcome=DENIED, action=CSRF_REJECTED 로
    (ACCESS_DENIED 가 아니라) 남아야 한다.
    """
    response = super_user.post("/api/admin/depts", json={"dept": "CSRF거부확인과"})
    assert response.status_code == 403

    audit = super_user.get(
        "/api/audit/logs",
        params={
            "actorUsername": "admin",
            "action": "CSRF_REJECTED",
            "outcome": "DENIED",
            "size": 50,
        },
    )
    assert audit.status_code == 200
    rows = audit.json()["content"]
    assert rows, "CSRF 거부가 감사 로그에 기록되지 않았다"
    assert all(r["action"] == "CSRF_REJECTED" for r in rows)
    assert all(r["outcome"] == "DENIED" for r in rows)


# ── Task 7: 감사 로그 필터 ────────────────────────────────────────


def test_audit_log_filters_narrow_results(super_user: httpx.Client, patient_id: int):
    """환자 조회 후, 그 행위가 필터로 찾아지는지 확인한다."""
    super_user.get(f"/api/patients/{patient_id}")

    filtered = super_user.get(
        "/api/audit/logs",
        params={"action": "PATIENT_VIEW", "targetPatientId": patient_id, "size": 50},
    )
    assert filtered.status_code == 200

    rows = filtered.json()["content"]
    assert rows, "필터로 조회한 감사 기록이 비어 있다"
    assert all(r["action"] == "PATIENT_VIEW" for r in rows)
    assert all(r["targetPatientId"] == patient_id for r in rows)


def test_audit_log_outcome_filter_finds_denials(super_user: httpx.Client, receptionist: httpx.Client):
    """거부된 시도가 outcome 필터로 찾아진다."""
    receptionist.post(
        "/api/agent/prescription/recommend",
        headers=csrf_headers(receptionist),
        json={"history_diagnose_id": 1},
    )

    denied = super_user.get("/api/audit/logs", params={"outcome": "DENIED", "size": 50})
    assert denied.status_code == 200

    rows = denied.json()["content"]
    assert rows, "DENIED 필터 결과가 비어 있다"
    assert all(r["outcome"] == "DENIED" for r in rows)


def test_old_super_path_is_gone(super_user: httpx.Client):
    assert super_user.get("/api/super/get_all_users").status_code == 404
