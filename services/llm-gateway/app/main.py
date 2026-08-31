"""LLM 게이트웨이.

프로덕션 서비스의 LLM 호출을 한 곳으로 모은다. 도메인 스키마를 모르며(GC-1),
파라미터 계약·재시도·계측만 소유한다. 상류 자격증명은 이 서비스에만 있다.

바깥 표면은 OpenAI 모양으로 고정돼 있고(`POST /v1/chat/completions`), 상류가
OpenAI 든 Bedrock 든 호출 서비스는 그 차이를 보지 않는다. 차이를 흡수하는
자리는 app/providers 다.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from typing import Any, Dict, Optional

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.config import Settings, load_settings
from app.metering import build_record
from app.providers import resolve_provider
from app.providers.base import (
    Provider,
    ProviderUnavailable,
    RawUsage,
    UpstreamRequest,
    facts_for,
)
from app.upstream import UpstreamError, call_upstream

logger = logging.getLogger("llm-gateway")


def _configure_logging() -> None:
    """계측 로그가 실제로 나가게 만든다.

    설정하지 않으면 이 로거에 레벨이 없어 루트의 WARNING 을 물려받는다 —
    uvicorn 기본 설정에서도 그렇다. 그러면 logger.info() 로 내보내는 계측
    레코드가 통째로 유실된다. logger.warning() 은 logging.lastResort 덕에
    stderr 로 나가기 때문에 유실이 더 눈에 안 띈다.

    **루트가 아니라 이 로거에만 설정한다.** 루트 레벨을 INFO 로 올리면 레벨이
    NOTSET 인 모든 서드파티 로거의 바닥이 함께 올라간다. 특히 httpx 가 상류
    호출마다 INFO 로 한 줄씩 찍어서, 한 줄에 JSON 하나여야 할 stdout 이
    평문과 섞인다 — 계측을 내보내려는 설정이 계측 스트림을 오염시키는 셈이다.

    propagate 는 켜 둔다. 프로덕션의 루트에는 핸들러가 없어 아무 일도 없고,
    테스트의 caplog 는 루트 핸들러로 잡기 때문에 꺼 두면 안 잡힌다.
    """
    level = os.environ.get("LOG_LEVEL", "INFO").upper()
    logger.setLevel(level)
    if not any(getattr(h, "_llm_gateway", False) for h in logger.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(message)s"))
        handler._llm_gateway = True  # type: ignore[attr-defined]
        logger.addHandler(handler)


_configure_logging()

app = FastAPI(title="LLM Gateway", version="0.2.0")

SETTINGS: Settings = load_settings()
# 여기서 던지지 않는다. 설정이 깨졌다고 컨테이너가 크래시 루프에 빠지면
# /health 조차 못 본다. 대신 미해석 상태로 남아 모든 요청을 503 으로 실패시키고,
# 그 사실이 계측에 provider=unresolved 로 찍힌다 — 다른 제공자로 대신 붙지 않는다.
PROVIDER: Provider = resolve_provider(SETTINGS)
if PROVIDER.name != SETTINGS.provider:
    logger.warning(
        json.dumps(
            {
                "event": "provider_unresolved",
                "providerConfigured": SETTINGS.provider,
                "provider": PROVIDER.name,
                "reason": getattr(PROVIDER, "reason", ""),
            },
            ensure_ascii=False,
        )
    )


def make_upstream_client(*, timeout: float) -> httpx.AsyncClient:
    """상류용 HTTP 클라이언트. 테스트에서 이 함수를 바꿔치기한다."""
    return httpx.AsyncClient(timeout=timeout)


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/chat/completions")
async def chat_completions(request: Request) -> JSONResponse:
    payload: Dict[str, Any] = await request.json()
    caller = request.headers.get("X-LLM-Caller", "unknown")

    # 모듈 전역을 그때그때 읽는다. 테스트가 설정과 제공자를 함께 바꿔 끼운다.
    provider = PROVIDER
    settings = SETTINGS

    normalized, param_notes = provider.normalize_params(payload)
    if param_notes:
        # 이 스트림은 한 줄에 JSON 하나여야 한다. 평문으로 찍으면 계측 레코드를
        # 파싱하는 쪽이 이 줄에서 깨진다.
        logger.warning(
            json.dumps(
                {"event": "param_normalized", "caller": caller, "paramNotes": param_notes},
                ensure_ascii=False,
            )
        )

    started = time.monotonic()

    try:
        upstream_request = provider.build_request(normalized)
    except ProviderUnavailable as exc:
        # 상류로 나간 요청이 없다. 계측에는 그 사실이 그대로 남는다.
        _log_record(
            settings=settings,
            model=str(normalized.get("model", settings.model)),
            caller=caller,
            usage=RawUsage(),
            latency_ms=int((time.monotonic() - started) * 1000),
            attempts=0,
            outcome="failed",
            param_notes=param_notes,
            execution=facts_for(provider, None),
        )
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "type": "provider_unresolved",
                    "providerConfigured": provider.configured_name,
                    # 이 문자열에는 설정 이름과 리전만 들어간다(GC-7).
                    "detail": str(exc),
                }
            },
        )

    # 계측이 보는 모든 제공자 사실은 여기서 한 번 도출된다. 설정을 다시 읽지 않는다.
    execution = facts_for(provider, upstream_request)
    # 실제로 보낸 모델 ID. 호출자가 보낸 것이 아니라 상류로 나간 것이다.
    sent_model = str(upstream_request.body.get("model", settings.model))

    async with make_upstream_client(timeout=settings.timeout_seconds) as client:
        try:
            raw_body, attempts = await call_upstream(
                client,
                request=upstream_request,
                max_retries=settings.max_retries,
                sleep=asyncio.sleep,
            )
        except UpstreamError as exc:
            _log_record(
                settings=settings,
                model=sent_model,
                caller=caller,
                usage=RawUsage(),
                latency_ms=int((time.monotonic() - started) * 1000),
                attempts=exc.attempts,
                outcome="failed",
                param_notes=param_notes,
                execution=execution,
                upstream_status=exc.status,
            )
            # 상류 응답 본문을 그대로 흘리지 않는다. 키가 섞일 여지를 남기지 않는다(GC-7).
            return JSONResponse(
                status_code=502,
                content={
                    "error": {
                        "type": "upstream_error",
                        "upstreamStatus": exc.status,
                        "attempts": exc.attempts,
                    }
                },
            )

    body = provider.parse_response(raw_body)
    _log_record(
        settings=settings,
        model=sent_model,
        caller=caller,
        usage=provider.read_usage(body),
        latency_ms=int((time.monotonic() - started) * 1000),
        attempts=attempts,
        outcome="success" if attempts == 1 else "success_after_retry",
        param_notes=param_notes,
        execution=execution,
    )
    return JSONResponse(status_code=200, content=body)


def _log_record(**kwargs: Any) -> None:
    logger.info(json.dumps(build_record(**kwargs), ensure_ascii=False))
