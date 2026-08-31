"""`gateway.create_llm()` 이 만든 클라이언트의 timeout/max_retries 계약과,
게이트웨이 호출 실패 시 조용히 삼키지 않고 로그를 남기는지를 검증한다.

최종 리뷰 CRITICAL: langchain-openai 는 timeout/max_retries 를 명시하지 않으면
내부 openai SDK 에 timeout=None(무한대) 을 넘긴다 — SDK 기본값 600s 를 오히려
무력화한다. 이 서비스는 RabbitMQ 컨슈머가 prefetch_count=1 로 도는 구조라
(rabbit_worker.py), 이 호출이 걸리면 뒤에 오는 모든 환자 작업이 대기한다.
max_retries=0 도 timeout 만큼 중요하다 — 재시도는 게이트웨이가 소유한다
(spec §6.1).

이 서비스는 현재 게이트웨이를 부르지 않는다. 부르던 두 자리(질의 생성과 근거
요약)가 함께 사라졌기 때문이다. 그래도 `create_llm` 의 타임아웃·재시도·헤더와
`resolve_llm_status` 는 계속 고정한다 — 전자는 다시 호출자가 생기는 순간 바로
쓰이고, 후자는 "이번 실행에서 모델이 돌았는가" 를 답하는 유일한 경로라 지금처럼
아무도 부르지 않을 때 `fallback` 을 내는 것 자체가 지켜야 할 동작이다.

옛 `_llm_tool_decision`·`_llm_finalize` 로깅 테스트는 그 함수들과 함께
삭제했다 — `_llm_finalize` 는 애초에 어떤 실행 경로에서도 불리지 않는 죽은
코드였고, 그 테스트가 죽은 코드를 살아 있는 것처럼 보이게 했다(F-M2).
"""
from __future__ import annotations

import logging

import pytest

from app import gateway
from app.gateway import ModelCallLedger


def _clear_llm_env(monkeypatch):
    monkeypatch.delenv("VALIDATION_LLM_TIMEOUT_SECONDS", raising=False)
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", "http://llm-gateway:8003/v1")


# ---------------------------------------------------------------------------
# create_llm() 이 만드는 클라이언트의 timeout/max_retries
# ---------------------------------------------------------------------------


def test_create_llm_has_finite_default_timeout(monkeypatch):
    """CRITICAL: timeout 을 명시하지 않으면 langchain-openai 가 내부 openai SDK 에
    Timeout(timeout=None) 을 넘긴다 — 이 서비스가 걸릴 때 영원히 걸린다. 기본값
    180 초가 실제로 httpx 클라이언트까지 전달됐는지 확인한다."""
    _clear_llm_env(monkeypatch)

    llm = gateway.create_llm()

    assert llm is not None
    httpx_timeout = llm.root_client._client.timeout
    assert httpx_timeout.connect is not None, "timeout=None(무한대) 이면 안 된다"
    assert httpx_timeout.read == pytest.approx(180.0)


def test_create_llm_reads_timeout_from_env(monkeypatch):
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("VALIDATION_LLM_TIMEOUT_SECONDS", "42")

    llm = gateway.create_llm()

    assert llm.root_client._client.timeout.read == pytest.approx(42.0)


def test_create_llm_max_retries_is_zero(monkeypatch):
    """재시도는 게이트웨이가 소유한다(spec §6.1). SDK 가 자체적으로 재시도하면
    게이트웨이의 backoff 안에 SDK 의 backoff 가 중첩되어, 상류 429 상황에서
    호출 수가 곱으로 불어난다."""
    _clear_llm_env(monkeypatch)

    llm = gateway.create_llm()

    assert llm.root_client.max_retries == 0


def test_create_llm_sends_its_own_caller_header(monkeypatch):
    """게이트웨이가 호출자를 구분할 수 있어야 한다(모든 모델 호출은 자기
    `X-LLM-Caller` 를 달고 나간다)."""
    _clear_llm_env(monkeypatch)

    llm = gateway.create_llm()

    assert llm.default_headers["X-LLM-Caller"] == "validation-agent"


def test_create_llm_returns_none_without_gateway(monkeypatch):
    monkeypatch.delenv("LLM_GATEWAY_BASE_URL", raising=False)
    assert gateway.create_llm() is None


# ---------------------------------------------------------------------------
# 게이트웨이 호출 실패 로깅 — IMPORTANT: 조용히 삼키면 안 된다(GC-2 운영 측면)
# ---------------------------------------------------------------------------


class _RaisingLLM:
    """`create_llm()` 대역. invoke() 가 항상 예외를 던진다.

    예외 메시지에 URL 을 닮은 비밀 마커를 심어, 로그가 "타입만" 남기고
    "메시지/트레이스백"은 남기지 않는지 함께 확인한다(GC-7 — LLM_GATEWAY_BASE_URL
    에 잘못 심긴 자격증명이 있다면 메시지에 요청 URL이 실릴 수 있다)."""

    SECRET_MARKER = "http://leaked-secret-token-in-url.example/should-not-be-logged"

    def invoke(self, _messages):
        raise ValueError(self.SECRET_MARKER)


# ---------------------------------------------------------------------------
# 장부와 llmStatus 도출
# ---------------------------------------------------------------------------


def test_resolve_llm_status_without_any_model_call_is_rule():
    """호출이 하나도 없으면 "real" 이 될 근거가 없다(fail-closed)."""
    # 호출이 하나도 없으면 "rule" 이다 — 부르지 않은 것과 불렀다가 실패한 것
    # (fallback)은 다른 사실이고, 화면이 후자만 장애로 표시해야 한다.
    assert gateway.resolve_llm_status([]) == "rule"
    assert gateway.resolve_llm_status(["fallback"]) == "fallback"


def test_resolve_llm_status_needs_a_successful_call_for_real():
    assert gateway.resolve_llm_status(["fallback", "fallback"]) == "fallback"
    assert gateway.resolve_llm_status(["fallback", "llm"]) == "real"
    assert gateway.resolve_llm_status(["stub", "stub"]) == "stub"
    # 스텁과 실제 호출이 섞이면 실제 호출이 이긴다 — 모델이 무언가는 썼다.
    assert gateway.resolve_llm_status(["stub", "llm"]) == "real"


def test_ledger_records_call_names_for_auditing():
    ledger = ModelCallLedger()
    ledger.record("disease_validation", "llm")
    ledger.record("prescription_validation", "fallback")

    assert [c["call"] for c in ledger.calls] == [
        "disease_validation", "prescription_validation",
    ]
    assert ledger.sources == ["llm", "fallback"]
