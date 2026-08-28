"""LLM 게이트웨이.

프로덕션 서비스의 LLM 호출을 한 곳으로 모은다. 도메인 스키마를 모르며(GC-1),
파라미터 계약·재시도·계측만 소유한다. AWS 자격증명은 이 서비스에만 있다.
"""
from __future__ import annotations

import asyncio
import json
import logging
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
        logger.warning(
            "파라미터 정규화: caller=%s notes=%s", caller, ",".join(param_notes)
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
