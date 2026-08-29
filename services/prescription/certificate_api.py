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
from typing import Any, Dict, Literal, Optional

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
from certificate_verification import verify_certificate, verify_certificate_nli
from llm_provider import resolve_provider, stub_certificate_response
from verification_contract import VerificationResult, aggregate_status

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
        # 개발 환경에서 이미 export 된 예전 값(예: LLM_GATEWAY_BASE_URL)이 남아 있으면
        # .env 값이 무시되는 혼선이 잦다. .env 를 "로컬 단일 진실"로 취급하기 위해
        # override=True 로 로드한다 — prescription_api.py 와 동일한 정책(최종 리뷰).
        load_dotenv(env_file, override=True)


_load_dotenv_if_present()


# B(NLI) 플래그. 기본 off — spec §8, Task 11. 켜지 않으면 모든 요청에
# 게이트웨이 호출이 하나씩 더 붙는 비용·지연이 조용히 생기지 않는다.
# off | on
NLI_ENABLED = os.environ.get("LLM_VERIFICATION_NLI", "off").strip().lower() == "on"
# NLI 2차 호출 단독 예산. 재시도 없음. 게이트웨이 자체 예산(136.5s)에
# 이 값이 더해져도 호출자 타임아웃(180s)을 넘지 않아야 한다(spec §8.4).
NLI_TIMEOUT_SECONDS = float(os.environ.get("LLM_VERIFICATION_NLI_TIMEOUT_SECONDS", "30"))


_ZERO_WIDTH_CHARS = "\u200b\u200c\u200d\ufeff"


def _strip_zero_width(text: str) -> str:
    """블랭크 판정 전에 폭이 0인 문자를 제거한다.

    M6: U+200B(zero-width space) 하나만 있는 content 는 str.strip() 을 통과해
    llmStatus="real" 인 "진짜" 진단서로 새어나간다. blank 판정에만 쓰고
    반환값 자체는 건드리지 않는다 — 본문 중간에 낀 zero-width 문자까지
    지우는 건 이 수정의 범위 밖이다."""
    for ch in _ZERO_WIDTH_CHARS:
        text = text.replace(ch, "")
    return text


def _default_llm_model() -> str:
    """LLM_MODEL 환경변수를 매 호출 시점에 읽는다.

    N12: 이전에는 import 시점 상수(DEFAULT_MODEL)와 호출 시점 재조회가
    각각 따로 os.environ.get() 을 불렀다. import 시점 값은 프로세스가 뜬
    이후 환경변수가 바뀌어도 갱신되지 않으므로, /health 가 보고하는
    default_model 이 실제로 게이트웨이에 실리는 model 과 어긋날 수
    있었다. 단일 함수로 합쳐 두 지점이 항상 같은 값을 보게 한다."""
    return os.environ.get("LLM_MODEL", "openai.gpt-5.6-luna")


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
    # LLM 을 실제로 썼는지. engineStatus 와 달리 실행 경로에서 도출한다(spec §6.2).
    # 기본값을 두지 않는다 — 생성 시 값을 빠뜨리면 "모델이 실제로 판단했다"는
    # 거짓 신호를 조용히 내보내게 된다. prescription_api.PrescriptionRecommendResponse.llmStatus
    # 와 동일한 강도로 맞춘다.
    llmStatus: Literal["real", "stub"]
    verification: Optional[Dict[str, Any]] = None


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
        "default_model": _default_llm_model(),
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
    # LLM_TIMEOUT_SECONDS 가 아니다 — 그 이름은 게이트웨이의 1회 시도당 타임아웃
    # (services/llm-gateway/app/config.py) 이 이미 쓰고 있다. infra/.env 는
    # 한 파일을 공유하고 이 파일은 override=True 로 로드하므로, 이름이 같으면
    # 운영자가 "게이트웨이 타임아웃"을 의도해 값을 바꿔도 이 호출자의 총
    # 대기시간까지 함께 바뀌어 재시도가 전부 무의미해진다(최종 리뷰 IMPORTANT).
    timeout_raw = os.environ.get("LLM_GATEWAY_TIMEOUT_SECONDS", "180")
    try:
        timeout = float(timeout_raw)
    except ValueError as exc:
        # certificate_api.py:143(구) — try 밖에서 ValueError 가 그대로 터지면
        # 트레이스백이 노출된 500 이 나간다. 잘못된 설정값도 "실패 계약"
        # 안에서 다뤄져야 한다(GC-2).
        logger.exception("LLM_GATEWAY_TIMEOUT_SECONDS 파싱 실패: %r", timeout_raw)
        raise HTTPException(
            status_code=503,
            detail=f"LLM_GATEWAY_TIMEOUT_SECONDS 설정이 올바르지 않습니다: {timeout_raw!r}",
        ) from exc
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers={"X-LLM-Caller": "certificate-api"},
                json=payload,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            # M6: U+200B 등 폭이 0인 문자만 있는 문자열은 str.strip() 을 그대로
            # 통과한다 — blank 판정 전에 zero-width 문자를 먼저 지운다. 반환값
            # 자체(content.strip())는 건드리지 않는다.
            if not isinstance(content, str) or not _strip_zero_width(content).strip():
                # CRITICAL C1: 200 이지만 형식이 깨진 본문(content: null/""/비문자열)을
                # str() 로 뭉개서 반환하면 "None" 같은 지어낸 문자열이 llmStatus="real" 인
                # 진짜 진단서 소견으로 통과한다(GC-2). 여기서 명시적으로 거부해
                # 아래 ``except Exception`` 분기(502, 사유 보존)로 떨어뜨린다.
                # M2: content 가 대용량(예: 200KB dict)이면 repr(content) 를 그대로
                # 실을 경우 502 detail·로그가 무한정 커진다 — 형제 분기인
                # HTTPStatusError 의 body[:500] 과 같은 정신으로 잘라낸다.
                raise ValueError(
                    f"게이트웨이가 빈 본문을 돌려주었습니다: content={repr(content)[:200]}"
                )
            return content.strip()
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


NLI_SYSTEM_PROMPT = (
    "당신은 자연어추론(NLI) 판정기입니다. 전제(premise)와 가설(hypothesis)이 "
    "주어지면 가설이 전제로부터 함의되는지 판단해, 다음 세 단어 중 정확히 "
    "하나만 출력하세요: ENTAILMENT, CONTRADICTION, NEUTRAL. 다른 말은 절대 "
    "덧붙이지 마세요."
)


def _certificate_premise(req: Any) -> str:
    """NLI 판정에 쓸 premise 문자열을 diseases + diagnoses 에서 만든다.

    certificate_verification.verify_certificate() 가 known_codes/known_terms 를
    뽑는 것과 같은 소스(diseases + diagnoses)에서 만든다 — 두 검사가 서로
    다른 premise 를 보면, 결정론적 검사는 "근거 있음"이라 하는데 NLI 는
    "근거 없음"이라 하는 모순이 생긴다.
    """
    entries = list(getattr(req, "diseases", None) or []) + list(getattr(req, "diagnoses", None) or [])
    parts: list[str] = []
    for entry in entries:
        code = str(getattr(entry, "code", "") or "").strip()
        name = str(getattr(entry, "name", "") or "").strip()
        if code and name:
            parts.append(f"{name}({code})")
        elif name or code:
            parts.append(name or code)
    return ", ".join(parts)


def _call_certificate_nli(premise: str, hypothesis: str, timeout: float) -> str:
    """NLI 2차 호출. `_invoke_gateway_text` 와 의도적으로 분리한 별도 함수다.

    - 헤더가 다르다: X-LLM-Caller: certificate-api-nli. 계측이 본 기능 호출
      (certificate-api)과 섞이지 않아야 B 를 기본으로 켤지 판단할 비용·지연
      숫자를 얻을 수 있다(spec §8.2, §11).
    - 재시도하지 않는다: 게이트웨이 자체 예산(3회 시도+backoff ≈ 136.5s)에
      NLI 호출까지 재시도로 늘어나면 호출자 타임아웃(180s) 사다리가
      뒤집힌다(spec §8.4). 그래서 httpx.Client 로 한 번만 호출하고 재시도
      루프를 두지 않는다 — 실패하면 그대로 예외를 던진다.
    - `_invoke_gateway_text` 를 재사용하지 않는 이유: 그 함수는 실패를
      HTTPException(502/503) 으로 바꿔 본 요청(진단서 생성) 흐름을 끊는
      용도로 설계됐다. NLI 호출은 부가 검증일 뿐이라 그 실패가 본 응답을
      끊으면 GC-4 를 어긴다. 그래서 여기서는 예외를 그대로 전파시키고,
      그걸 skipped 로 접수하는 책임은 verify_certificate_nli 의 try/except
      쪽에 맡긴다(GC-1: I/O 는 주입, 판정 로직은 순수 함수).
    - `timeout` 을 인자로 받는다 — 모듈 상수 NLI_TIMEOUT_SECONDS 를 여기서
      직접 읽지 않는다. 예산은 문장별이 아니라 요청 전체에 대한 것이라,
      `verify_certificate_nli` 가 매 문장 호출 전에 "남은" 시간으로 잘라
      넘긴다(CRITICAL 후속 리뷰). 이 함수가 상수를 다시 읽으면 그 절삭이
      여기서 무시되고 매 호출이 다시 전체 예산을 받는 것과 같아진다.
    """
    base_url = os.environ.get("LLM_GATEWAY_BASE_URL")
    if not base_url:
        raise RuntimeError("LLM_GATEWAY_BASE_URL 이 설정되지 않았습니다.")
    payload = {
        "model": _default_llm_model(),
        "messages": [
            {"role": "system", "content": NLI_SYSTEM_PROMPT},
            {"role": "user", "content": f"전제: {premise}\n가설: {hypothesis}"},
        ],
    }
    with httpx.Client(timeout=timeout) as client:
        response = client.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers={"X-LLM-Caller": "certificate-api-nli"},
            json=payload,
        )
        response.raise_for_status()
        return str(response.json()["choices"][0]["message"]["content"])


def _safe_verify_certificate(req: Any, text: str) -> Dict[str, Any]:
    """검증을 돌리되 본 응답을 실패시키지 않는다(GC-4)."""
    try:
        result = verify_certificate(
            diseases=getattr(req, "diseases", None) or [],
            diagnoses=getattr(req, "diagnoses", None) or [],
            text=text,
        )
        checks = list(result.checks)
        if NLI_ENABLED:
            # NLI_ENABLED 는 이 검사가 도는지만 결정한다 — outcome 은 항상
            # call_llm(=_call_certificate_nli) 의 실행 결과에서만 나온다
            # (GC-5: 상태는 실행 경로에서 나오지 설정에서 도출되지 않는다).
            checks.extend(verify_certificate_nli(
                premise=_certificate_premise(req),
                text=text,
                call_llm=_call_certificate_nli,
                # CRITICAL 리뷰: NLI_TIMEOUT_SECONDS 는 이 호출 전체의 예산이지
                # 문장마다 새로 지급되는 예산이 아니다. 여기서 명시적으로
                # 넘기지 않으면 verify_certificate_nli 의 함수 기본값만 쓰이게
                # 되어, 문장이 여럿인 소견에서 예산이 문장 수만큼 불어난다.
                budget_seconds=NLI_TIMEOUT_SECONDS,
            ))
        return VerificationResult(
            status=aggregate_status(checks),
            checks=checks,
            skippedReason=result.skippedReason,
        ).to_dict()
    except Exception as exc:  # noqa: BLE001
        logger.exception("진단서 검증 실패, skipped 로 처리")
        return {
            "status": "skipped",
            "checks": [],
            "skippedReason": f"검증기 예외: {type(exc).__name__}",
        }


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
        wire_model = _default_llm_model()
        certificate = _invoke_gateway_text(SYSTEM_CERTIFICATE, user_msg, wire_model)
        llm_status = "real"

    logger.info(
        "진단서 생성 완료 - history_id=%d, length=%d", req.history_id, len(certificate)
    )
    return CertificateGenerateResponse(
        medicalCertificate=certificate,
        llmStatus=llm_status,
        verification=_safe_verify_certificate(req, certificate),
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "certificate_api:app",
        host=os.environ.get("CERTIFICATE_API_HOST", "0.0.0.0"),
        port=int(os.environ.get("CERTIFICATE_API_PORT", "5001")),
        reload=bool(os.environ.get("CERTIFICATE_API_RELOAD", "")),
    )
