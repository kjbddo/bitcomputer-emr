#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Spring Boot Back-End ↔ LLM 게이트웨이 기반 진단서 소견 생성 FastAPI 서비스.

Spring은 MySQL에서 환자·진료 기록을 모은 뒤 이 서비스로 POST합니다.
응답: {"medicalCertificate": "...", "llmStatus": "real"|"stub"} — 진단서 소견 텍스트

prescription_api.py 와 동일한 구조로 작성됨. LLM 호출은 자체적으로 하지 않고
llm-gateway(services/llm-gateway) 를 경유한다(spec §3.1) — 자격증명은 게이트웨이만 갖는다.

실행:
    cd GraphDB/langchain_graph_qa
    pip install -r requirements.txt
    # 영상판독 Flask 서버(AI_BackEnd/app.py)와 포트 충돌을 피하려고 5001 사용.
    # Spring 의 application.properties 의 ai.certificate-agent.base-url 과 일치해야 한다.
    uvicorn certificate_api:app --host 0.0.0.0 --port 5001
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

from certificate_agent import SYSTEM_CERTIFICATE, build_certificate_agent_prompt
from llm_provider import resolve_provider, stub_certificate_response

logger = logging.getLogger("certificate_api")
logging.basicConfig(
    level=os.environ.get("CERTIFICATE_API_LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)


def _load_dotenv_if_present() -> None:
    if not load_dotenv:
        return
    env_file = SCRIPT_DIR / ".env"
    if env_file.is_file():
        load_dotenv(env_file)


_load_dotenv_if_present()

DEFAULT_MODEL = os.environ.get("LLM_MODEL", "openai.gpt-5.6-luna")


# ── Request / Response 스키마 ─────────────────────────────────────────────────

class DiseaseInfo(BaseModel):
    code: str = ""
    name: str = ""
    degree: str | None = None


class DiagnoseInfo(BaseModel):
    code: str = ""
    name: str = ""
    dose: int = 0
    time: int = 0
    days: int = 0


class CertificateGenerateRequest(BaseModel):
    """Spring → Python 요청 스키마.

    Spring의 CertificateAgentRequest 와 필드명이 1:1 로 매칭된다.
    """
    history_id: int
    certificate_type: str = Field(default="GENERAL", description="GENERAL 또는 MILITARY")
    patient_name: str = ""
    patient_age: int = 0
    patient_gender: str = ""
    entry_date: str = ""
    symptom_detail: str | None = None
    diagnosis_kind: str = Field(default="미선택", description="임상적 추정 또는 최종 진단")
    purpose: str = Field(default="", description="진단서 용도")
    diseases: list[DiseaseInfo] = Field(default_factory=list)
    diagnoses: list[DiagnoseInfo] = Field(default_factory=list)


class CertificateGenerateResponse(BaseModel):
    medicalCertificate: str
    # LLM 을 실제로 썼는지. 실행 경로에서 도출한다(spec §6.2).
    llmStatus: str = "real"


# ── FastAPI 앱 ─────────────────────────────────────────────────────────────────

app = FastAPI(
    title="BitComputer Certificate Generation Agent",
    version="0.1.0",
    description="LLM 게이트웨이 기반 진단서 소견 생성 서비스 (Spring Boot 연동용).",
)


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "llm_gateway_configured": bool(os.environ.get("LLM_GATEWAY_BASE_URL")),
        "default_model": DEFAULT_MODEL,
    }


def _invoke_gateway_text(system_prompt: str, user_prompt: str, model: str) -> str:
    """게이트웨이를 통해 진단서 소견 텍스트를 받는다.

    자격증명은 게이트웨이가 갖는다(spec §3.1). temperature 는 보내지 않는다 —
    luna 계약이며 게이트웨이가 어차피 제거한다(spec §5). ``model`` 은 호출자가
    실제로 payload 에 실릴 값을 명시적으로 넘긴다 — 여기서 다시 환경변수를
    읽으면 호출자의 trace 가 기록한 모델과 실제로 보낸 모델이 어긋날 수 있다.
    """
    base_url = os.environ.get("LLM_GATEWAY_BASE_URL")
    if not base_url:
        raise HTTPException(
            status_code=503,
            detail="LLM_GATEWAY_BASE_URL 이 설정되지 않았습니다.",
        )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    timeout = float(os.environ.get("LLM_TIMEOUT_SECONDS", "180"))
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers={"X-LLM-Caller": "certificate-api"},
                json=payload,
            )
            response.raise_for_status()
            return str(response.json()["choices"][0]["message"]["content"]).strip()
    except httpx.HTTPStatusError as exc:
        # exc.response.text 는 게이트웨이가 GC-7 에 맞춰 이미 상류 응답을 걷어낸
        # 구조화된 본문(예: {"error":{"type":"upstream_error","upstreamStatus":N,
        # "attempts":N}})이므로 로그·detail 에 그대로 실어도 안전하다. 요청 헤더나
        # Authorization 값은 여기서 절대 로그하지 않는다.
        body = exc.response.text[:500]
        logger.exception(
            "게이트웨이 호출 실패: status=%s body=%s", exc.response.status_code, body
        )
        detail = f"LLM 게이트웨이 호출 실패: status={exc.response.status_code}"
        try:
            error_body = exc.response.json()
        except ValueError:
            error_body = None
        upstream_info = error_body.get("error") if isinstance(error_body, dict) else None
        if isinstance(upstream_info, dict) and (
            "upstreamStatus" in upstream_info or "attempts" in upstream_info
        ):
            detail += (
                f" upstreamStatus={upstream_info.get('upstreamStatus')}"
                f" attempts={upstream_info.get('attempts')}"
            )
        else:
            detail += f" body={body}"
        raise HTTPException(status_code=502, detail=detail) from exc
    except Exception as exc:
        logger.exception("게이트웨이 호출 실패")
        raise HTTPException(status_code=502, detail=f"LLM 게이트웨이 호출 실패: {exc}") from exc


@app.post("/api/ai/document/generate", response_model=CertificateGenerateResponse)
def generate_certificate(req: CertificateGenerateRequest) -> CertificateGenerateResponse:
    user_msg = build_certificate_agent_prompt(
        patient_gender=req.patient_gender,
        patient_age=req.patient_age,
        entry_date=req.entry_date,
        symptom_detail=req.symptom_detail,
        diagnosis_kind=req.diagnosis_kind,
        purpose=req.purpose,
        diseases=[d.model_dump() for d in req.diseases],
        diagnoses=[d.model_dump() for d in req.diagnoses],
        certificate_type=req.certificate_type,
    )

    logger.info(
        "진단서 생성 요청 - history_id=%d, type=%s",
        req.history_id,
        req.certificate_type,
    )

    if resolve_provider() == "stub":
        certificate = stub_certificate_response(req)
        llm_status = "stub"
    else:
        wire_model = os.environ.get("LLM_MODEL", "openai.gpt-5.6-luna")
        certificate = _invoke_gateway_text(SYSTEM_CERTIFICATE, user_msg, wire_model)
        llm_status = "real"

    logger.info(
        "진단서 생성 완료 - history_id=%d, length=%d", req.history_id, len(certificate)
    )
    return CertificateGenerateResponse(medicalCertificate=certificate, llmStatus=llm_status)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "certificate_api:app",
        host=os.environ.get("CERTIFICATE_API_HOST", "0.0.0.0"),
        port=int(os.environ.get("CERTIFICATE_API_PORT", "5001")),
        reload=bool(os.environ.get("CERTIFICATE_API_RELOAD", "")),
    )
