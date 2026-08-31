"""검증 파이프라인의 배선.

**여기에는 도구 선택 루프가 없다.** 아키텍처 리뷰 §5 가 라이브 트레이스로
보인 것: 루프가 고른 4수 중 3수가 하드코딩 폴백 순서와 같았고, 종료는 모델의
FINALIZE 가 아니라 `max_iterations` 소진이었으며, 관측값이 다음 행동을 바꾼
유일한 사례는 루프 **밖** 의 하드코딩 재시도 목록이었다. 게이트웨이 호출 4회를
써서 `for` 루프가 공짜로 만들었을 시퀀스를 재생산한 것이다.

그래서 실행 순서는 도메인이 정한 고정 순서다 — 옛 `_fallback_tool_decision`
이 이미 갖고 있던 바로 그 순서:

    X-ray Result Loader -> Disease Validator -> Prescription Validator
      -> Pubmed Loader -> Prescription Finder -> Rule-based Finalize

모델은 두 자리에서만 쓴다(gateway.py 참조): PubMed 질의 생성과 근거 요약.
그 둘만 `ModelCallLedger` 에 기록되고, `llmStatus` 는 그 장부에서만 나온다.

부수 효과 두 가지를 기록해 둔다.
- 페이로드가 전부 state 에서 조립되므로, 모델의 `actionInput` 이 X-ray 관측값을
  덮어쓸 수 있던 구멍(`payload.update(action_input)`)이 사라졌다.
- Prescription Validator 가 후보 처방이 아니라 **저장 처방** 을 받는다(F-H6).
  옛 코드는 `candidate_prescriptions or saved_prescriptions` 로 후보를 우선해,
  "저장 처방이 상병과 맞는가" 를 묻는 도구가 방금 자기가 만든 추천을 검사했다.
- PubMed 조회가 `overallStatus == "PASS"` 게이팅 없이 항상 돈다(고정 순서의
  결과다). 문헌이 가장 필요한 WARNING/CRITICAL 응답에서 근거 검사가 구조적으로
  꺼져 있던 상태(F-H5)가 이 순서에서는 성립하지 않는다.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from . import pubmed
from .deadline import JobDeadline
from .finalize import (
    normalize_final_result,
    normalize_prescription_candidates,
    rule_based_finalize,
)
from .gateway import ModelCallLedger, create_llm, resolve_llm_status
from .llm_provider import resolve_provider
from .models import ValidationAgentRequest, ValidationAgentResponse
from .pubmed import format_article
from .state import ValidationState
from .trace import (
    downgrade_by_payload_source,
    invoke_tool,
    thought,
    trace_step,
)
from .tools import (
    disease_validator,
    prescription_finder,
    prescription_validator,
    pubmed_loader,
    xray_result_loader,
)
from .verification import verify_validation

logger = logging.getLogger("validation_agent.agent")


def run_validation_agent(request: ValidationAgentRequest) -> ValidationAgentResponse:
    deadline = JobDeadline.from_env()
    provider = resolve_provider()
    ledger = ModelCallLedger()

    state: ValidationState = {
        "event_id": request.eventId,
        "event_type": request.eventType,
        "history_id": request.historyId,
        "event_payload": request.eventPayload,
        "patient_summary": request.patientSummary,
        "symptoms": request.symptoms,
        "saved_diseases": request.savedDiseases,
        "saved_prescriptions": request.savedPrescriptions,
        "xray_inference": request.xrayInference,
        "candidate_prescriptions": [],
        "pubmed_articles": [],
        "finder_candidates": [],
        "prescription_verification": None,
        "prescription_llm_status": None,
    }
    trace: List[Dict[str, Any]] = []
    pubmed_evidence: List[Dict[str, Any]] = []
    pubmed_queries: List[str] = []

    # --- 1. X-ray 추론 결과 로드 -------------------------------------------
    if _budget_ok(deadline, trace, 1, "X-ray Result Loader", "X-ray 추론 결과 로드"):
        state["xray_check"] = invoke_tool(
            trace, "X-ray Result Loader",
            thought(1, "Spring 이 전달한 X-ray 추론 결과를 검증 컨텍스트로 로드한다."),
            {"xray_inference": state.get("xray_inference")},
            xray_result_loader,
        )

    # --- 2. 상병 검증 -------------------------------------------------------
    if _budget_ok(deadline, trace, 2, "Disease Validator", "상병 검증"):
        state["disease_check"] = invoke_tool(
            trace, "Disease Validator",
            thought(2, "저장 상병, 증상, X-ray 추론 결과의 일관성을 확인한다."),
            {
                "symptoms": state.get("symptoms"),
                "saved_diseases": state.get("saved_diseases", []),
                "xray_inference": state.get("xray_inference"),
            },
            disease_validator,
        )

    # --- 3. 처방 검증 -------------------------------------------------------
    # F-H6: 검사 대상은 의사가 저장한 처방이다. 후보로 치환하지 않는다.
    if _budget_ok(deadline, trace, 3, "Prescription Validator", "처방 검증"):
        state["prescription_check"] = invoke_tool(
            trace, "Prescription Validator",
            thought(3, "의사가 저장한 처방이 저장 상병/증상과 함께 검토 가능한지 확인한다."),
            {
                "symptoms": state.get("symptoms"),
                "saved_diseases": state.get("saved_diseases", []),
                "saved_prescriptions": state.get("saved_prescriptions", []),
            },
            prescription_validator,
        )

    interim = rule_based_finalize(state)
    interim_reason = str(interim.get("reason") or interim.get("summary") or "")

    # --- 4. PubMed 근거 ----------------------------------------------------
    if _budget_ok(deadline, trace, 4, "Pubmed Loader", "PubMed 근거 조회"):
        pubmed_evidence.extend(
            _load_pubmed_evidence(trace, state, interim_reason, pubmed_queries, ledger, provider)
        )

    # --- 5. 처방 후보 조회 --------------------------------------------------
    if _budget_ok(deadline, trace, 5, "Prescription Finder", "처방 후보 조회"):
        query_context = ", ".join(pubmed_queries[-2:]) or pubmed.build_query(state, interim_reason)
        finder_result = _invoke_prescription_finder(
            trace,
            thought(5, "기존 처방 RAG 에서 참고 처방 후보를 조회한다."),
            {
                "patient_id": str(
                    (state.get("patient_summary") or {}).get("patientId") or request.patientId or ""
                ),
                "diseases": state.get("saved_diseases", []),
                "symptoms": (
                    f"{state.get('symptoms') or ''}\n검증 사유: {interim_reason}\n"
                    f"PubMed query: {query_context}"
                ),
            },
            state,
        )
        candidates_from_finder = finder_result.get("candidatePrescriptions") or []
        if candidates_from_finder:
            state["candidate_prescriptions"] = normalize_prescription_candidates(candidates_from_finder)

    # --- 6. 규칙 기반 판정 --------------------------------------------------
    final_result = dict(rule_based_finalize(state))
    final_overall = str(final_result.get("overallStatus") or "NEEDS_REVIEW").upper()
    trace_step(
        trace, "Rule-based Finalize",
        thought(6, "수집된 관측값으로 결정론적 규칙이 최종 판정을 만든다."),
        {},
        {
            "status": "FINALIZED",
            "evidence": [
                f"overallStatus={final_overall}",
                "이 판정(overallStatus/summary/reason/checks)은 모델이 아니라 "
                "결정론적 규칙(finalize.rule_based_finalize)이 만들었습니다.",
            ],
        },
        "rule",
    )

    # PubMed 근거 요약. 모델 호출 2/2 — 근거가 하나도 없으면 호출 자체가 없다.
    pubmed_evidence_summary, summary_source = pubmed.summarize_evidence(
        state, pubmed_evidence, final_overall, ledger, create_llm, provider
    )
    if pubmed_evidence_summary:
        checks = final_result.get("checks") if isinstance(final_result.get("checks"), list) else []
        # 규칙 기반 문자열 조합 요약을 모델이 쓴 것처럼 보이게 하지 않는다.
        summary_label = "PubMed 근거 요약" if summary_source == "llm" else "PubMed 근거 요약(규칙 기반)"
        checks.append({
            "type": "PUBMED_EVIDENCE",
            "status": "REFERENCE",
            "message": f"{summary_label}: {pubmed_evidence_summary}",
            "evidence": [
                format_article(article, include_abstract=True)
                for article in pubmed_evidence[:3]
            ],
            "relatedDiseases": state.get("saved_diseases", []),
            "relatedPrescriptions": state.get("candidate_prescriptions") or state.get("saved_prescriptions", []),
            "recommendedAction": "논문 초록 기반 참고 근거이므로 의료진이 환자 상태와 원문을 함께 확인하세요.",
        })
        final_result["checks"] = checks

    graph_lookup = state.get("graph_lookup")
    graph_check = _graph_lookup_check(state, graph_lookup)
    if graph_check:
        checks = final_result.get("checks") if isinstance(final_result.get("checks"), list) else []
        checks.append(graph_check)
        final_result["checks"] = checks

    candidates = normalize_prescription_candidates(state.get("candidate_prescriptions", []))
    final_result.update({
        "jobId": request.jobId,
        "historyId": request.historyId,
        "recommendedPrescriptions": candidates,
        "candidatePrescriptions": candidates,
        "validation": {
            "diseaseValidation": state.get("disease_check") or {},
            "prescriptionValidation": state.get("prescription_check") or {},
            "xrayInference": state.get("xray_inference"),
            "pubmedEvidence": pubmed_evidence,
            "pubmedQueries": pubmed_queries,
            "pubmedEvidenceSummary": pubmed_evidence_summary,
            # 후보 조회 단계를 돌지 않았으면 None 이다. "확인 못 함" 은 "0건" 과
            # 다른 상태이므로 빈 dict 로 채우지 않는다(GC-3, 설계 문서 §3.2).
            "graphLookup": graph_lookup,
        },
        "reasoningTrace": trace,
        # 이 실행에서 실제로 성사된 모델 호출만 본다(GC-5). 도구 실행 결과나
        # 상류 서비스가 보고한 출처는 여기 들어오지 않는다.
        "llmStatus": resolve_llm_status(ledger.sources),
    })
    if pubmed_evidence and final_overall != "PASS":
        final_result["reason"] = _with_pubmed_reason(str(final_result.get("reason") or ""), pubmed_evidence)
    # normalize_final_result 는 알려진 키만 남기는 새 dict 를 만들어 돌려주므로
    # (임의 키를 그대로 통과시키지 않는다), verification 은 정규화 이후에 얹는다.
    response_payload = normalize_final_result(final_result)
    response_payload["verification"] = _safe_verify(state, response_payload)
    # prescription_api 자신의 항목 단위 검증. validation-agent 자신의 verification
    # (바로 위)과는 다른 서비스, 다른 판정이라 별도 필드로만 얹는다 — 병합하지
    # 않는다(최종 리뷰 C1). 후보 조회 자체가 없었으면(예: 예산 초과로 5단계를
    # 건너뛴 경우) None 그대로 두어 GC-2/GC-3(미검증 fail-closed)를 지킨다.
    response_payload["prescriptionVerification"] = state.get("prescription_verification")
    # prescription_api 자신의 모델 출처. 위 `llmStatus`(이 서비스의 모델 호출
    # 원장에서 도출)와 같은 자리에 섞지 않고 별도 필드로만 얹는다 —
    # prescriptionVerification 과 정확히 같은 이유, 같은 방식이다(F-H3).
    # 후보 조회가 아예 없었으면 None 그대로 둔다(GC-2/GC-3).
    response_payload["prescriptionLlmStatus"] = state.get("prescription_llm_status")
    # prescription_api 의 신기능 금기 관문. 위 verification / llmStatus 와 정확히
    # 같은 이유로 최상위 별도 필드다 — 다른 서비스의 판정을 이 에이전트의 판정에
    # 병합하지 않는다(최종 리뷰 C1). 후보 조회가 없었으면 None 이다(GC-2/GC-3).
    response_payload["prescriptionRenalGate"] = state.get("renal_gate")
    return ValidationAgentResponse(**response_payload)


# ---------------------------------------------------------------------------
# 전역 예산
# ---------------------------------------------------------------------------

def _budget_ok(
    deadline: JobDeadline,
    trace: List[Dict[str, Any]],
    index: int,
    action: str,
    step_label: str,
) -> bool:
    """예산이 남았으면 True. 소진됐으면 그 사실을 트레이스에 남기고 False.

    조용히 건너뛰면 GC-2 위반이다 — 실행되지 않은 단계는 "확인했는데 문제
    없었다" 가 아니라 "확인하지 못했다" 이고, 그 구분이 화면까지 가야 한다.
    """
    if not deadline.expired():
        return True
    trace_step(
        trace, action,
        thought(index, f"{step_label} — 전역 예산 소진으로 실행하지 않음."),
        {},
        {"status": "BUDGET_EXCEEDED", "evidence": [deadline.reason(action)]},
        "rule",
    )
    return False


def _graph_lookup_check(
    state: ValidationState,
    graph_lookup: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """ArangoDB 처방 그래프 조회 결과를 checks 한 줄로 만든다(F-M6).

    세 상태를 구분한다(설계 문서 §3.2, GC-3).

    - `None` — 후보 조회 단계를 아예 돌지 않았다. 트레이스가 이미 그 사실을
      남기므로 여기서 check 를 만들지 않는다. 없는 근거를 "0건" 으로 바꾸지 않는다
    - `status == "FAILED"` — 조회하지 못했다. "확인 못 함" 이다
    - `foundNothing` — 조회했고 참고할 처방이 정말 0건이다
    """
    if not isinstance(graph_lookup, dict):
        return None
    status = str(graph_lookup.get("status") or "")
    evidence = list(graph_lookup.get("evidence") or [])
    related = {
        "relatedDiseases": state.get("saved_diseases", []),
        "relatedPrescriptions": state.get("saved_prescriptions", []),
    }
    if status == "FAILED":
        return {
            "type": "GRAPH_LOOKUP",
            "status": "UNKNOWN",
            "message": "처방 그래프를 조회하지 못해 과거 처방·코호트 근거를 확인하지 못했습니다.",
            "evidence": evidence,
            **related,
            "recommendedAction": "그래프 근거가 확인되지 않은 추천이므로 의료진이 더 보수적으로 확인하세요.",
        }
    if graph_lookup.get("foundNothing"):
        return {
            "type": "GRAPH_LOOKUP",
            "status": "NO_DATA",
            "message": "처방 그래프에 이 상병을 뒷받침하는 과거 처방·코호트 처방이 없습니다.",
            "evidence": evidence,
            **related,
            "recommendedAction": "그래프 근거 없이 생성된 추천이므로 의료진이 더 보수적으로 확인하세요.",
        }
    return None


def _invoke_prescription_finder(
    trace: List[Dict[str, Any]],
    thought: str,
    payload: Dict[str, Any],
    state: ValidationState,
) -> Dict[str, Any]:
    """Prescription Finder 전용 호출 래퍼.

    `state["finder_candidates"]` 에 관측값 원본(정규화 전)을 누적한다 — 검증기
    (app.verification)가 대조할 기준은 응답에 실리는 정규화값이 아니라 이
    원본이어야 한다(spec §4.1).

    상류가 보고한 `recommendationLlmStatus` 는 **트레이스 스텝의 source 강등에만**
    쓴다. `ModelCallLedger` 에는 절대 넣지 않는다 — 최상위 llmStatus 를 다른
    서비스의 출처로 오염시키면 Task 6 의 결함이 재발한다.
    """
    try:
        observation = prescription_finder.invoke(payload)
    except Exception as exc:  # noqa: BLE001
        observation = {"status": "FAILED", "evidence": [str(exc)]}
    payload_status = (
        observation.get("recommendationLlmStatus") if isinstance(observation, dict) else None
    )
    trace_step(
        trace, "Prescription Finder", thought, payload, observation,
        downgrade_by_payload_source("rule", payload_status),
    )
    if isinstance(observation, dict):
        raw_candidates = observation.get("candidatePrescriptions") or []
        if isinstance(raw_candidates, list):
            state.setdefault("finder_candidates", []).extend(raw_candidates)
        # prescription_api 자신의 항목 단위 검증(target="prescription[N]") 원본을
        # 그대로 들고 있는다 — 최상위 응답의 prescriptionVerification 이 이 값을
        # 읽는다(최종 리뷰 C1).
        state["prescription_verification"] = observation.get("recommendationVerification")
        # 같은 관측값에서 처방 RAG 자신의 llmStatus 도 들고 있는다. 이 값이
        # 최상위까지 가지 않아서 처방 표의 모델 배지가 읽을 값이 없었고,
        # 그래서 다른 서비스의 llmStatus 를 읽고 있었다(F-H3). 키가 없으면
        # None 이 그대로 남아 웹이 "미확인" 으로 렌더한다(GC-3).
        state["prescription_llm_status"] = observation.get("recommendationLlmStatus")
        # ArangoDB 처방 그래프 조회 결과(F-M6). 키가 없으면 None 이 남아 "확인
        # 못 함" 으로 렌더된다 — "0건" 이라고 주장하지 않는다(GC-3).
        state["graph_lookup"] = observation.get("graphLookup")
        # 신기능 금기 관문. 값이 없으면 None 이 남고 웹은 "확인 못 함" 으로
        # 렌더한다 — 관문의 clear(표 범위 밖) 와 다른 상태다(설계 §3.3).
        state["renal_gate"] = observation.get("recommendationRenalGate")
    return observation if isinstance(observation, dict) else {"status": "UNKNOWN", "raw": observation}


# ---------------------------------------------------------------------------
# PubMed 조회
# ---------------------------------------------------------------------------

def _load_pubmed_evidence(
    trace: List[Dict[str, Any]],
    state: ValidationState,
    reason: str,
    pubmed_queries: List[str],
    ledger: ModelCallLedger,
    provider: str,
) -> List[Dict[str, Any]]:
    """모델 질의를 먼저, 규칙 빌더 질의를 뒤에 시도하고 첫 성공에서 멈춘다.

    이 재시도 목록이 리뷰가 관측한 유일한 "관측이 다음 행동을 바꾼" 지점이다
    (§5.3) — 그리고 그것은 루프가 아니라 여기 있었다. 옛 루프는 0건이라는
    사실을 보지도 못했다.

    스텝의 `source` 는 **이번에 실제로 검색에 쓰인 질의문 하나** 를 기준으로
    정한다: 모델이 만든 질의면 "llm", 규칙 빌더 질의면 "rule"(모델 호출이
    실패했다면 "fallback"). 배치 단위로 판정하면, 모델 질의가 0건을 내고
    사전 질의가 성공한 스텝까지 "llm" 으로 찍힌다.
    """
    llm_queries, query_source = pubmed.generate_queries_with_llm(
        state, reason, ledger, create_llm, provider
    )
    candidates = pubmed.build_query_candidates(state, reason, llm_queries)

    max_attempts = int(os.environ.get("VALIDATION_PUBMED_MAX_QUERY_ATTEMPTS", "4"))
    articles: List[Dict[str, Any]] = []
    for index, query in enumerate(candidates[:max_attempts], start=1):
        if not query or query in pubmed_queries:
            continue
        pubmed_queries.append(query)
        if query in llm_queries:
            step_source = "llm"
            origin = "모델이 생성한 영어 질의"
        else:
            # 모델 호출이 실패해서 여기로 떨어졌는지, 애초에 모델을 안 쓰는
            # 경로였는지를 구분해서 표기한다.
            step_source = query_source if query_source in {"stub", "fallback"} else "rule"
            origin = "규칙 기반 질의 빌더"
        observation = invoke_tool(
            trace, "Pubmed Loader",
            thought(4, f"PubMed 검색 시도 {index} — 검색어 출처: {origin}."),
            {"query": query, "max_results": 3},
            pubmed_loader,
            source=step_source,
        )
        raw_articles = observation.get("articles") or []
        # 검증기(app.verification) 대조 기준은 관측값 원본이다(spec §4.1).
        # dedupe 는 표시용 가공이므로 여기에 쌓는 것은 원본이어야 한다.
        state.setdefault("pubmed_articles", []).extend(raw_articles)
        articles.extend(raw_articles)
        if articles:
            break
    return pubmed.dedupe_articles(articles)


def _with_pubmed_reason(reason: str, pubmed_evidence: List[Dict[str, Any]]) -> str:
    evidence_lines = []
    for article in pubmed_evidence[:3]:
        citation = format_article(article, include_abstract=True)
        if not citation:
            continue
        evidence_lines.append(citation)

    if not evidence_lines:
        return reason

    pubmed_reason = "PubMed 근거 후보: " + " / ".join(evidence_lines)
    if reason:
        return f"{reason} {pubmed_reason}"
    return pubmed_reason


# ---------------------------------------------------------------------------
# 검증
# ---------------------------------------------------------------------------

def _safe_verify(state: Any, response_payload: Dict[str, Any]) -> Dict[str, Any]:
    """검증을 돌리되 본 응답을 실패시키지 않는다(GC-4).

    반드시 도구 관측값 원본(state["pubmed_articles"] / state["finder_candidates"])을
    넘긴다 — state["candidate_prescriptions"] 처럼 응답에 그대로 실리는 정규화값을
    넘기면 응답이 자기 자신과 비교돼 어떤 입력으로도 flagged 가 나올 수 없다.
    """
    try:
        return verify_validation(
            pubmed_articles=state.get("pubmed_articles") or [],
            finder_candidates=state.get("finder_candidates") or [],
            response_dict=response_payload,
        ).to_dict()
    except Exception as exc:  # noqa: BLE001
        logger.warning("검증 실패, skipped 로 처리: %s", type(exc).__name__)
        return {
            "status": "skipped",
            "checks": [],
            "skippedReason": f"검증기 예외: {type(exc).__name__}",
        }
