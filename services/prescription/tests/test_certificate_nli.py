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
    def fake_llm(premise, hypothesis, timeout):
        return "ENTAILMENT"

    checks = verify_certificate_nli(
        premise="급성 비인두염(J00) 진단", text="환자는 급성 비인두염입니다.",
        call_llm=fake_llm)

    assert [c.outcome for c in checks] == ["ok"]


def test_contradiction_is_flagged():
    def fake_llm(premise, hypothesis, timeout):
        return "CONTRADICTION"

    checks = verify_certificate_nli(
        premise="급성 비인두염(J00) 진단", text="환자는 골절 상태입니다.",
        call_llm=fake_llm)

    assert [c.outcome for c in checks] == ["flagged"]


# GC-2 의 NLI 판. 2차 호출이 실패하면 통과가 아니라 미확인이다.
# 검증기가 자기 실패를 통과로 바꾸면 검증층이 있는 이유가 사라진다.
def test_llm_failure_is_skipped_not_ok():
    def boom(premise, hypothesis, timeout):
        raise TimeoutError("30초 초과")

    checks = verify_certificate_nli(
        premise="급성 비인두염(J00) 진단", text="환자는 급성 비인두염입니다.",
        call_llm=boom)

    assert [c.outcome for c in checks] == ["skipped"]
    assert "TimeoutError" in checks[0].evidence


def test_unknown_verdict_is_skipped():
    def weird(premise, hypothesis, timeout):
        return "아무말"

    checks = verify_certificate_nli(
        premise="p", text="환자는 급성 비인두염입니다.", call_llm=weird)

    assert [c.outcome for c in checks] == ["skipped"]


def test_empty_premise_returns_no_checks():
    checks = verify_certificate_nli(premise="", text="문장.", call_llm=lambda p, h, timeout: "ENTAILMENT")
    assert checks == []


# CRITICAL 리뷰: NLI 타임아웃 예산은 요청 전체에 대한 것이지 문장마다
# 새로 지급되지 않는다. 문장이 N개면 사다리(136.5s 게이트웨이 + 30s NLI =
# 166.5s < 180s 호출자 타임아웃, spec §8.4)가 136.5 + 30×N 으로 뒤집힌다.
# 가짜 시계로 "게이트웨이가 매 호출마다 정직하게 자기 타임아웃까지 다
# 태운다"는 최악을 시뮬레이션해, 예산 소진 이후 문장은 call_llm 을 아예
# 부르지 않고 skipped 로 떨어지는지 확인한다.
def test_total_nli_latency_is_bounded_by_one_budget_not_per_sentence():
    calls = []
    clock_state = {"now": 0.0}

    def fake_clock():
        return clock_state["now"]

    def fake_llm(premise, hypothesis, timeout):
        calls.append(hypothesis)
        clock_state["now"] += 30.0  # 게이트웨이가 자기 타임아웃까지 다 태움
        return "ENTAILMENT"

    text = "첫째 문장. 둘째 문장. 셋째 문장. 넷째 문장."
    checks = verify_certificate_nli(
        premise="p", text=text, call_llm=fake_llm,
        budget_seconds=30.0, clock=fake_clock)

    assert len(checks) == 4
    # 첫 문장 호출이 끝나는 순간 예산(30s)이 이미 소진되므로, 나머지
    # 세 문장은 call_llm 을 아예 호출하지 않는다 — 문장마다 새 30초를
    # 받으면 이 assert 는 4 로 실패한다.
    assert len(calls) == 1
    assert checks[0].outcome == "ok"
    assert [c.outcome for c in checks[1:]] == ["skipped", "skipped", "skipped"]
    for skipped_check in checks[1:]:
        assert "예산" in skipped_check.evidence


# CRITICAL 리뷰 후속: 마감 검사는 호출 "전"에만 있고, 이미 시작된 호출은
# 끊지 못한다. 그래서 최악은 예산 하나가 아니라 거의 둘이다 — 문장 1이
# 자기 몫(30s)을 거의 다 태우고 나서(t=29) 마감 검사를 통과하면, 문장
# 2가 다시 새로 30초를 받아 총합이 59s 로 예산을 넘는다. 이 테스트는
# call_llm 이 실제로 받는 timeout 값을 기록해, 매 호출이 "남은" 예산으로
# 잘리는지 — 소진된 뒤에 새 30초를 다시 받지 않는지 — 확인한다.
def test_call_llm_receives_truncated_timeout_when_budget_partially_consumed():
    granted_timeouts = []
    clock_state = {"now": 0.0}

    def fake_clock():
        return clock_state["now"]

    # 첫 호출은 자기가 받은 예산(30s) 중 20s 만 쓰고 돌아온다(남은 예산 10s).
    # 둘째 호출은 자기가 받은 예산을 전부 쓴다.
    call_durations = iter([20.0, 10.0])

    def fake_llm(premise, hypothesis, timeout):
        granted_timeouts.append(timeout)
        clock_state["now"] += next(call_durations)
        return "ENTAILMENT"

    text = "첫째 문장. 둘째 문장. 셋째 문장."
    checks = verify_certificate_nli(
        premise="p", text=text, call_llm=fake_llm,
        budget_seconds=30.0, clock=fake_clock)

    assert len(checks) == 3
    # 첫 호출은 남은 예산 전체(30s)를 받는다. 둘째 호출은 새 30초가 아니라
    # 그 시점에 실제로 남은 10초로 잘려서 전달돼야 한다 — min(per_call,
    # remaining) 대신 per_call_timeout 을 그대로 넘기면 이 assert 가
    # [30.0, 30.0] 으로 실패한다.
    assert granted_timeouts == [30.0, 10.0]
    # 둘째 호출이 남은 10초를 전부 써서 예산이 소진되므로, 셋째 문장은
    # call_llm 자체가 호출되지 않고 skipped 로 떨어진다.
    assert [c.outcome for c in checks] == ["ok", "ok", "skipped"]
    assert "예산" in checks[2].evidence
    # 둘째 호출은 새 30초(budget_seconds) 가 아니라 그 시점에 실제로
    # 남은 몫만 받는다 — 소진되지 않았다고 매번 신선한 전체 예산을
    # 재지급하지 않는다.
    assert granted_timeouts[1] < 30.0
    # 실제로 소요된 총 시간(각 호출이 받은 timeout 을 다 쓴 경우를 포함해)이
    # 예산을 넘지 않는다는 일반 성질 — 마감이 호출마다 남은 몫으로 계속
    # 줄어들기 때문에 성립한다.
    assert clock_state["now"] <= 30.0


def test_nli_budget_defaults_when_not_passed():
    """budget_seconds/clock 을 넘기지 않아도 함수가 호출 가능해야 한다 —
    certificate_api.py 가 아닌 다른 호출자, 혹은 예전 시그니처로 호출하는
    테스트 코드가 깨지지 않아야 한다."""
    checks = verify_certificate_nli(
        premise="p", text="문장.", call_llm=lambda p, h, timeout: "ENTAILMENT")
    assert [c.outcome for c in checks] == ["ok"]


# IMPORTANT 1(1): NEUTRAL 을 보내는 테스트가 지금까지 하나도 없었다.
# `_VERDICT_BAD` 에서 "NEUTRAL" 을 빼도(else 분기로 떨어져 skipped 가
# 돼도) 스위트가 전부 초록이었다.
def test_neutral_verdict_is_flagged():
    def fake_llm(premise, hypothesis, timeout):
        return "NEUTRAL"

    checks = verify_certificate_nli(
        premise="급성 비인두염(J00) 진단", text="환자는 상태가 애매합니다.",
        call_llm=fake_llm)

    assert [c.outcome for c in checks] == ["flagged"]


# IMPORTANT 1(2): 종결부호 없이 줄바꿈만으로 구분된 소견을 쓰는 테스트가
# 지금까지 하나도 없었다. splitter 에서 `|\n+` 를 빼도 스위트가 전부
# 초록이었다.
def test_newline_separated_sentences_without_terminal_punctuation_still_split():
    calls = []

    def fake_llm(premise, hypothesis, timeout):
        calls.append(hypothesis)
        return "ENTAILMENT"

    text = "첫째 줄\n둘째 줄\n셋째 줄"
    checks = verify_certificate_nli(premise="p", text=text, call_llm=fake_llm)

    assert len(checks) == 3
    assert len(calls) == 3


# CRITICAL 리뷰 부록: 소수점(예: "1.5mg")이 문장 경계로 오인되면 안 된다.
# splitter 가 이를 잘못 다루면, 3문장짜리 소견이 4개 조각으로 쪼개져
# 위 예산 문제를 더 악화시킨다.
def test_decimal_point_in_dosage_is_not_a_sentence_boundary():
    calls = []

    def fake_llm(premise, hypothesis, timeout):
        calls.append(hypothesis)
        return "ENTAILMENT"

    text = (
        "환자는 급성 비인두염 진단을 받았습니다. "
        "아목시실린 1.5mg 3회/일 3일분을 처방합니다. "
        "향후 발열 시 재내원 바랍니다."
    )
    checks = verify_certificate_nli(premise="p", text=text, call_llm=fake_llm)

    assert len(checks) == 3
    assert "1.5mg" in calls[1]


def test_nli_entailment_is_a_grounding_check_not_structural():
    """nli_entailment 는 근거 검사다 — STRUCTURAL_CHECK_IDS 에 넣으면
    trace_step_has_observation 과 같은 이유로 "형식만 맞아도 passed" 가
    새는 구멍이 된다(verification_contract.py 의 STRUCTURAL_CHECK_IDS 문서
    참조)."""
    assert "nli_entailment" not in STRUCTURAL_CHECK_IDS


def test_multiple_sentences_each_get_their_own_check():
    calls = []

    def fake_llm(premise, hypothesis, timeout):
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


# IMPORTANT 2: 지금까지 NLI_ENABLED 를 필요로 하는 모든 테스트가
# monkeypatch.setattr(ca, "NLI_ENABLED", True) 로 파싱 자체를 우회했다.
# 리뷰어가 실제로 `== "on"` 을 `== "true"` 로 바꿔봤더니 185개가 전부
# 초록이었다 — test_nli_is_off_by_default 조차도, 환경변수가 비어 있으면
# "off" == "true" 가 여전히 False 라 통과해버리기 때문이다. 이 테스트는
# os.environ.get(...).strip().lower() == "on" 파싱 경로를 직접 태워서,
# 그 리터럴이 바뀌면 실제로 빨개지게 만든다.
@pytest.mark.parametrize("raw,expected", [
    ("on", True),
    ("ON", True),
    (" on ", True),
    ("On", True),
    ("true", False),
    ("1", False),
    ("off", False),
    ("", False),
])
def test_nli_enabled_env_var_parsing_covers_tolerant_shapes(monkeypatch, raw, expected):
    import importlib
    import certificate_api

    monkeypatch.setenv("LLM_VERIFICATION_NLI", raw)
    importlib.reload(certificate_api)

    assert certificate_api.NLI_ENABLED is expected

    # 다음 테스트에 영향을 주지 않도록 기본값(off)으로 되돌려 둔다.
    monkeypatch.delenv("LLM_VERIFICATION_NLI", raising=False)
    importlib.reload(certificate_api)


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

    verdict = ca._call_certificate_nli("premise", "hypothesis", 30.0)

    assert verdict.strip() == "ENTAILMENT"
    assert captured["headers"].get("x-llm-caller") == "certificate-api-nli"
    assert captured["calls"] == 1


def test_nli_call_uses_its_timeout_argument_not_the_gateway_timeout(monkeypatch):
    """게이트웨이 총예산(136.5s)에 NLI 예산이 더해지면 호출자 타임아웃(180s)을
    넘는다(spec §8.4) — 그래서 NLI 호출은 LLM_GATEWAY_TIMEOUT_SECONDS 를 쓰면
    안 된다. 후속 CRITICAL 리뷰 이후로는 NLI_TIMEOUT_SECONDS 모듈 상수도 여기서
    직접 읽지 않는다 — `_call_certificate_nli` 는 이제 `timeout` 인자로 받은
    값을 그대로 httpx 타임아웃으로 쓴다. 그 값은 verify_certificate_nli 가
    "남은" 예산으로 잘라서 넘기므로(문장마다 다를 수 있다), 함수 자신이
    NLI_TIMEOUT_SECONDS 를 다시 읽으면 그 절삭이 여기서 무시된다."""
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
    # NLI_TIMEOUT_SECONDS 를 일부러 다른 값(20.0)으로 둬서, 함수가 그 상수를
    # 몰래 다시 읽는 게 아니라 실제로 넘겨받은 timeout 인자(7.0)를 쓰는지
    # 구분해 확인한다.
    monkeypatch.setattr(ca, "NLI_TIMEOUT_SECONDS", 20.0)

    ca._call_certificate_nli("premise", "hypothesis", 7.0)

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
        ca._call_certificate_nli("premise", "hypothesis", 30.0)


def test_nli_disabled_by_default_appends_no_nli_checks(monkeypatch):
    import certificate_api as ca

    monkeypatch.setattr(ca, "NLI_ENABLED", False)
    called = {"n": 0}

    def fake_llm(premise, hypothesis, timeout):
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
    monkeypatch.setattr(ca, "_call_certificate_nli", lambda premise, hypothesis, timeout: "CONTRADICTION")

    result = ca._safe_verify_certificate(_request(), "환자는 골절 상태입니다.")

    nli_checks = [c for c in result["checks"] if c["id"] == "nli_entailment"]
    assert nli_checks
    assert all(c["outcome"] == "flagged" for c in nli_checks)
    assert result["status"] == "flagged"


def test_safe_verify_certificate_passes_nli_timeout_as_budget_seconds(monkeypatch):
    """CRITICAL 리뷰: 예산은 문장이 아니라 요청 전체에 대한 것이어야 한다.
    _safe_verify_certificate 가 NLI_TIMEOUT_SECONDS 를 verify_certificate_nli 의
    budget_seconds 로 넘기지 않으면, 이 CRITICAL 수정이 순수 함수 안에서만
    맞고 실제 배선에서는 새어나간다(문장마다 함수 기본값이 다시 적용됨)."""
    import certificate_api as ca

    captured: dict = {}

    def fake_verify_certificate_nli(*, premise, text, call_llm, **kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(ca, "NLI_ENABLED", True)
    monkeypatch.setattr(ca, "NLI_TIMEOUT_SECONDS", 7.0)
    monkeypatch.setattr(ca, "verify_certificate_nli", fake_verify_certificate_nli)

    ca._safe_verify_certificate(_request(), "환자는 급성 비인두염(J00)입니다.")

    assert captured.get("budget_seconds") == 7.0


def test_nli_enabled_llm_failure_still_skipped_through_safe_verify(monkeypatch):
    """_safe_verify_certificate 를 거쳐도 GC-2 가 유지되는지 끝까지 확인한다
    — call_llm 이 예외를 던지면 nli_entailment 는 skipped 로 남아야 하고,
    본 응답 경로(예외 전파)로는 절대 새면 안 된다(GC-4)."""
    import certificate_api as ca

    monkeypatch.setattr(ca, "NLI_ENABLED", True)

    def boom(premise, hypothesis, timeout):
        raise TimeoutError("30초 초과")

    monkeypatch.setattr(ca, "_call_certificate_nli", boom)

    result = ca._safe_verify_certificate(_request(), "환자는 급성 비인두염(J00)입니다.")

    nli_checks = [c for c in result["checks"] if c["id"] == "nli_entailment"]
    assert nli_checks
    assert all(c["outcome"] == "skipped" for c in nli_checks)


# 프로덕션 호출부(_safe_verify_certificate)는 budget_seconds 는 명시적으로
# 넘기지만 clock 은 안 넘긴다 — 기본값에 전적으로 의존한다. 그런데 시간을
# 다루는 모든 테스트가 자기 가짜 clock 을 주입하므로, 정작 프로덕션이 쓰는
# 그 기본값을 아무도 안 본다. 여기가 망가지면 매 문장이 다시 온전한 예산을
# 받아 사다리 역전이 되돌아오는데 테스트 신호가 전혀 없다.
def test_default_clock_is_monotonic():
    import inspect
    import time

    from certificate_verification import verify_certificate_nli

    default = inspect.signature(verify_certificate_nli).parameters["clock"].default
    assert default is time.monotonic
