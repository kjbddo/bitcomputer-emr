"""회귀 테스트: LLM_PROVIDER=stub 모드에서 /api/agent/prescription/recommend 가
GOOGLE_API_KEY 없이도 동작하는지 확인한다.

Task 4 리뷰 3번째 지적사항: recommend() 상단의 GOOGLE_API_KEY 필수 체크가
resolve_provider() 를 고려하지 않아, stub 모드인데도 500 을 던지던 문제.
이후 태스크에서 추가될 CI E2E 테스트(LLM_PROVIDER=stub, 키 없음으로
POST /api/agent/prescription/recommend 호출)가 통과하려면 이 경로가 반드시
정상 동작해야 한다.

Task 7 에서 Gemini 직접 호출을 게이트웨이 경유로 교체하면서 GOOGLE_API_KEY
필수 체크 자체가 사라졌다. real 모드에서 자격증명 없이 500 을 던지던 기존
동작은, 게이트웨이 미설정(LLM_GATEWAY_BASE_URL 없음) 시 503 을 던지는 동작으로
대체되었다(spec §6.2 / prescription_api._invoke_gateway_json).

prescription_api 모듈은 로드 시 ARANGO_PASSWORD 를 요구하므로(env_check.require_env),
이 파일을 import 하기 전에 최소한의 더미 값을 채워 넣는다. Arango 자체는
fetch_top_rx_from_arango=False, fetch_cohort_rx_from_arango=False 로 두어
실제로 호출되지 않게 한다.
"""
import os

os.environ.setdefault("ARANGO_PASSWORD", "test-only-not-used")
os.environ["LLM_PROVIDER"] = "stub"
os.environ.pop("GOOGLE_API_KEY", None)

import prescription_api as pa  # noqa: E402  (환경변수 설정 이후 import 필요)


def test_recommend_stub_mode_without_google_api_key(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    req = pa.PrescriptionRecommendRequest(
        patient_id="p-stub-1",
        symptoms="발열",
        history="특이사항 없음",
        top_rx=[{"처방명": "아목시실린캡슐", "처방코드": "A001"}],
        fetch_top_rx_from_arango=False,
        fetch_cohort_rx_from_arango=False,
    )

    resp = pa.recommend(req, x_prescription_eval_trace=None)

    assert isinstance(resp, pa.PrescriptionRecommendResponse)
    assert len(resp.prescriptions) == 3
    assert [p.rank for p in resp.prescriptions] == [1, 2, 3]
    assert resp.prescriptions[0].prescription_code == "A001"


def test_recommend_real_mode_without_gateway_url_raises_503(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "real")
    monkeypatch.delenv("LLM_GATEWAY_BASE_URL", raising=False)

    req = pa.PrescriptionRecommendRequest(
        patient_id="p-real-1",
        symptoms="발열",
        history="특이사항 없음",
        top_rx=[{"처방명": "아목시실린캡슐", "처방코드": "A001"}],
        fetch_top_rx_from_arango=False,
        fetch_cohort_rx_from_arango=False,
    )

    try:
        pa.recommend(req, x_prescription_eval_trace=None)
        assert False, "LLM_GATEWAY_BASE_URL 없이 real 모드면 HTTPException 이 발생해야 한다"
    except pa.HTTPException as exc:
        assert exc.status_code == 503
        assert "LLM_GATEWAY_BASE_URL" in exc.detail
