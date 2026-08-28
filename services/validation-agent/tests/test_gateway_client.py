"""`_create_llm()` 이 만든 ChatOpenAI 클라이언트의 timeout/max_retries 계약과,
게이트웨이 호출 실패 시 조용히 삼키지 않고 로그를 남기는지를 검증한다.

최종 리뷰 CRITICAL: langchain-openai 는 timeout/max_retries 를 명시하지 않으면
내부 openai SDK 에 timeout=None(무한대) 을 넘긴다 — SDK 기본값 600s 를 오히려
무력화한다. 이 서비스는 RabbitMQ 컨슈머 스레드 하나가 prefetch_count=1 로 도는
구조라(rabbit_worker.py), 이 호출이 걸리면 ack/nack 없이 영원히 막혀 뒤에 오는
모든 환자 작업이 무기한 대기한다. max_retries=0 도 timeout 만큼 중요하다 —
재시도는 게이트웨이가 소유한다(spec §6.1).

기존 24개 테스트는 전부 `_create_llm` 을 monkeypatch 로 대체하거나 `None` 으로
고정해서, 실제로 생성되는 ChatOpenAI 객체의 설정을 한 번도 들여다보지 않았다.
이 파일이 그 공백을 메운다.
"""
from __future__ import annotations

import logging

import pytest

from app import agent


def _clear_llm_env(monkeypatch):
    monkeypatch.delenv("VALIDATION_LLM_TIMEOUT_SECONDS", raising=False)
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", "http://llm-gateway:8003/v1")


# ---------------------------------------------------------------------------
# _create_llm() 이 만드는 클라이언트의 timeout/max_retries
# ---------------------------------------------------------------------------


def test_create_llm_has_finite_default_timeout(monkeypatch):
    """CRITICAL: timeout 을 명시하지 않으면 langchain-openai 가 내부 openai SDK 에
    Timeout(timeout=None) 을 넘긴다 — 이 서비스가 걸릴 때 영원히 걸린다. 기본값
    180 초가 실제로 httpx 클라이언트까지 전달됐는지 확인한다."""
    _clear_llm_env(monkeypatch)

    llm = agent._create_llm()

    assert llm is not None
    httpx_timeout = llm.root_client._client.timeout
    assert httpx_timeout.connect is not None, "timeout=None(무한대) 이면 안 된다"
    assert httpx_timeout.read == pytest.approx(180.0)


def test_create_llm_reads_timeout_from_env(monkeypatch):
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("VALIDATION_LLM_TIMEOUT_SECONDS", "42")

    llm = agent._create_llm()

    assert llm.root_client._client.timeout.read == pytest.approx(42.0)


def test_create_llm_max_retries_is_zero(monkeypatch):
    """재시도는 게이트웨이가 소유한다(spec §6.1). SDK 가 자체적으로 재시도하면
    게이트웨이의 backoff 안에 SDK 의 backoff 가 중첩되어, 상류 429 상황에서
    호출 수가 곱으로 불어난다(4 ReAct iterations x 3 SDK attempts x 3 gateway
    attempts = 36 상류 호출)."""
    _clear_llm_env(monkeypatch)

    llm = agent._create_llm()

    assert llm.root_client.max_retries == 0


# ---------------------------------------------------------------------------
# 게이트웨이 호출 실패 로깅 — IMPORTANT: 조용히 삼키면 안 된다(GC-2 운영 측면)
# ---------------------------------------------------------------------------


class _RaisingLLM:
    """`_create_llm()` 대역. invoke() 가 항상 예외를 던진다.

    예외 메시지에 URL 을 닮은 비밀 마커를 심어, 로그가 "타입만" 남기고
    "메시지/트레이스백"은 남기지 않는지 함께 확인한다(GC-7 — LLM_GATEWAY_BASE_URL
    에 잘못 심긴 자격증명이 있다면 메시지에 요청 URL이 실릴 수 있다)."""

    SECRET_MARKER = "http://leaked-secret-token-in-url.example/should-not-be-logged"

    def invoke(self, _messages):
        raise ValueError(self.SECRET_MARKER)


def test_llm_tool_decision_failure_logs_warning_with_type_only(monkeypatch, caplog):
    monkeypatch.setattr(agent, "_create_llm", lambda: _RaisingLLM())

    with caplog.at_level(logging.WARNING, logger="validation_agent.agent"):
        result = agent._llm_tool_decision({}, [], [], 1)

    assert result is None
    records = [r for r in caplog.records if r.name == "validation_agent.agent"]
    assert any(r.levelno == logging.WARNING for r in records), "실패가 로깅되지 않았다"
    assert "ValueError" in caplog.text
    assert _RaisingLLM.SECRET_MARKER not in caplog.text


def test_generate_pubmed_queries_failure_logs_warning_with_type_only(monkeypatch, caplog):
    monkeypatch.setattr(agent, "_create_llm", lambda: _RaisingLLM())

    with caplog.at_level(logging.WARNING, logger="validation_agent.agent"):
        queries, source = agent._generate_pubmed_queries_with_llm({}, "검증 사유")

    assert queries == []
    assert source == "fallback"
    assert "ValueError" in caplog.text
    assert _RaisingLLM.SECRET_MARKER not in caplog.text


def test_summarize_pubmed_evidence_failure_logs_warning_with_type_only(monkeypatch, caplog):
    monkeypatch.setattr(agent, "_create_llm", lambda: _RaisingLLM())
    pubmed_evidence = [{"pmid": "111", "title": "t", "source": "s", "pubdate": "2024", "abstract": "a"}]

    with caplog.at_level(logging.WARNING, logger="validation_agent.agent"):
        summary, source = agent._summarize_pubmed_evidence({}, pubmed_evidence, "PASS")

    assert source == "fallback"
    assert "ValueError" in caplog.text
    assert _RaisingLLM.SECRET_MARKER not in caplog.text


def test_llm_finalize_failure_logs_warning_with_type_only(monkeypatch, caplog):
    monkeypatch.setattr(agent, "_create_llm", lambda: _RaisingLLM())

    with caplog.at_level(logging.WARNING, logger="validation_agent.agent"):
        result = agent._llm_finalize({})

    assert result is None
    records = [r for r in caplog.records if r.name == "validation_agent.agent"]
    assert any(r.levelno == logging.WARNING for r in records), "실패가 로깅되지 않았다"
    assert "ValueError" in caplog.text
    assert _RaisingLLM.SECRET_MARKER not in caplog.text
