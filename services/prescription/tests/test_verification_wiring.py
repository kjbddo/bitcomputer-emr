import os

os.environ.setdefault("ARANGO_PASSWORD", "test-only-not-used")
os.environ["LLM_PROVIDER"] = "stub"

import prescription_api  # noqa: E402  (환경변수 설정 이후 import 필요)


def test_response_model_has_verification_field():
    assert "verification" in prescription_api.PrescriptionRecommendResponse.model_fields


# GC-4. 검증기가 터져도 본 응답은 성공해야 한다.
def test_verifier_exception_becomes_skipped(monkeypatch):
    def boom(**kwargs):
        raise RuntimeError("검증기 폭발")

    monkeypatch.setattr(prescription_api, "verify_prescriptions", boom)

    result = prescription_api._safe_verify(candidates=[], items=[])

    assert result["status"] == "skipped"
    assert "RuntimeError" in (result["skippedReason"] or "")


def test_safe_verify_passes_through_normal_result():
    # 확인하려는 것은 특정 status 값이 아니라, _safe_verify 가 정상 결과를
    # (예외 경로처럼) skipped 로 뭉개지 않고 그대로 통과시킨다는 것이다.
    # 후보와 항목이 실제로 맞물리는 입력을 주어 "passed" 를 받는다 — 예외
    # 경로가 내는 skipped 와 확실히 구분되는 값이다.
    #
    # 예전에는 items=[] 로 호출해 flagged 를 기대했다. schema_top3 가
    # `sorted(ranks) == [1,2,3]` 이던 시절 items=[] 는 항상 flagged 였기
    # 때문이다. 응답 길이가 가변이 된 지금 빈 응답은 온전한 형식이므로
    # (설계 §3.2) 그 기대는 더 이상 성립하지 않는다.
    class _Item:
        rank = 1
        prescription_code = "642202450"
        name = "약가"
        confidence_score = 0.5

    result = prescription_api._safe_verify(
        candidates=[{"prescription_code": "642202450", "prescription_name": "약가"}],
        items=[_Item()],
    )
    assert result["status"] == "passed"
    assert isinstance(result["checks"], list)


def test_safe_verify_receives_candidates_verbatim(monkeypatch):
    """_safe_verify 자체는 받은 candidates 를 그대로 verify_prescriptions 에 넘긴다.

    다음 테스트(test_recommend_wires_effective_top_rx_not_request)가 실제
    recommend() 호출 경로에서 req.top_rx 가 아니라 effective_top_rx 가
    전달되는지를 검증하므로, 이 테스트는 _safe_verify 자체의 단순 위임만 본다.
    """
    seen = {}

    def spy(*, candidates, items):
        seen["candidates"] = candidates
        raise RuntimeError("여기서 멈춘다")

    monkeypatch.setattr(prescription_api, "verify_prescriptions", spy)
    prescription_api._safe_verify(candidates=["조회결과"], items=[])

    assert seen["candidates"] == ["조회결과"]


def test_recommend_wires_effective_top_rx_not_request(monkeypatch):
    """검증기에 요청이 아니라 실제 조회 결과(effective_top_rx)가 간다(spec §4.1).

    req.top_rx 를 비워 두고 fetch_top_rx_from_arango=True 로 요청하면
    recommend() 는 Arango 조회 결과로 effective_top_rx 를 갈아치운다. 여기서
    Arango 조회를 가짜 값으로 패치해, 검증기가 req.top_rx(빈 리스트)가 아니라
    그 가짜 조회 결과를 받는지 직접 확인한다.

    _safe_verify 를 단위 테스트로 직접 부르는 것만으로는 recommend() 안에서
    실제로 어떤 인자가 넘어가는지 확인할 수 없다 — req.top_rx 를 넘기는
    회귀가 들어와도 조용히 통과한다. 반드시 recommend() 자체를 호출해야
    이 배선을 잡을 수 있다.
    """
    fetched_rows = [{"처방코드": "Z99", "처방명": "가짜조회결과"}]
    monkeypatch.setattr(prescription_api, "fetch_top_rx_from_arango", lambda *a, **k: fetched_rows)

    seen = {}

    def spy(*, candidates, items):
        seen["candidates"] = candidates
        raise RuntimeError("여기서 멈춘다")  # _safe_verify 가 skipped 로 흡수한다

    monkeypatch.setattr(prescription_api, "verify_prescriptions", spy)
    monkeypatch.setenv("LLM_PROVIDER", "stub")

    req = prescription_api.PrescriptionRecommendRequest(
        patient_id="p-wiring-1",
        symptoms="발열",
        history="특이사항 없음",
        top_rx=[],
        fetch_top_rx_from_arango=True,
        fetch_cohort_rx_from_arango=False,
    )

    resp = prescription_api.recommend(req, x_prescription_eval_trace=None)

    assert seen["candidates"] == fetched_rows
    assert seen["candidates"] != req.top_rx
    assert resp.verification["status"] == "skipped"


# 예외 경로의 반환 형태를 아무도 안 봤다. checks 를 None 으로 바꿔도 전체가
# 초록이었다. 이 dict 는 그대로 JSON 응답에 실려 웹이 배열로 읽으므로,
# 형태가 틀어지면 화면 쪽에서 터진다.
def test_exception_fallback_shape_is_json_ready(monkeypatch):
    import json

    def boom(**kwargs):
        raise RuntimeError("검증기 폭발")

    monkeypatch.setattr(prescription_api, "verify_prescriptions", boom)
    result = prescription_api._safe_verify(candidates=[], items=[])

    assert result["status"] == "skipped"
    assert isinstance(result["checks"], list)
    assert result["checks"] == []
    assert isinstance(result["skippedReason"], str)
    json.dumps(result)


# --- F-H1 Half 1: 약제 후보가 0건일 때의 정직한 degradation ---

def test_zero_medication_candidates_never_reports_passed(monkeypatch):
    """약제 필터가 후보를 0건으로 만들면 응답은 passed 가 아니다(GC-2).

    라이브에서 E78(고지혈증)이 정확히 이 경우다: 연결된 order_line 14행이
    전부 수가·검사라 약제는 0건이다. 조회가 성공했다는 뜻의 필드
    (used_arango_top_rx / used_cohort_rx)가 켜지지 않고, 검증은 대조할
    근거가 없으므로 skipped 로 떨어지며 이유가 남는다.
    """
    monkeypatch.setattr(prescription_api, "fetch_top_rx_from_arango", lambda *a, **k: [])
    monkeypatch.setattr(
        prescription_api, "fetch_cohort_prescriptions_by_diagnosis_codes", lambda *a, **k: []
    )
    monkeypatch.setattr(
        prescription_api, "fetch_confidence_scores_by_diagnosis_codes", lambda *a, **k: []
    )
    monkeypatch.setenv("LLM_PROVIDER", "stub")

    req = prescription_api.PrescriptionRecommendRequest(
        patient_id="p-e78",
        symptoms="건강검진에서 콜레스테롤 높다고 들었다",
        history="특이사항 없음",
        top_rx=[],
        disease_codes=["E78"],
        fetch_top_rx_from_arango=True,
        fetch_cohort_rx_from_arango=True,
    )
    resp = prescription_api.recommend(req, x_prescription_eval_trace=None)

    assert resp.used_arango_top_rx is False
    assert resp.arango_top_rx_count == 0
    assert resp.used_cohort_rx is False
    assert resp.cohort_rx_count == 0
    assert resp.verification["status"] == "skipped"
    assert resp.verification["skippedReason"]
