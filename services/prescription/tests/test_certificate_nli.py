"""진단서 소견의 문장별 함의(NLI) 2차 판정을 검증한다.

Task 11(B(NLI) 플래그, 기본 off). 결정론적 검사(certificate_verification.
verify_certificate)와 달리 이 판정은 LLM 을 다시 호출해 문장이 premise 에서
함의되는지 묻는다. GC-2 핵심: 2차 호출이 실패·타임아웃·알 수 없는 판정을
돌려주면 절대 "ok" 가 아니라 "skipped" 다 — 검증기가 자기 실패를 통과로
바꾸면 검증층이 있는 이유가 사라진다.

verify_certificate_nli 자체는 순수 함수다(GC-1) — call_llm 을 주입받아
I/O 를 호출자(certificate_api.py)에게 미룬다. 앞 절반은 그 순수 함수만
본다. 뒤 절반은 certificate_api.py 의 배선(플래그, 게이트웨이 호출 계약,
_safe_verify_certificate 에 이어붙이는 지점)을 본다.
"""
import httpx
import pytest

from certificate_verification import verify_certificate_nli
from verification_contract import STRUCTURAL_CHECK_IDS


# ---------------------------------------------------------------------------
# 순수 함수: verify_certificate_nli (브리프 Step 1, 검증되지 않은 부분 없이 그대로)
# ---------------------------------------------------------------------------


def test_entailed_sentences_pass():
    def fake_llm(premise, hypothesis):
        return "ENTAILMENT"

    checks = verify_certificate_nli(
        premise="급성 비인두염(J00) 진단", text="환자는 급성 비인두염입니다.",
        call_llm=fake_llm)

    assert [c.outcome for c in checks] == ["ok"]


def test_contradiction_is_flagged():
    def fake_llm(premise, hypothesis):
        return "CONTRADICTION"

    checks = verify_certificate_nli(
        premise="급성 비인두염(J00) 진단", text="환자는 골절 상태입니다.",
        call_llm=fake_llm)

    assert [c.outcome for c in checks] == ["flagged"]


# GC-2 의 NLI 판. 2차 호출이 실패하면 통과가 아니라 미확인이다.
# 검증기가 자기 실패를 통과로 바꾸면 검증층이 있는 이유가 사라진다.
def test_llm_failure_is_skipped_not_ok():
    def boom(premise, hypothesis):
        raise TimeoutError("30초 초과")

    checks = verify_certificate_nli(
        premise="급성 비인두염(J00) 진단", text="환자는 급성 비인두염입니다.",
        call_llm=boom)

    assert [c.outcome for c in checks] == ["skipped"]
    assert "TimeoutError" in checks[0].evidence


def test_unknown_verdict_is_skipped():
    def weird(premise, hypothesis):
        return "아무말"

    checks = verify_certificate_nli(
        premise="p", text="환자는 급성 비인두염입니다.", call_llm=weird)

    assert [c.outcome for c in checks] == ["skipped"]


def test_empty_premise_returns_no_checks():
    checks = verify_certificate_nli(premise="", text="문장.", call_llm=lambda p, h: "ENTAILMENT")
    assert checks == []


def test_nli_entailment_is_a_grounding_check_not_structural():
    """nli_entailment 는 근거 검사다 — STRUCTURAL_CHECK_IDS 에 넣으면
    trace_step_has_observation 과 같은 이유로 "형식만 맞아도 passed" 가
    새는 구멍이 된다(verification_contract.py 의 STRUCTURAL_CHECK_IDS 문서
    참조)."""
    assert "nli_entailment" not in STRUCTURAL_CHECK_IDS


def test_multiple_sentences_each_get_their_own_check():
    calls = []

    def fake_llm(premise, hypothesis):
        calls.append(hypothesis)
        return "ENTAILMENT" if "비인두염" in hypothesis else "CONTRADICTION"

    checks = verify_certificate_nli(
        premise="급성 비인두염(J00) 진단",
        text="환자는 급성 비인두염입니다. 향후 골절 치료도 필요합니다.",
        call_llm=fake_llm)

    assert len(checks) == 2
    assert [c.id for c in checks] == ["nli_entailment", "nli_entailment"]
    assert [c.target for c in checks] == ["sentence[0]", "sentence[1]"]
    assert [c.outcome for c in checks] == ["ok", "flagged"]
    assert len(calls) == 2


# ---------------------------------------------------------------------------
# certificate_api.py 배선: 플래그, 게이트웨이 유선 계약, _safe_verify_certificate
# ---------------------------------------------------------------------------

_REAL_HTTPX_CLIENT = httpx.Client


def _install_transport(monkeypatch, handler):
    def _factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return _REAL_HTTPX_CLIENT(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", _factory)


def _request(**overrides):
    import certificate_api as ca

    defaults = dict(
        history_id=1,
        certificate_type="GENERAL",
        patient_name="홍길동",
        patient_age=30,
        patient_gender="남",
        entry_date="2026-08-28",
        symptom_detail="발열",
        diagnosis_kind="최종 진단",
        purpose="회사 제출용",
        diseases=[{"code": "J00", "name": "급성 비인두염"}],
        diagnoses=[{"code": "A001", "name": "아목시실린캡슐", "dose": 500, "time": 3, "days": 3}],
    )
    defaults.update(overrides)
    return ca.CertificateGenerateRequest(**defaults)


def test_nli_is_off_by_default(monkeypatch):
    """기본으로 켜지면 모든 요청의 비용과 지연이 조용히 늘어난다."""
    monkeypatch.delenv("LLM_VERIFICATION_NLI", raising=False)
    import importlib
    import certificate_api

    importlib.reload(certificate_api)

    assert certificate_api.NLI_ENABLED is False


def test_nli_timeout_seconds_defaults_to_30(monkeypatch):
    monkeypatch.delenv("LLM_VERIFICATION_NLI_TIMEOUT_SECONDS", raising=False)
    import importlib
    import certificate_api

    importlib.reload(certificate_api)

    assert certificate_api.NLI_TIMEOUT_SECONDS == 30.0


def test_nli_wire_contract_header_is_certificate_api_nli_and_single_attempt(monkeypatch):
    """spec §8.2: X-LLM-Caller 가 certificate-api-nli 로 분리돼야 계측이
    본 기능 호출(certificate-api)과 섞이지 않는다. 재시도가 없으므로
    한 번만 호출돼야 한다(spec §8.4 사다리)."""
    import certificate_api as ca

    captured = {"calls": 0, "headers": None}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["calls"] += 1
        captured["headers"] = request.headers
        return httpx.Response(200, json={"choices": [{"message": {"content": "ENTAILMENT"}}]})

    _install_transport(monkeypatch, handler)
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", "http://llm-gateway:8003/v1")

    verdict = ca._call_certificate_nli("premise", "hypothesis")

    assert verdict.strip() == "ENTAILMENT"
    assert captured["headers"].get("x-llm-caller") == "certificate-api-nli"
    assert captured["calls"] == 1


def test_nli_call_uses_nli_timeout_seconds_not_gateway_timeout(monkeypatch):
    """게이트웨이 총예산(136.5s)에 NLI 예산이 더해지면 호출자 타임아웃(180s)을
    넘는다(spec §8.4) — 그래서 NLI 호출은 LLM_GATEWAY_TIMEOUT_SECONDS 가
    아니라 별도의 NLI_TIMEOUT_SECONDS 를 써야 한다."""
    import certificate_api as ca

    captured_kwargs: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "ENTAILMENT"}}]})

    def _factory(*args, **kwargs):
        captured_kwargs.update(kwargs)
        kwargs["transport"] = httpx.MockTransport(handler)
        return _REAL_HTTPX_CLIENT(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", _factory)
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", "http://llm-gateway:8003/v1")
    monkeypatch.setenv("LLM_GATEWAY_TIMEOUT_SECONDS", "180")
    monkeypatch.setattr(ca, "NLI_TIMEOUT_SECONDS", 7.0)

    ca._call_certificate_nli("premise", "hypothesis")

    assert captured_kwargs.get("timeout") == 7.0


def test_nli_call_failure_is_not_swallowed_by_the_caller(monkeypatch):
    """_call_certificate_nli 자체는 실패를 삼키지 않는다 — 예외를 skipped 로
    바꾸는 책임은 verify_certificate_nli 쪽에 있다(GC-1: I/O 와 판정 로직을
    분리해 검증기를 순수 함수로 남긴다)."""
    import certificate_api as ca

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out", request=request)

    _install_transport(monkeypatch, handler)
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", "http://llm-gateway:8003/v1")

    with pytest.raises(httpx.ConnectTimeout):
        ca._call_certificate_nli("premise", "hypothesis")


def test_nli_disabled_by_default_appends_no_nli_checks(monkeypatch):
    import certificate_api as ca

    monkeypatch.setattr(ca, "NLI_ENABLED", False)
    called = {"n": 0}

    def fake_llm(premise, hypothesis):
        called["n"] += 1
        return "ENTAILMENT"

    monkeypatch.setattr(ca, "_call_certificate_nli", fake_llm)

    result = ca._safe_verify_certificate(_request(), "환자는 급성 비인두염(J00)입니다.")

    assert not any(c["id"] == "nli_entailment" for c in result["checks"])
    assert called["n"] == 0


def test_nli_enabled_outcome_comes_from_call_llm_not_from_the_flag(monkeypatch):
    """GC-5: 설정(플래그)이 아니라 실행 경로가 상태를 만든다. NLI_ENABLED 는
    nli_entailment 검사가 도는지만 결정해야 하고, 그 검사의 outcome 은
    call_llm 이 실제로 뭐라고 답했는지에서만 나와야 한다. 이 테스트는
    call_llm 이 CONTRADICTION 을 돌려줄 때 outcome 이 정확히 "flagged"
    인지 확인한다 — 플래그 값("on") 자체가 outcome 을 결정하도록 바뀌는
    변이(예: NLI_ENABLED 가 True 면 무조건 "ok")를 잡는다."""
    import certificate_api as ca

    monkeypatch.setattr(ca, "NLI_ENABLED", True)
    monkeypatch.setattr(ca, "_call_certificate_nli", lambda premise, hypothesis: "CONTRADICTION")

    result = ca._safe_verify_certificate(_request(), "환자는 골절 상태입니다.")

    nli_checks = [c for c in result["checks"] if c["id"] == "nli_entailment"]
    assert nli_checks
    assert all(c["outcome"] == "flagged" for c in nli_checks)
    assert result["status"] == "flagged"


def test_nli_enabled_llm_failure_still_skipped_through_safe_verify(monkeypatch):
    """_safe_verify_certificate 를 거쳐도 GC-2 가 유지되는지 끝까지 확인한다
    — call_llm 이 예외를 던지면 nli_entailment 는 skipped 로 남아야 하고,
    본 응답 경로(예외 전파)로는 절대 새면 안 된다(GC-4)."""
    import certificate_api as ca

    monkeypatch.setattr(ca, "NLI_ENABLED", True)

    def boom(premise, hypothesis):
        raise TimeoutError("30초 초과")

    monkeypatch.setattr(ca, "_call_certificate_nli", boom)

    result = ca._safe_verify_certificate(_request(), "환자는 급성 비인두염(J00)입니다.")

    nli_checks = [c for c in result["checks"] if c["id"] == "nli_entailment"]
    assert nli_checks
    assert all(c["outcome"] == "skipped" for c in nli_checks)
