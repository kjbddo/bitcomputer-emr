#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Spring Boot Back-End ↔ prescription_agent 를 연결하는 FastAPI 서비스.

Spring 은 MySQL 에서 환자·진료 기록을 모은 뒤 이 서비스로 POST 합니다.
- `fetch_top_rx_from_arango` 가 true 이고 클라이언트가 보낸 `top_rx` 가 비어 있으면
  ArangoDB(visits → order_lines → prescription_masters) 에서 직접 처방 라인을 채웁니다.
- `disease_codes`(예: E11)가 있고 `fetch_cohort_rx_from_arango` 가 true 이면,
  visit_has_diagnosis 로 해당 상병이 붙은 방문들의 처방을 빈도 집계해 `similar_outcomes` 문구와
  `top_rx` 후보 행(코호트)에 병합합니다.
- 그 외에는 Spring 이 만들어 준 feature 를 그대로 LLM 프롬프트에 싣습니다.
- 응답은 ``prescription_agent.parse_prescriptions_llm_response`` 가 검증한
  Required JSON Format `{ "prescriptions": [...] }` 입니다.

실행:
    cd GraphDB/langchain_graph_qa
    pip install -r requirements.txt
    uvicorn prescription_api:app --host 0.0.0.0 --port 8001
"""

import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Union

import httpx
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

from llm_provider import resolve_provider, stub_prescription_response

from verification import verify_prescriptions

from prescription_agent import (
    build_prescription_agent_prompt,
    parse_prescriptions_llm_response,
)
from run_prescription_agent import (
    SYSTEM_PRESCRIPTION,
    cohort_stat_rows_to_top_rx_lines,
    fetch_cohort_prescriptions_by_diagnosis_codes,
    fetch_confidence_scores_by_diagnosis_codes,
    fetch_top_rx_from_arango,
    format_cohort_similar_outcomes_summary,
)

logger = logging.getLogger("prescription_api")
logging.basicConfig(
    level=os.environ.get("PRESCRIPTION_API_LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)


def _load_dotenv_if_present() -> None:
    if not load_dotenv:
        return
    env_file = SCRIPT_DIR / ".env"
    if env_file.is_file():
        # 개발 환경에서 이미 export 된 예전 값(예: LLM_GATEWAY_BASE_URL)이 남아 있으면
        # .env 값이 무시되는 혼선이 잦다. .env 를 "로컬 단일 진실"로 취급하기 위해
        # override=True 로 로드한다 — certificate_api.py 와 동일한 정책(최종 리뷰).
        load_dotenv(env_file, override=True)


_load_dotenv_if_present()


_ZERO_WIDTH_CHARS = "​‌‍﻿"


def _strip_zero_width(text: str) -> str:
    """블랭크 판정 전에 폭이 0인 문자를 제거한다.

    certificate_api.py 의 동일 함수와 같은 이유: U+200B(zero-width space)
    하나만 있는 content 는 str.strip() 을 통과해 llmStatus="real" 인 "진짜"
    처방 추천으로 새어나간다. blank 판정에만 쓰고 반환값 자체는 건드리지
    않는다(최종 리뷰 IMPORTANT 2 — 이 가드는 Task 8 에서 certificate_api.py 에만
    들어가고 이 파일에는 이관되지 않았다).
    """
    for ch in _ZERO_WIDTH_CHARS:
        text = text.replace(ch, "")
    return text


def _default_llm_model() -> str:
    """LLM_MODEL 환경변수를 매 호출 시점에 읽는다.

    certificate_api.py 의 동일 함수와 같은 이유: import 시점 상수(구 DEFAULT_MODEL)와
    호출 시점 재조회가 각각 따로 os.environ.get() 을 부르면, import 시점 값은
    프로세스가 뜬 이후 환경변수가 바뀌어도 갱신되지 않아 /health 가 보고하는
    default_model 이 실제로 게이트웨이에 실리는 model 과 어긋날 수 있다(최종 리뷰
    IMPORTANT 2). 단일 함수로 합쳐 두 지점이 항상 같은 값을 보게 한다.
    """
    return os.environ.get("LLM_MODEL", "openai.gpt-5.6-luna")


class PrescriptionRecommendRequest(BaseModel):
    """Spring → Python 요청 스키마.

    Spring 은 MySQL 의 History / HistoryDiagnose / HistoryDisease / Patient 를 읽어
    아래 필드로 변환해서 보냅니다. top_rx 가 비어 있으면 `fetch_top_rx_from_arango`
    를 true 로 주어 Arango 에서 보강할 수 있습니다.
    """

    patient_id: str = Field(..., description="Arango 에서 visit·내원번호 매칭에 쓰는 문자열")
    # Python 3.9: Pydantic v2 가 PEP 604 (`|`) 평가에 실패할 수 있어 Union 사용
    symptoms: Union[str, List[Any], Dict[str, Any]] = Field("", description="현재 증상")
    history: Union[str, List[Any], Dict[str, Any]] = Field("", description="과거 진료/특이사항")
    top_rx: Optional[Union[List[Any], str]] = Field(default=None, description="방문의 처방 라인")
    similar_outcomes: Optional[Union[str, List[Any], Dict[str, Any]]] = Field("", description="유사 환자 요약")
    mention_links: Optional[List[Any]] = None
    clinician_question: Optional[str] = None
    # Spring 기본(ai.prescription-agent.fetch-top-rx-from-arango=true)과 맞춤.
    # 요청 JSON 에 키가 빠져도 Arango 보강을 시도한다.
    fetch_top_rx_from_arango: bool = Field(
        default=True,
        description="true 이고 top_rx 가 비어 있으면 patient_id 로 Arango 조회",
    )
    arango_top_rx_limit: int = Field(default=80, ge=1, le=500)
    disease_codes: Optional[List[str]] = Field(
        default=None,
        description="상병 코드 목록(E11 등). 있으면 Arango에서 코호트 빈도 처방을 조회해 top_rx·similar_outcomes 에 반영",
    )
    fetch_cohort_rx_from_arango: bool = Field(
        default=True,
        description="true 이고 disease_codes 가 비어 있지 않으면 상병별 코호트 처방 통계를 조회",
    )
    arango_cohort_rx_limit: int = Field(default=40, ge=1, le=500)
    model: Optional[str] = None
    temperature: Optional[float] = None


class PrescriptionItem(BaseModel):
    rank: int
    name: str
    prescription_code: str
    dosage: str
    reason: str
    confidence_score: Optional[float] = None


class PrescriptionRecommendResponse(BaseModel):
    prescriptions: List[PrescriptionItem]
    used_arango_top_rx: bool = False
    arango_top_rx_count: int = 0
    used_cohort_rx: bool = False
    cohort_rx_count: int = 0
    toolTrace: List[Dict[str, Any]] = Field(default_factory=list)
    engineStatus: str = "real"
    # LLM 을 실제로 썼는지. engineStatus 와 달리 실행 경로에서 도출한다(spec §6.2).
    # 기본값을 두지 않는다 — 생성 시 값을 빠뜨리면 "모델이 실제로 판단했다"는
    # 거짓 신호를 조용히 내보내게 된다(MINOR 5).
    llmStatus: Literal["real", "stub"]
    # 출력이 조회 결과로 추적되는지. llmStatus 와 다른 축이다 —
    # llmStatus 는 "모델이 돌았나", 이건 "돈 결과에 근거가 있나"다(spec §7.1).
    verification: Optional[Dict[str, Any]] = None


class PrescriptionFeedbackItem(BaseModel):
    rank: int
    prescription_id: Optional[int] = None
    prescription_code: str
    prescription_name: str
    confidence_score: Optional[float] = None
    reason: Optional[str] = None
    status: str


class PrescriptionFeedbackRequest(BaseModel):
    history_id: int
    history_diagnose_id: Optional[int] = None
    feedback_items: List[PrescriptionFeedbackItem]


class PrescriptionFeedbackResponse(BaseModel):
    saved: int
    edge_collection: str


from env_check import require_env

_required = ["ARANGO_PASSWORD"]
if os.environ.get("LLM_PROVIDER", "real") != "stub":
    _required.append("LLM_GATEWAY_BASE_URL")
require_env(_required)

app = FastAPI(
    title="BitComputer Prescription Agent",
    version="0.1.0",
    description="ArangoDB 그래프 + LLM 게이트웨이 기반 처방 추천 에이전트 (Spring Boot 연동용).",
)

_ARANGO_HISTORY_VTX = "recommendation_histories"
_ARANGO_FALLBACK_RX_VTX = "recommendation_prescriptions"
_ARANGO_RECOMMENDED_EDGE = "history_recommended_prescription"


@app.get("/")
def root() -> Dict[str, Any]:
    """브라우저로 루트만 열 때 404로 오해하지 않도록 안내."""
    return {
        "service": "prescription_api",
        "message": "Spring에서 호출하는 처방 추천 API입니다. 웹 화면 URL이 아닙니다.",
        "health": "/health",
        "openapi_docs": "/docs",
        "recommend_endpoint": "POST /api/agent/prescription/recommend",
    }


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    return Response(status_code=204)


@app.get("/health")
def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "llm_gateway_configured": bool(os.environ.get("LLM_GATEWAY_BASE_URL")),
        "default_model": _default_llm_model(),
        "arangodb_expected": (
            f"{os.environ.get('ARANGO_HOST', '127.0.0.1')}:"
            f"{os.environ.get('ARANGO_PORT', '8529')} "
            "(optional; cohort/top_rx graph queries skip if down)"
        ),
    }


def _normalize_disease_codes(raw: Optional[List[str]]) -> List[str]:
    if not raw:
        return []
    return [str(c).strip() for c in raw if c is not None and str(c).strip()]


def _merge_top_rx_with_cohort(
    base: Any,
    cohort_lines: List[Dict[str, Any]],
) -> List[Any]:
    """환자 방문 처방 뒤에 코호트 후보를 붙인다(처방코드 중복은 스킵)."""
    base_list: List[Any] = []
    if isinstance(base, list):
        base_list = list(base)
    seen_codes: set[str] = set()
    for row in base_list:
        if isinstance(row, dict):
            c = row.get("prescription_code")
            if c is None:
                c = row.get("처방코드")
            if c is not None and str(c).strip():
                seen_codes.add(str(c).strip())
    out = list(base_list)
    for row in cohort_lines:
        c = row.get("prescription_code") if isinstance(row, dict) else None
        if c is None and isinstance(row, dict):
            c = row.get("처방코드")
        key = str(c).strip() if c is not None else ""
        if key and key in seen_codes:
            continue
        if key:
            seen_codes.add(key)
        out.append(row)
    return out


def _combine_similar_outcomes(base: Any, cohort_summary: str) -> str:
    parts: List[str] = []
    if isinstance(base, str) and base.strip():
        parts.append(base.strip())
    elif base not in (None, "", []):
        parts.append(str(base).strip())
    if cohort_summary.strip():
        parts.append(cohort_summary.strip())
    return "\n\n".join(parts) if parts else ""


def _is_empty_top_rx(top_rx: Any) -> bool:
    if top_rx is None:
        return True
    if isinstance(top_rx, str):
        return not top_rx.strip()
    if isinstance(top_rx, (list, tuple, dict)):
        return len(top_rx) == 0
    return False


def _safe_key_part(raw: Any, fallback: str) -> str:
    text = str(raw).strip() if raw is not None else ""
    if not text:
        text = fallback
    return "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in text)


def _get_arango_db():
    from run_graph_qa import connect_arango, load_arango_config

    cfg = load_arango_config()
    return connect_arango(cfg)


def _invoke_gateway_json(system_prompt: str, user_prompt: str, model: str) -> str:
    """게이트웨이를 통해 JSON 응답을 받는다.

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
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    # LLM_TIMEOUT_SECONDS 가 아니다 — 그 이름은 게이트웨이의 1회 시도당 타임아웃
    # (services/llm-gateway/app/config.py) 이 이미 쓰고 있다. infra/.env 는 한
    # 파일을 공유하고 이 파일은 override=True 로 로드하므로, 이름이 같으면
    # 운영자가 "게이트웨이 타임아웃"을 의도해 값을 바꿔도 이 호출자의 총
    # 대기시간까지 함께 바뀌어 재시도가 전부 무의미해진다(최종 리뷰 IMPORTANT).
    timeout_raw = os.environ.get("LLM_GATEWAY_TIMEOUT_SECONDS", "180")
    try:
        timeout = float(timeout_raw)
    except ValueError as exc:
        # 최종 리뷰 IMPORTANT 2: try 밖에서 ValueError 가 그대로 터지면
        # 트레이스백이 노출된 500 이 나간다. certificate_api.py 는 Task 8 에서
        # 이 가드를 받았지만 이 파일은 복사 당시(같은 디렉터리, 같은 빌드
        # 컨텍스트) 받지 못했다. 잘못된 설정값도 "실패 계약" 안에서 다뤄져야
        # 한다(GC-2).
        logger.exception("LLM_GATEWAY_TIMEOUT_SECONDS 파싱 실패: %r", timeout_raw)
        raise HTTPException(
            status_code=503,
            detail=f"LLM_GATEWAY_TIMEOUT_SECONDS 설정이 올바르지 않습니다: {timeout_raw!r}",
        ) from exc
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers={"X-LLM-Caller": "prescription-api"},
                json=payload,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            # 최종 리뷰 IMPORTANT 2: 200 이지만 형식이 깨진 본문(content: null/""/
            # 비문자열)을 str() 로 뭉개서 반환하면 "None" 같은 지어낸 문자열이
            # llmStatus="real" 인 진짜 처방 추천으로 통과한다(GC-2). certificate_api.py
            # 는 Task 8 에서 이 가드를 받았다 — 여기서도 같은 검사를 적용한다.
            # zero-width 문자만 있는 content 도 blank 판정 전에 걸러낸다.
            if not isinstance(content, str) or not _strip_zero_width(content).strip():
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


def _ensure_feedback_graph_collections(db: Any) -> None:
    if not db.has_collection(_ARANGO_HISTORY_VTX):
        db.create_collection(_ARANGO_HISTORY_VTX)
    if not db.has_collection(_ARANGO_FALLBACK_RX_VTX):
        db.create_collection(_ARANGO_FALLBACK_RX_VTX)
    if not db.has_collection(_ARANGO_RECOMMENDED_EDGE):
        db.create_collection(_ARANGO_RECOMMENDED_EDGE, edge=True)


def _safe_verify(*, candidates: Any, items: Any) -> Dict[str, Any]:
    """검증을 돌리되 절대 본 응답을 실패시키지 않는다(GC-4).

    검증기에서 예외가 나면 skipped 로 흡수한다. 검증이 실패했는데 passed 로
    떨어지면 검증층이 있는 이유가 사라지므로, 실패는 반드시 skipped 다.
    """
    try:
        return verify_prescriptions(candidates=candidates, items=items).to_dict()
    except Exception as exc:  # noqa: BLE001
        logger.exception("처방 검증 실패, skipped 로 처리")
        return {
            "status": "skipped",
            "checks": [],
            "skippedReason": f"검증기 예외: {type(exc).__name__}",
        }


@app.post(
    "/api/agent/prescription/recommend",
    response_model=PrescriptionRecommendResponse,
)
def recommend(
    req: PrescriptionRecommendRequest,
    x_prescription_eval_trace: Optional[str] = Header(default=None),
) -> PrescriptionRecommendResponse:
    effective_top_rx: Any = req.top_rx
    used_arango = False
    arango_count = 0
    used_cohort = False
    cohort_count = 0
    eval_trace_enabled = os.environ.get("PRESCRIPTION_EVAL_TRACE_ENABLED", "").lower() in {
        "1",
        "true",
        "yes",
        "on",
    } or str(x_prescription_eval_trace or "").lower() in {"1", "true", "yes", "on"}
    tool_trace: List[Dict[str, Any]] = []

    def trace_tool(tool: str, called: bool, **payload: Any) -> None:
        if not eval_trace_enabled:
            return
        tool_trace.append({"tool": tool, "called": called, **payload})

    dx_codes = _normalize_disease_codes(req.disease_codes)

    _tr_len = len(req.top_rx) if isinstance(req.top_rx, list) else ("str" if isinstance(req.top_rx, str) else "?")
    logger.info(
        "recommend: patient_id=%r fetch_top_rx_from_arango=%s top_rx=%s disease_codes=%s",
        req.patient_id,
        req.fetch_top_rx_from_arango,
        _tr_len,
        dx_codes,
    )

    # confidence_score 는 LLM 출력에 없으므로, Arango co-occurrence 기반으로 별도 계산한다.
    w_freq = float(os.environ.get("CONFIDENCE_W_FREQ", "0.7"))
    w_sim = float(os.environ.get("CONFIDENCE_W_SIM", "0.3"))
    accepted_boost = float(os.environ.get("CONFIDENCE_ACCEPTED_BOOST", "0.15"))
    rejected_penalty = float(os.environ.get("CONFIDENCE_REJECTED_PENALTY", "0.20"))
    missed_boost = float(os.environ.get("CONFIDENCE_MISSED_BOOST", "0.05"))
    feedback_smoothing = float(os.environ.get("CONFIDENCE_FEEDBACK_SMOOTHING", "5.0"))
    confidence_by_code: dict[str, float] = {}
    if dx_codes:
        try:
            # NOTE: confidence AQL이 상위 N개만 반환하므로, LLM이 고른 코드가 누락되지 않도록 넉넉히 조회한다.
            confidence_rows = fetch_confidence_scores_by_diagnosis_codes(
                dx_codes,
                limit=int(os.environ.get("CONFIDENCE_LIMIT", str(max(5000, req.arango_cohort_rx_limit * 50)))),
                w_freq=w_freq,
                w_sim=w_sim,
                accepted_boost=accepted_boost,
                rejected_penalty=rejected_penalty,
                missed_boost=missed_boost,
                feedback_smoothing=feedback_smoothing,
            )
            confidence_by_code = {
                str(r.get("prescription_code")): float(r.get("confidence_score") or 0.0)
                for r in (confidence_rows or [])
                if r.get("prescription_code") is not None
            }
            trace_tool(
                "confidence_scores",
                True,
                status="success",
                input={"disease_codes": dx_codes},
                rowCount=len(confidence_rows or []),
            )
        except Exception as exc:
            logger.warning("confidence_score 계산 실패: %s", exc)
            trace_tool(
                "confidence_scores",
                True,
                status="failed",
                input={"disease_codes": dx_codes},
                error=str(exc),
            )
    else:
        trace_tool(
            "confidence_scores",
            False,
            reason="disease_codes is empty",
        )

    if req.fetch_top_rx_from_arango and _is_empty_top_rx(effective_top_rx):
        try:
            rows = fetch_top_rx_from_arango(
                req.patient_id, limit=req.arango_top_rx_limit
            )
        except Exception as exc:  # Arango 연결/AQL 실패는 500 이 아니라 경고 후 원본 유지
            logger.warning(
                "Arango top_rx 조회 실패 (patient_id=%r): %s", req.patient_id, exc
            )
            rows = []
            trace_tool(
                "top_rx_from_arango",
                True,
                status="failed",
                input={"patient_id": req.patient_id, "limit": req.arango_top_rx_limit},
                error=str(exc),
            )
        if rows:
            effective_top_rx = rows
            used_arango = True
            arango_count = len(rows)
            trace_tool(
                "top_rx_from_arango",
                True,
                status="success",
                input={"patient_id": req.patient_id, "limit": req.arango_top_rx_limit},
                rowCount=len(rows),
            )
            logger.info(
                "Arango 에서 top_rx %d 건 로드 (patient_id=%r)", arango_count, req.patient_id
            )
        else:
            if eval_trace_enabled and not any(
                row.get("tool") == "top_rx_from_arango" and row.get("status") == "failed"
                for row in tool_trace
            ):
                trace_tool(
                    "top_rx_from_arango",
                    True,
                    status="empty",
                    input={"patient_id": req.patient_id, "limit": req.arango_top_rx_limit},
                    rowCount=0,
                )
            logger.info(
                "Arango 에서 top_rx 를 찾지 못함 (patient_id=%r). 요청의 top_rx 를 그대로 사용.",
                req.patient_id,
            )
    else:
        trace_tool(
            "top_rx_from_arango",
            False,
            reason=(
                "fetch_top_rx_from_arango=false"
                if not req.fetch_top_rx_from_arango
                else "top_rx already provided"
            ),
        )

    cohort_summary = ""
    if req.fetch_cohort_rx_from_arango and dx_codes:
        try:
            cohort_stats = fetch_cohort_prescriptions_by_diagnosis_codes(
                dx_codes,
                limit=req.arango_cohort_rx_limit,
            )
        except Exception as exc:
            logger.warning("코호트 처방 조회 실패 (codes=%r): %s", dx_codes, exc)
            cohort_stats = []
            trace_tool(
                "cohort_rx_from_arango",
                True,
                status="failed",
                input={"disease_codes": dx_codes, "limit": req.arango_cohort_rx_limit},
                error=str(exc),
            )
        if cohort_stats:
            used_cohort = True
            cohort_count = len(cohort_stats)
            cohort_lines = cohort_stat_rows_to_top_rx_lines(cohort_stats)
            effective_top_rx = _merge_top_rx_with_cohort(effective_top_rx, cohort_lines)
            cohort_summary = format_cohort_similar_outcomes_summary(dx_codes, cohort_stats)
            trace_tool(
                "cohort_rx_from_arango",
                True,
                status="success",
                input={"disease_codes": dx_codes, "limit": req.arango_cohort_rx_limit},
                rowCount=len(cohort_stats),
            )
            logger.info(
                "상병 코호트 처방 %d건 병합 (codes=%r)",
                cohort_count,
                dx_codes,
            )
        else:
            if eval_trace_enabled and not any(
                row.get("tool") == "cohort_rx_from_arango" and row.get("status") == "failed"
                for row in tool_trace
            ):
                trace_tool(
                    "cohort_rx_from_arango",
                    True,
                    status="empty",
                    input={"disease_codes": dx_codes, "limit": req.arango_cohort_rx_limit},
                    rowCount=0,
                )
    else:
        trace_tool(
            "cohort_rx_from_arango",
            False,
            reason=(
                "fetch_cohort_rx_from_arango=false"
                if not req.fetch_cohort_rx_from_arango
                else "disease_codes is empty"
            ),
        )

    similar_for_prompt = _combine_similar_outcomes(req.similar_outcomes, cohort_summary)

    if _is_empty_top_rx(effective_top_rx):
        effective_top_rx = [{"note": "데이터 부족: top_rx 비어 있음"}]

    user_msg = build_prescription_agent_prompt(
        patient_id=req.patient_id,
        symptoms=req.symptoms,
        history=req.history,
        top_rx=effective_top_rx,
        similar_outcomes=similar_for_prompt,
        clinician_question=req.clinician_question,
        mention_links=req.mention_links,
    )
    trace_tool(
        "prompt_builder",
        True,
        status="success",
        inputSummary={
            "has_top_rx": not _is_empty_top_rx(effective_top_rx),
            "has_similar_outcomes": bool(str(similar_for_prompt or "").strip()),
            "has_mention_links": bool(req.mention_links),
        },
    )

    # 게이트웨이에 실제로 실릴 모델. req.model 은 게이트웨이 payload 에 실리지
    # 않는다(luna 계약 — 서비스가 하나의 고정 모델만 사용). GC-2: req.model /
    # req.temperature 가 채워져 있는데도 조용히 버려지면 안 되므로 흔적을 남긴다.
    # 최종 리뷰 IMPORTANT 2: os.environ.get() 을 여기서 또 부르지 않는다 —
    # /health(_default_llm_model()) 와 서로 다른 시점에 읽으면 두 값이 어긋날
    # 수 있다. 단일 함수로 합쳐 항상 같은 값을 보게 한다.
    wire_model = _default_llm_model()
    ignored_kwargs: Dict[str, Any] = {}
    if req.model and req.model != wire_model:
        logger.warning(
            "req.model=%r 은(는) 무시됩니다 — 게이트웨이에는 항상 LLM_MODEL=%r 로 전송됩니다.",
            req.model,
            wire_model,
        )
        ignored_kwargs["ignoredRequestModel"] = req.model
    if req.temperature is not None:
        logger.warning(
            "req.temperature=%r 은(는) 무시됩니다 — 게이트웨이는 temperature 를 받지 않습니다(luna 계약).",
            req.temperature,
        )
        ignored_kwargs["ignoredTemperature"] = req.temperature

    provider = resolve_provider()
    if provider == "stub":
        raw = stub_prescription_response(effective_top_rx)
        llm_status = "stub"
        trace_tool(
            "llm_generate", True, status="success", model="stub", temperature=0.0, **ignored_kwargs
        )
    else:
        raw = _invoke_gateway_json(SYSTEM_PRESCRIPTION, user_msg, wire_model)
        llm_status = "real"
        trace_tool("llm_generate", True, status="success", model=wire_model, **ignored_kwargs)

    try:
        data = parse_prescriptions_llm_response(raw)
        trace_tool(
            "json_parse",
            True,
            status="success",
            prescriptionCount=len(data.get("prescriptions") or []),
        )
    except ValueError as exc:
        logger.error("LLM 응답 파싱 실패: %s / raw=%r", exc, raw)
        trace_tool(
            "json_parse",
            True,
            status="failed",
            error=str(exc),
            rawPreview=raw[:500],
        )
        raise HTTPException(status_code=502, detail=f"LLM JSON 파싱 실패: {exc}") from exc

    items = [PrescriptionItem(**item) for item in data["prescriptions"]]

    # confidence_by_code는 Arango co-occurrence 기반 계산 결과.
    # LLM 출력에는 confidence_score가 없으므로 처방코드로 매칭해서 주입한다.
    for it in items:
        if not it.prescription_code:
            continue
        code = str(it.prescription_code).strip()
        if not code or code == "미기재":
            continue
        if confidence_by_code:
            # M-4(verification.py 의 confidence_in_range 문서화 참조): 코드가
            # confidence_by_code 에 없어도 여기서 0.0 이 주입된다 — 조회된 0.0 과
            # 폴백된 0.0 이 구분되지 않는다. 동작은 그대로 두고 한계만 기록한다.
            it.confidence_score = confidence_by_code.get(code, 0.0)

    return PrescriptionRecommendResponse(
        prescriptions=items,
        used_arango_top_rx=used_arango,
        arango_top_rx_count=arango_count,
        used_cohort_rx=used_cohort,
        cohort_rx_count=cohort_count,
        toolTrace=tool_trace if eval_trace_enabled else [],
        # MINOR 6: 같은 요청 안에서 resolve_provider() 를 두 번 읽지 않는다 — 스레드풀에서
        # LLM_PROVIDER(프로세스 전역)가 요청 도중 바뀌면 engineStatus 와 llmStatus 가
        # 서로 다른 시점의 값을 가리켜 응답이 자기모순에 빠질 수 있다. 위에서 이미 읽은
        # provider 를 그대로 재사용한다 — GC-5: engineStatus 의 관측 가능한 동작(값)은
        # 바뀌지 않는다, resolve_provider() 를 몇 번 호출하는지만 바뀐다.
        engineStatus=provider,
        llmStatus=llm_status,
        verification=_safe_verify(candidates=effective_top_rx, items=items),
    )


@app.post(
    "/api/agent/prescription/feedback",
    response_model=PrescriptionFeedbackResponse,
)
def save_feedback(req: PrescriptionFeedbackRequest) -> PrescriptionFeedbackResponse:
    if not req.feedback_items:
        raise HTTPException(status_code=400, detail="feedback_items 가 비어 있습니다.")
    try:
        db = _get_arango_db()
        _ensure_feedback_graph_collections(db)
    except Exception as exc:
        logger.exception("ArangoDB 연결 또는 컬렉션 준비 실패")
        raise HTTPException(status_code=502, detail=f"ArangoDB 처리 실패: {exc}") from exc

    now_iso = datetime.now(timezone.utc).isoformat()
    history_col = db.collection(_ARANGO_HISTORY_VTX)
    fallback_rx_col = db.collection(_ARANGO_FALLBACK_RX_VTX)
    edge_col = db.collection(_ARANGO_RECOMMENDED_EDGE)

    history_key = _safe_key_part(req.history_id, "history")
    history_doc_id = f"{_ARANGO_HISTORY_VTX}/{history_key}"
    history_col.insert(
        {
            "_key": history_key,
            "history_id": req.history_id,
            "history_diagnose_id": req.history_diagnose_id,
            "updated_at": now_iso,
        },
        overwrite=True,
        silent=True,
    )

    saved_count = 0
    for item in req.feedback_items:
        rx_code_key = _safe_key_part(item.prescription_code, "unknown_code")
        rank_key = _safe_key_part(item.rank, "0")
        edge_key = f"{history_key}_{rank_key}_{rx_code_key}"

        target_doc_id = f"prescription_masters/{rx_code_key}"
        if not db.has_document(target_doc_id):
            fallback_rx_col.insert(
                {
                    "_key": rx_code_key,
                    "prescription_code": item.prescription_code,
                    "prescription_name": item.prescription_name,
                    "updated_at": now_iso,
                },
                overwrite=True,
                silent=True,
            )
            target_doc_id = f"{_ARANGO_FALLBACK_RX_VTX}/{rx_code_key}"

        edge_col.insert(
            {
                "_key": edge_key,
                "_from": history_doc_id,
                "_to": target_doc_id,
                "history_id": req.history_id,
                "history_diagnose_id": req.history_diagnose_id,
                "rank": item.rank,
                "prescription_id": item.prescription_id,
                "prescription_code": item.prescription_code,
                "prescription_name": item.prescription_name,
                "confidence_score": item.confidence_score,
                "reason": item.reason,
                "status": item.status,
                "updated_at": now_iso,
            },
            overwrite=True,
            silent=True,
        )
        saved_count += 1

    logger.info(
        "Arango 처방 피드백 저장 완료: history_id=%s saved=%s edge_collection=%s",
        req.history_id,
        saved_count,
        _ARANGO_RECOMMENDED_EDGE,
    )
    return PrescriptionFeedbackResponse(
        saved=saved_count,
        edge_collection=_ARANGO_RECOMMENDED_EDGE,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "prescription_api:app",
        host=os.environ.get("PRESCRIPTION_API_HOST", "0.0.0.0"),
        port=int(os.environ.get("PRESCRIPTION_API_PORT", "8001")),
        reload=bool(os.environ.get("PRESCRIPTION_API_RELOAD", "")),
    )
