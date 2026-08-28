"""PrescriptionRecommendResponse 가 llmStatus 필드를 갖고, 실행 경로에서
도출되는지 확인한다(spec §6.2, GC-3).

필드 존재 여부만 확인하면, llm_status 계산 자체가 삭제되고 고정값 "real" 만
남아도 테스트가 계속 통과할 수 있다(Task 6 리뷰에서 지적된 함정). 그래서
stub/real 두 실행 경로를 각각 실제로 실행시켜 llmStatus 값 자체도 검증한다.

prescription_api 모듈은 로드 시 ARANGO_PASSWORD 를 요구하므로(env_check.require_env),
다른 테스트 파일들과 동일하게 import 전에 stub 모드로 고정한다.
"""
import os

os.environ.setdefault("ARANGO_PASSWORD", "test-only-not-used")
os.environ["LLM_PROVIDER"] = "stub"
os.environ.pop("GOOGLE_API_KEY", None)

import prescription_api as pa  # noqa: E402
from prescription_api import PrescriptionRecommendResponse  # noqa: E402


def test_response_model_has_llm_status():
    fields = PrescriptionRecommendResponse.model_fields
    assert "llmStatus" in fields


def test_engine_status_still_present():
    """GC-5: 기존 필드의 의미를 바꾸지 않는다."""
    fields = PrescriptionRecommendResponse.model_fields
    assert "engineStatus" in fields


def _request(**overrides):
    defaults = dict(
        patient_id="p-llm-status-1",
        symptoms="발열",
        history="특이사항 없음",
        top_rx=[{"처방명": "아목시실린캡슐", "처방코드": "A001"}],
        fetch_top_rx_from_arango=False,
        fetch_cohort_rx_from_arango=False,
    )
    defaults.update(overrides)
    return pa.PrescriptionRecommendRequest(**defaults)


def test_stub_provider_reports_llm_status_stub(monkeypatch):
    """stub 모드로 실제 recommend() 를 실행해 llmStatus 가 "stub" 인지 본다.

    stub_prescription_response 가 실제로 호출된 경로에서 나온 값이어야 하며,
    단지 필드 기본값 "real" 이 우연히 통과하는 게 아니어야 한다.
    """
    monkeypatch.setenv("LLM_PROVIDER", "stub")

    resp = pa.recommend(_request(), x_prescription_eval_trace=None)

    assert resp.llmStatus == "stub"


def test_real_provider_reports_llm_status_real(monkeypatch):
    """게이트웨이 호출이 실제로 성공한 경로에서만 "real" 이 나오는지 본다.

    _invoke_gateway_json 을 대역으로 바꿔 네트워크 없이 "게이트웨이가 실제로
    호출됐다" 는 상황만 재현한다 — 값 자체는 recommend() 의 실행 경로가 계산한다.
    """
    monkeypatch.setenv("LLM_PROVIDER", "real")
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", "http://dummy-gateway.invalid/v1")

    calls = []

    def _fake_invoke_gateway_json(system_prompt, user_prompt):
        calls.append((system_prompt, user_prompt))
        return (
            '{"prescriptions": ['
            '{"rank": 1, "name": "아목시실린캡슐", "prescription_code": "A001", '
            '"dosage": "1일 3회", "reason": "발열"},'
            '{"rank": 2, "name": "미기재", "prescription_code": "미기재", '
            '"dosage": "미기재", "reason": "발열"},'
            '{"rank": 3, "name": "미기재", "prescription_code": "미기재", '
            '"dosage": "미기재", "reason": "발열"}'
            ']}'
        )

    monkeypatch.setattr(pa, "_invoke_gateway_json", _fake_invoke_gateway_json)

    resp = pa.recommend(_request(), x_prescription_eval_trace=None)

    assert resp.llmStatus == "real"
    assert calls, "게이트웨이 호출 대역이 실제로 호출되지 않았다"
