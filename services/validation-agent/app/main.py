from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

from .agent import run_validation_agent
from .models import ValidationAgentRequest, ValidationAgentResponse
from .rabbit_worker import start_rabbit_worker_in_background


logger = logging.getLogger("validation_agent")
logging.basicConfig(
    level=os.environ.get("VALIDATION_AGENT_LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)


def _load_dotenv_if_present() -> None:
    if not load_dotenv:
        return
    env_file = Path(__file__).resolve().parents[1] / ".env"
    if env_file.is_file():
        load_dotenv(env_file, override=True)


_load_dotenv_if_present()

from .env_check import require_env

_required: list[str] = []
if os.environ.get("LLM_PROVIDER", "real") != "stub":
    _required.append("LLM_GATEWAY_BASE_URL")
require_env(_required)

app = FastAPI(
    title="BitComputer Validation Agent",
    version="0.1.0",
    description="DB Outbox 이벤트를 처리하는 LangGraph 기반 진료 데이터 검증 에이전트",
)


@app.on_event("startup")
def startup() -> None:
    if os.environ.get("VALIDATION_RABBITMQ_ENABLED", "true").lower() != "false":
        start_rabbit_worker_in_background()


@app.get("/")
def root() -> Dict[str, Any]:
    return {
        "service": "validation_agent",
        "health": "/health",
        "run_endpoint": "POST /api/agent/validation/run",
    }


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    return Response(status_code=204)


@app.get("/health")
def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "llm_gateway_configured": bool(os.environ.get("LLM_GATEWAY_BASE_URL")),
        "default_model": os.environ.get("LLM_MODEL", "openai.gpt-5.6-luna"),
        "prescription_agent": os.environ.get("PRESCRIPTION_AGENT_BASE_URL", "http://prescription-api:8001"),
        "rabbitmq_enabled": os.environ.get("VALIDATION_RABBITMQ_ENABLED", "true").lower() != "false",
    }


@app.post("/api/agent/validation/run", response_model=ValidationAgentResponse)
def run_validation(request: ValidationAgentRequest) -> ValidationAgentResponse:
    try:
        return run_validation_agent(request)
    except Exception as exc:  # noqa: BLE001 - API should return structured failure to Spring
        logger.exception("검증 에이전트 실행 실패 - eventId=%s", request.eventId)
        raise HTTPException(status_code=500, detail=f"validation agent failed: {exc}") from exc
