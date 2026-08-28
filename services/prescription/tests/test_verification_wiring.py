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
    # items=[] 이면 verify_prescriptions 의 schema_top3 검사가 rank 집합을
    # {1,2,3} 과 대조하다 항상 flagged 로 떨어진다(candidates 유무와 무관) —
    # 따라서 실제로 통과 가능한 status 는 "skipped" 가 아니라 "flagged" 다.
    # 여기서 확인하려는 것은 특정 status 값이 아니라, _safe_verify 가 정상
    # 결과를 (예외 경로처럼) skipped 로 뭉개지 않고 그대로 통과시킨다는 것.
    result = prescription_api._safe_verify(
        candidates=[{"prescription_code": "A01", "prescription_name": "약가"}],
        items=[],
    )
    assert result["status"] == "flagged"
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
