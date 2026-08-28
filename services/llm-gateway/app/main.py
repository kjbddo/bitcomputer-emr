"""LLM 게이트웨이.

프로덕션 서비스의 LLM 호출을 한 곳으로 모은다. 도메인 스키마를 모르며(GC-1),
파라미터 계약·재시도·계측만 소유한다. AWS 자격증명은 이 서비스에만 있다.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from typing import Any, Dict

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.config import Settings, load_settings
from app.metering import build_record
from app.params import normalize_params
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

app = FastAPI(title="LLM Gateway", version="0.1.0")

SETTINGS: Settings = load_settings()


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

    normalized, param_notes = normalize_params(
        payload, default_reasoning_effort=SETTINGS.reasoning_effort
    )
    if param_notes:
        # 이 스트림은 한 줄에 JSON 하나여야 한다. 평문으로 찍으면 계측 레코드를
        # 파싱하는 쪽이 이 줄에서 깨진다.
        logger.warning(
            json.dumps(
                {"event": "param_normalized", "caller": caller, "paramNotes": param_notes},
                ensure_ascii=False,
            )
        )

    url = f"{SETTINGS.upstream_base_url}/chat/completions"
    started = time.monotonic()

    async with make_upstream_client(timeout=SETTINGS.timeout_seconds) as client:
        try:
            body, attempts = await call_upstream(
                client,
                url=url,
                api_key=SETTINGS.api_key,
                payload=normalized,
                max_retries=SETTINGS.max_retries,
                sleep=asyncio.sleep,
            )
        except UpstreamError as exc:
            latency_ms = int((time.monotonic() - started) * 1000)
            _log_record(
                model=str(normalized.get("model", SETTINGS.model)),
                caller=caller,
                usage=None,
                latency_ms=latency_ms,
                attempts=exc.attempts,
                outcome="failed",
                param_notes=param_notes,
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

    latency_ms = int((time.monotonic() - started) * 1000)
    _log_record(
        model=str(normalized.get("model", SETTINGS.model)),
        caller=caller,
        usage=body.get("usage"),
        latency_ms=latency_ms,
        attempts=attempts,
        outcome="success" if attempts == 1 else "success_after_retry",
        param_notes=param_notes,
    )
    return JSONResponse(status_code=200, content=body)


def _log_record(**kwargs: Any) -> None:
    record = build_record(settings=SETTINGS, **kwargs)
    logger.info(json.dumps(record, ensure_ascii=False))
