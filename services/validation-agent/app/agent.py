from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph

from .models import ValidationAgentRequest, ValidationAgentResponse
from .tools import (
    disease_validator,
    pubmed_loader,
    prescription_finder,
    prescription_validator,
    xray_result_loader,
)


KOREAN_PUBMED_TERMS = {
    "결절성 근막염": "nodular fasciitis",
    "근막염": "fasciitis",
    "근육의 기타 명시된 장애": "muscle disorder",
    "근육": "muscle",
    "손가락": "finger",
    "손목": "wrist",
    "발목": "ankle",
    "무릎": "knee",
    "어깨": "shoulder",
    "허리": "back pain",
    "폐렴": "pneumonia",
    "기침": "cough",
    "발열": "fever",
    "통증": "pain",
}

DEFAULT_OPENAI_MODEL = "gpt-5-nano"


class ValidationState(TypedDict, total=False):
    event_id: int
    event_type: str
    history_id: int
    event_payload: Dict[str, Any]
    patient_summary: Dict[str, Any]
    symptoms: Optional[str]
    saved_diseases: List[Dict[str, Any]]
    saved_prescriptions: List[Dict[str, Any]]
    xray_inference: Optional[Dict[str, Any]]
    xray_check: Dict[str, Any]
    disease_check: Dict[str, Any]
    prescription_check: Dict[str, Any]
    candidate_prescriptions: List[Dict[str, Any]]
    final_result: Dict[str, Any]


SYSTEM_PROMPT = """너는 의료 진료 데이터 검증 보조 에이전트다.

역할:
- DB에 저장된 상병, 처방, 증상, X-ray 이미지 기반 추론 결과 사이의 일관성을 검토한다.
- 의사를 대체하지 않는다.
- 최종 진단 확정, 처방 자동 변경, DB 수정은 하지 않는다.
- 의료진이 확인해야 할 위험 신호를 구조화된 JSON으로만 반환한다.

판단 원칙:
- X-ray 추론 점수가 높더라도 DB 상병이 반드시 틀렸다고 단정하지 않는다.
- 저장 상병과 X-ray 추론 결과가 다르면 불일치 가능성으로 표현한다.
- 증상 정보가 부족하면 INSUFFICIENT_DATA 또는 NEEDS_REVIEW를 사용한다.
- 처방 후보는 참고 정보이며 기존 처방을 자동 대체하지 않는다.
- 환자에게 직접 제공할 문장이 아니라 의료진 검토용 시스템 결과로 작성한다.

반드시 JSON만 출력한다.
"""


def run_validation_agent(request: ValidationAgentRequest) -> ValidationAgentResponse:
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
    }
    reasoning_trace: List[Dict[str, Any]] = []
    pubmed_evidence: List[Dict[str, Any]] = []
    pubmed_queries: List[str] = []
    max_iterations = int(os.environ.get("VALIDATION_REACT_MAX_ITERATIONS", "4"))

    final_result: Dict[str, Any] = {}
    for iteration in range(1, max_iterations + 1):
        decision = _decide_next_tool(state, reasoning_trace, pubmed_queries, iteration)
        action = str(decision.get("action") or "FINALIZE")
        if action == "FINALIZE":
            break
        _execute_decided_tool(
            decision,
            state,
            request,
            reasoning_trace,
            pubmed_evidence,
            pubmed_queries,
        )
        if state.get("disease_check") or state.get("prescription_check"):
            final_result = _rule_based_finalize(state)

    final_result = dict(final_result or _rule_based_finalize(state))
    final_overall = str(final_result.get("overallStatus") or "NEEDS_REVIEW").upper()
    if final_overall == "PASS" and not pubmed_evidence:
        reason = final_result.get("reason") or final_result.get("summary") or ""
        pubmed_evidence.extend(_load_pubmed_evidence(
            reasoning_trace,
            "검증 통과 결과에 참고할 의학 문헌 후보를 PubMed에서 검색한다.",
            state,
            str(reason),
            pubmed_queries,
        ))

    if not state.get("candidate_prescriptions"):
        reason = final_result.get("reason") or final_result.get("summary") or ""
        query_context = ", ".join(pubmed_queries[-2:]) or _build_pubmed_query(state, str(reason))
        finder_result = _invoke_tool(
            reasoning_trace,
            "Prescription Finder",
            "검증 상태와 무관하게 AI 처방 추천 결과를 생성하기 위해 처방 후보를 조회한다.",
            {
                "patient_id": str((state.get("patient_summary") or {}).get("patientId") or request.patientId or ""),
                "diseases": state.get("saved_diseases", []),
                "symptoms": f"{state.get('symptoms') or ''}\n검증 사유: {reason}\nPubMed query: {query_context}",
            },
            prescription_finder,
        )
        candidates_from_finder = finder_result.get("candidatePrescriptions") or []
        if candidates_from_finder:
            state["candidate_prescriptions"] = _normalize_prescription_candidates(candidates_from_finder)

    pubmed_evidence_summary = _summarize_pubmed_evidence(state, pubmed_evidence, final_overall)
    if pubmed_evidence_summary:
        checks = final_result.get("checks") if isinstance(final_result.get("checks"), list) else []
        checks.append({
            "type": "PUBMED_EVIDENCE",
            "status": "REFERENCE",
            "message": f"PubMed 근거 요약: {pubmed_evidence_summary}",
            "evidence": [
                _format_pubmed_article(article, include_abstract=True)
                for article in pubmed_evidence[:3]
            ],
            "relatedDiseases": state.get("saved_diseases", []),
            "relatedPrescriptions": state.get("candidate_prescriptions") or state.get("saved_prescriptions", []),
            "recommendedAction": "논문 초록 기반 참고 근거이므로 의료진이 환자 상태와 원문을 함께 확인하세요.",
        })
        final_result["checks"] = checks

    candidates = _normalize_prescription_candidates(state.get("candidate_prescriptions", []))
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
        },
        "reasoningTrace": reasoning_trace,
    })
    if pubmed_evidence and final_overall != "PASS":
        final_result["reason"] = _with_pubmed_reason(str(final_result.get("reason") or ""), pubmed_evidence)
    return ValidationAgentResponse(**_normalize_final_result(final_result))


def _invoke_tool(
    reasoning_trace: List[Dict[str, Any]],
    action: str,
    thought: str,
    payload: Dict[str, Any],
    tool_obj: Any,
) -> Dict[str, Any]:
    try:
        observation = tool_obj.invoke(payload)
    except Exception as exc:  # noqa: BLE001
        observation = {"status": "FAILED", "evidence": [str(exc)]}
    reasoning_trace.append({
        "thought": thought,
        "action": action,
        "actionInput": payload,
        "observation": observation,
    })
    return observation if isinstance(observation, dict) else {"status": "UNKNOWN", "raw": observation}


def _create_llm() -> Optional[ChatOpenAI]:
    if not os.environ.get("OPENAI_API_KEY"):
        return None
    model = os.environ.get("OPENAI_MODEL", DEFAULT_OPENAI_MODEL)
    return ChatOpenAI(model=model, temperature=0)


def _decide_next_tool(
    state: ValidationState,
    reasoning_trace: List[Dict[str, Any]],
    pubmed_queries: List[str],
    iteration: int,
) -> Dict[str, Any]:
    if os.environ.get("OPENAI_API_KEY"):
        decision = _llm_tool_decision(state, reasoning_trace, pubmed_queries, iteration)
        if decision:
            return decision
    return _fallback_tool_decision(state, pubmed_queries)


def _llm_tool_decision(
    state: ValidationState,
    reasoning_trace: List[Dict[str, Any]],
    pubmed_queries: List[str],
    iteration: int,
) -> Optional[Dict[str, Any]]:
    payload = {
        "iteration": iteration,
        "state": _compact_state(state),
        "pubmedQueries": pubmed_queries,
        "recentTrace": reasoning_trace[-6:],
        "hasCandidatePrescriptions": bool(state.get("candidate_prescriptions")),
        "availableTools": [
            {
                "action": "X-ray Result Loader",
                "purpose": "Spring이 전달한 최신 X-ray 추론 결과를 검증 컨텍스트로 로드한다.",
                "requiredInput": {"xray_inference": "state.xray_inference"},
            },
            {
                "action": "Disease Validator",
                "purpose": "저장 상병, 증상, X-ray 추론 결과의 일관성을 확인한다.",
                "requiredInput": ["symptoms", "saved_diseases", "xray_inference"],
            },
            {
                "action": "Prescription Validator",
                "purpose": "현재 저장 처방 또는 추천 후보와 상병/증상의 관련성을 검증한다.",
                "requiredInput": ["symptoms", "saved_diseases", "saved_prescriptions"],
            },
            {
                "action": "Pubmed Loader",
                "purpose": "검증 근거가 부족하거나 문헌 근거가 필요할 때 PubMed 초록을 검색한다.",
                "requiredInput": {"query": "English PubMed query", "max_results": 3},
            },
            {
                "action": "Prescription Finder",
                "purpose": "검증 결과와 문헌 근거를 바탕으로 기존 처방 RAG에서 처방 후보를 조회한다.",
                "requiredInput": ["patient_id", "diseases", "symptoms"],
            },
            {
                "action": "FINALIZE",
                "purpose": "검증과 처방 추천에 필요한 근거가 충분하면 종료한다.",
            },
        ],
    }
    prompt = f"""너는 ReAct 방식의 의료 검증 보조 에이전트다.
다음 상태를 보고 지금 한 단계에서 사용할 도구 하나만 선택하라.

목표:
- 저장 상병, 처방, 증상, X-ray 추론의 일관성을 검증한다.
- 처방 추천 버튼의 결과이므로 최종 종료 전에는 가능한 한 Prescription Finder를 호출해 처방 후보를 확보한다.
- PubMed 근거가 없으면 필요 시 Pubmed Loader를 호출해 초록 근거를 확보한다.
- 같은 도구를 불필요하게 반복 호출하지 않는다.
- 의료진 검토용이며 진단/처방 확정처럼 단정하지 않는다.

반드시 JSON만 출력:
{{
  "thought": "왜 이 도구가 필요한지",
  "action": "X-ray Result Loader | Disease Validator | Prescription Validator | Pubmed Loader | Prescription Finder | FINALIZE",
  "actionInput": {{}}
}}

상태:
{json.dumps(payload, ensure_ascii=False)}
"""
    try:
        llm = _create_llm()
        if not llm:
            return None
        response = llm.invoke([
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ])
        parsed = _parse_json_object(str(response.content))
    except Exception:
        return None
    if not parsed:
        return None
    action = str(parsed.get("action") or "")
    allowed = {
        "X-ray Result Loader",
        "Disease Validator",
        "Prescription Validator",
        "Pubmed Loader",
        "Prescription Finder",
        "FINALIZE",
    }
    if action not in allowed:
        return None
    return {
        "thought": str(parsed.get("thought") or f"{action} 실행이 필요합니다."),
        "action": action,
        "actionInput": parsed.get("actionInput") if isinstance(parsed.get("actionInput"), dict) else {},
    }


def _fallback_tool_decision(state: ValidationState, pubmed_queries: List[str]) -> Dict[str, Any]:
    if "xray_check" not in state:
        return {
            "thought": "먼저 X-ray 추론 결과를 검증 컨텍스트로 로드한다.",
            "action": "X-ray Result Loader",
            "actionInput": {},
        }
    if "disease_check" not in state:
        return {
            "thought": "저장 상병, 증상, X-ray 추론 결과의 일관성을 먼저 확인한다.",
            "action": "Disease Validator",
            "actionInput": {},
        }
    if "prescription_check" not in state:
        return {
            "thought": "현재 저장 처방 또는 후보 처방이 상병/증상과 검토 가능한지 확인한다.",
            "action": "Prescription Validator",
            "actionInput": {},
        }
    if not pubmed_queries:
        return {
            "thought": "검증 결과를 설명할 문헌 근거를 확보하기 위해 PubMed를 검색한다.",
            "action": "Pubmed Loader",
            "actionInput": {},
        }
    if not state.get("candidate_prescriptions"):
        return {
            "thought": "검증 근거를 바탕으로 처방 후보를 조회한다.",
            "action": "Prescription Finder",
            "actionInput": {},
        }
    return {
        "thought": "필요한 검증, 문헌 근거, 처방 후보가 확보되어 결과를 정리한다.",
        "action": "FINALIZE",
        "actionInput": {},
    }


def _execute_decided_tool(
    decision: Dict[str, Any],
    state: ValidationState,
    request: ValidationAgentRequest,
    reasoning_trace: List[Dict[str, Any]],
    pubmed_evidence: List[Dict[str, Any]],
    pubmed_queries: List[str],
) -> None:
    action = str(decision.get("action") or "")
    thought = str(decision.get("thought") or f"{action} 실행")
    action_input = decision.get("actionInput") if isinstance(decision.get("actionInput"), dict) else {}

    if action == "X-ray Result Loader":
        payload = {"xray_inference": state.get("xray_inference")}
        payload.update(action_input)
        state["xray_check"] = _invoke_tool(
            reasoning_trace,
            action,
            thought,
            payload,
            xray_result_loader,
        )
        return

    if action == "Disease Validator":
        payload = {
            "symptoms": state.get("symptoms"),
            "saved_diseases": state.get("saved_diseases", []),
            "xray_inference": state.get("xray_inference"),
        }
        state["disease_check"] = _invoke_tool(
            reasoning_trace,
            action,
            thought,
            payload,
            disease_validator,
        )
        return

    if action == "Prescription Validator":
        payload = {
            "symptoms": state.get("symptoms"),
            "saved_diseases": state.get("saved_diseases", []),
            "saved_prescriptions": state.get("candidate_prescriptions") or state.get("saved_prescriptions", []),
        }
        state["prescription_check"] = _invoke_tool(
            reasoning_trace,
            action,
            thought,
            payload,
            prescription_validator,
        )
        return

    if action == "Pubmed Loader":
        query = str(action_input.get("query") or "").strip()
        if query:
            if query not in pubmed_queries:
                pubmed_queries.append(query)
            pubmed_result = _invoke_tool(
                reasoning_trace,
                action,
                thought,
                {"query": query, "max_results": int(action_input.get("max_results") or 3)},
                pubmed_loader,
            )
            pubmed_evidence.extend(_dedupe_pubmed_articles(pubmed_result.get("articles") or []))
        else:
            reason = _summary_for_current_state(state)
            pubmed_evidence.extend(_load_pubmed_evidence(
                reasoning_trace,
                thought,
                state,
                reason,
                pubmed_queries,
            ))
        return

    if action == "Prescription Finder":
        reason = _summary_for_current_state(state)
        query_context = ", ".join(pubmed_queries[-2:]) or _build_pubmed_query(state, reason)
        payload = {
            "patient_id": str((state.get("patient_summary") or {}).get("patientId") or request.patientId or ""),
            "diseases": state.get("saved_diseases", []),
            "symptoms": f"{state.get('symptoms') or ''}\n검증 사유: {reason}\nPubMed query: {query_context}",
        }
        finder_result = _invoke_tool(
            reasoning_trace,
            action,
            thought,
            payload,
            prescription_finder,
        )
        candidates = finder_result.get("candidatePrescriptions") or []
        if candidates:
            state["candidate_prescriptions"] = _normalize_prescription_candidates(candidates)


def _summary_for_current_state(state: ValidationState) -> str:
    result = _rule_based_finalize(state)
    return str(result.get("reason") or result.get("summary") or "")


def _load_pubmed_evidence(
    reasoning_trace: List[Dict[str, Any]],
    thought: str,
    state: ValidationState,
    reason: str,
    pubmed_queries: List[str],
) -> List[Dict[str, Any]]:
    articles: List[Dict[str, Any]] = []
    max_query_attempts = int(os.environ.get("VALIDATION_PUBMED_MAX_QUERY_ATTEMPTS", "4"))
    for query in _build_pubmed_queries(state, reason)[:max_query_attempts]:
        if not query or query in pubmed_queries:
            continue
        pubmed_queries.append(query)
        pubmed_result = _invoke_tool(
            reasoning_trace,
            "Pubmed Loader",
            thought,
            {"query": query, "max_results": 3},
            pubmed_loader,
        )
        articles.extend(pubmed_result.get("articles") or [])
        if articles:
            break
    return _dedupe_pubmed_articles(articles)


def _build_pubmed_queries(state: ValidationState, reason: str) -> List[str]:
    queries: List[str] = []
    queries.extend(_generate_pubmed_queries_with_llm(state, reason))
    queries.append(_build_pubmed_query(state, reason))
    queries.append(_build_pubmed_reference_query(state))
    queries.append(_build_pubmed_disease_query(state))
    queries.append(_build_pubmed_prescription_query(state))
    return _dedupe_queries(queries)


def _generate_pubmed_queries_with_llm(state: ValidationState, reason: str) -> List[str]:
    llm = _create_llm()
    if not llm:
        return []

    payload = _compact_state(state)
    prompt = f"""다음 진료 검증 컨텍스트를 PubMed ESearch에 적합한 영어 검색어로 정규화하라.

요구사항:
- 한국어 상병명/증상/처방명을 영어 의학 검색어로 번역한다.
- 너무 긴 문장을 만들지 말고, query당 핵심 용어 3~6개만 사용한다.
- 코드(M7244 등)만 단독으로 쓰지 말고 가능한 질환명, 부위, 처방 성분명, treatment/diagnosis 중심으로 작성한다.
- 결과는 JSON만 출력한다.

응답 스키마:
{{"queries": ["query 1", "query 2", "query 3"]}}

검증 사유:
{reason}

검증 컨텍스트:
{json.dumps(payload, ensure_ascii=False)}
"""
    try:
        response = llm.invoke([
            SystemMessage(content="You generate concise English PubMed search queries and return JSON only."),
            HumanMessage(content=prompt),
        ])
        parsed = _parse_json_object(str(response.content))
    except Exception:
        return []

    if not parsed or not isinstance(parsed.get("queries"), list):
        return []
    return [
        _clean_pubmed_query(query)
        for query in parsed["queries"]
        if isinstance(query, str) and _clean_pubmed_query(query)
    ]


def _build_pubmed_query(state: ValidationState, reason: str) -> str:
    xray_inference = state.get("xray_inference") or {}
    predicted = xray_inference.get("predictedDiseases") if isinstance(xray_inference, dict) else []
    if not isinstance(predicted, list):
        predicted = []
    xray_terms = _unique_terms(
        _pubmed_term(row.get("disease") or row.get("name") or row.get("label"))
        for row in predicted
        if isinstance(row, dict)
    )
    suspicious_terms = _unique_terms(
        _pubmed_term(row.get("disease") or row.get("name") or row.get("label"))
        for row in ((state.get("disease_check") or {}).get("suspiciousItems") or [])
        if isinstance(row, dict)
    )
    disease_terms = _unique_terms(
        _pubmed_term(row.get("name") or row.get("code") or "")
        for row in (state.get("saved_diseases") or [])
    )
    prescription_terms = _unique_terms(
        _pubmed_term(row.get("name") or row.get("prescription_name") or row.get("code") or "")
        for row in (state.get("candidate_prescriptions") or state.get("saved_prescriptions") or [])
    )
    symptoms = _unique_terms(_pubmed_term(state.get("symptoms") or "").split())

    # PubMed ESearch treats overly long mixed clinical text as a very narrow query.
    # Use the most important inferred disease plus prescription/treatment terms first.
    disease_focus = (xray_terms or suspicious_terms or disease_terms)[:2]
    prescription_focus = prescription_terms[:2]
    symptom_focus = symptoms[:2] if not prescription_focus else []
    query = " ".join([*disease_focus, *prescription_focus, *symptom_focus, "treatment"]).strip()
    return query[:500] or "pneumonia treatment"


def _clean_pubmed_query(query: str) -> str:
    query = " ".join(str(query or "").replace("\n", " ").split())
    tokens: List[str] = []
    seen: set[str] = set()
    for token in query.split():
        key = token.lower()
        if key not in seen:
            tokens.append(token)
            seen.add(key)
    return " ".join(tokens)[:500]


def _pubmed_term(value: Any) -> str:
    text = _translate_pubmed_terms(str(value or ""))
    ascii_text = text.encode("ascii", "ignore").decode("ascii")
    ascii_text = ascii_text.replace("_", " ")
    ascii_text = re.sub(r"[^A-Za-z0-9 +\"()/-]+", " ", ascii_text)
    ascii_text = ascii_text.replace("/", " ")
    return " ".join(ascii_text.split())


def _translate_pubmed_terms(text: str) -> str:
    translated = text
    for korean, english in KOREAN_PUBMED_TERMS.items():
        translated = translated.replace(korean, f" {english} ")
    return translated


def _unique_terms(values: Any) -> List[str]:
    if values is None:
        return []
    terms: List[str] = []
    seen: set[str] = set()
    for value in values:
        term = _pubmed_term(value)
        key = term.lower()
        if term and key not in seen:
            terms.append(term)
            seen.add(key)
    return terms


def _dedupe_queries(queries: List[str]) -> List[str]:
    deduped: List[str] = []
    seen: set[str] = set()
    for query in queries:
        cleaned = _clean_pubmed_query(query)
        key = cleaned.lower()
        if cleaned and key not in seen:
            deduped.append(cleaned)
            seen.add(key)
    return deduped


def _dedupe_pubmed_articles(articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    deduped: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for article in articles:
        if not isinstance(article, dict):
            continue
        key = str(article.get("pmid") or article.get("title") or "").strip().lower()
        if key and key not in seen:
            deduped.append(article)
            seen.add(key)
    return deduped


def _summarize_pubmed_evidence(
    state: ValidationState,
    pubmed_evidence: List[Dict[str, Any]],
    overall: str,
) -> str:
    if not pubmed_evidence:
        return ""

    llm = _create_llm()
    if llm:
        payload = {
            "overallStatus": overall,
            "savedDiseases": state.get("saved_diseases") or [],
            "savedPrescriptions": state.get("saved_prescriptions") or [],
            "candidatePrescriptions": state.get("candidate_prescriptions") or [],
            "symptoms": state.get("symptoms") or "",
            "articles": [
                {
                    "pmid": article.get("pmid"),
                    "title": article.get("title"),
                    "source": article.get("source"),
                    "pubdate": article.get("pubdate"),
                    "abstract": article.get("abstract") or article.get("abstractSnippet") or "",
                }
                for article in pubmed_evidence[:3]
            ],
        }
        prompt = f"""다음 PubMed 초록 내용을 진료 데이터 검증 근거로 4문장 이내 한국어로 요약하라.

주의:
- 논문이 직접적으로 현재 환자 처방을 승인한다고 단정하지 않는다.
- 초록에서 확인되는 질환/증상/약물/치료 관련 내용만 말한다.
- PMID를 최소 1개 포함한다.
- JSON이 아닌 평문 한 문단으로 답한다.

자료:
{json.dumps(payload, ensure_ascii=False)}
"""
        try:
            response = llm.invoke([
                SystemMessage(content="You summarize PubMed abstracts as cautious clinical validation evidence in Korean."),
                HumanMessage(content=prompt),
            ])
            summary = " ".join(str(response.content).split())
            if summary:
                return summary[:900]
        except Exception:
            pass

    return _fallback_pubmed_summary(pubmed_evidence)


def _fallback_pubmed_summary(pubmed_evidence: List[Dict[str, Any]]) -> str:
    lines = []
    for article in pubmed_evidence[:2]:
        title = str(article.get("title") or "").strip()
        pmid = str(article.get("pmid") or "").strip()
        snippet = str(article.get("abstractSnippet") or article.get("abstract") or "").strip()
        if not title:
            continue
        if snippet:
            lines.append(f"{title} (PMID {pmid}) 초록 내용: {_truncate_text(snippet, 260)}")
        else:
            lines.append(f"{title} (PMID {pmid})는 관련 문헌 후보이나 초록을 가져오지 못했습니다.")
    return " / ".join(lines)


def _format_pubmed_article(article: Dict[str, Any], include_abstract: bool = False) -> str:
    title = str(article.get("title") or "").strip()
    pmid = str(article.get("pmid") or "").strip()
    source = str(article.get("source") or "").strip()
    pubdate = str(article.get("pubdate") or "").strip()
    meta = ", ".join(part for part in [source, pubdate, f"PMID {pmid}" if pmid else ""] if part)
    citation = title
    if meta:
        citation = f"{citation} ({meta})"
    if include_abstract:
        snippet = str(article.get("abstractSnippet") or article.get("abstract") or "").strip()
        if snippet:
            citation = f"{citation} - 초록: {_truncate_text(snippet, 350)}"
    return citation


def _truncate_text(value: str, max_length: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= max_length:
        return text
    return text[: max_length - 3].rstrip() + "..."


def _build_pubmed_reference_query(state: ValidationState) -> str:
    xray_inference = state.get("xray_inference") or {}
    predicted = xray_inference.get("predictedDiseases") if isinstance(xray_inference, dict) else []
    if not isinstance(predicted, list):
        predicted = []
    xray_terms = _unique_terms(
        _pubmed_term(row.get("disease") or row.get("name") or row.get("label"))
        for row in predicted
        if isinstance(row, dict)
    )
    disease_terms = _unique_terms(
        _pubmed_term(row.get("name") or row.get("code") or "")
        for row in (state.get("saved_diseases") or [])
    )
    symptom_terms = _unique_terms(_pubmed_term(state.get("symptoms") or "").split())
    focus = (xray_terms or disease_terms or symptom_terms)[:3]
    return " ".join([*focus, "treatment"]).strip()[:500] or "clinical treatment"


def _build_pubmed_disease_query(state: ValidationState) -> str:
    xray_inference = state.get("xray_inference") or {}
    predicted = xray_inference.get("predictedDiseases") if isinstance(xray_inference, dict) else []
    if not isinstance(predicted, list):
        predicted = []
    xray_terms = _unique_terms(
        _pubmed_term(row.get("disease") or row.get("name") or row.get("label"))
        for row in predicted
        if isinstance(row, dict)
    )
    disease_terms = _unique_terms(
        _pubmed_term(row.get("name") or row.get("code") or "")
        for row in (state.get("saved_diseases") or [])
    )
    focus = (xray_terms or disease_terms)[:3]
    return " ".join([*focus, "diagnosis treatment"]).strip()[:500] or "clinical diagnosis treatment"


def _build_pubmed_prescription_query(state: ValidationState) -> str:
    prescription_terms = _unique_terms(
        _pubmed_term(row.get("name") or row.get("prescription_name") or row.get("code") or "")
        for row in (state.get("candidate_prescriptions") or state.get("saved_prescriptions") or [])
    )
    disease_terms = _unique_terms(
        _pubmed_term(row.get("name") or row.get("code") or "")
        for row in (state.get("saved_diseases") or [])
    )
    focus = [*prescription_terms[:2], *disease_terms[:1]]
    return " ".join([*focus, "indication"]).strip()[:500] or "medication indication"


def _normalize_prescription_candidates(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            continue
        normalized.append({
            "id": int(row.get("id") or 0),
            "rank": int(row.get("rank") or index),
            "prescription_code": row.get("prescription_code") or row.get("code") or "",
            "prescription_name": row.get("prescription_name") or row.get("name") or "",
            "reason": row.get("reason") or "",
            "confidence_score": float(row.get("confidence_score") or row.get("confidenceScore") or 0),
            "dose": int(row.get("dose") or 0),
            "time": int(row.get("time") or 0),
            "days": int(row.get("days") or 0),
        })
    return normalized


def _build_graph():
    workflow = StateGraph(ValidationState)
    workflow.add_node("load_context", _load_context)
    workflow.add_node("disease_validation_agent", _disease_validation_agent)
    workflow.add_node("prescription_validation_agent", _prescription_validation_agent)
    workflow.add_node("prescription_candidate_lookup", _prescription_candidate_lookup)
    workflow.add_node("finalize_validation", _finalize_validation)

    workflow.set_entry_point("load_context")
    workflow.add_edge("load_context", "disease_validation_agent")
    workflow.add_edge("disease_validation_agent", "prescription_validation_agent")
    workflow.add_conditional_edges(
        "prescription_validation_agent",
        _route_next_action,
        {
            "find_prescription": "prescription_candidate_lookup",
            "finalize": "finalize_validation",
        },
    )
    workflow.add_edge("prescription_candidate_lookup", "finalize_validation")
    workflow.add_edge("finalize_validation", END)
    return workflow.compile()


def _load_context(state: ValidationState) -> ValidationState:
    state["xray_check"] = xray_result_loader.invoke({
        "xray_inference": state.get("xray_inference"),
    })
    return state


def _disease_validation_agent(state: ValidationState) -> ValidationState:
    state["disease_check"] = disease_validator.invoke({
        "symptoms": state.get("symptoms"),
        "saved_diseases": state.get("saved_diseases", []),
        "xray_inference": state.get("xray_inference"),
    })
    return state


def _prescription_validation_agent(state: ValidationState) -> ValidationState:
    state["prescription_check"] = prescription_validator.invoke({
        "symptoms": state.get("symptoms"),
        "saved_diseases": state.get("saved_diseases", []),
        "saved_prescriptions": state.get("saved_prescriptions", []),
    })
    return state


def _route_next_action(state: ValidationState) -> str:
    disease_status = (state.get("disease_check") or {}).get("status")
    prescription_status = (state.get("prescription_check") or {}).get("status")
    if disease_status in {"MISMATCH", "PARTIAL_MATCH"}:
        return "find_prescription"
    if prescription_status in {"QUESTIONABLE", "UNRELATED"}:
        return "find_prescription"
    return "finalize"


def _prescription_candidate_lookup(state: ValidationState) -> ValidationState:
    patient_id = str((state.get("patient_summary") or {}).get("patientId") or "")
    result = prescription_finder.invoke({
        "patient_id": patient_id,
        "diseases": state.get("saved_diseases", []),
        "symptoms": state.get("symptoms"),
    })
    state["candidate_prescriptions"] = result.get("candidatePrescriptions") or []
    return state


def _finalize_validation(state: ValidationState) -> ValidationState:
    state["final_result"] = _llm_finalize(state) or _rule_based_finalize(state)
    return state


def _llm_finalize(state: ValidationState) -> Optional[Dict[str, Any]]:
    llm = _create_llm()
    if not llm:
        return None

    payload = _compact_state(state)
    user_prompt = f"""다음 검증 컨텍스트를 바탕으로 최종 검증 결과를 작성하라.

응답 스키마:
{{
  "overallStatus": "PASS | WARNING | CRITICAL | NEEDS_REVIEW",
  "summary": "검증 요약",
  "reason": "overallStatus를 선택한 핵심 이유. checks와 suspectedIssues의 근거를 1~2문장으로 요약",
  "checks": [
    {{
      "type": "DISEASE_XRAY_CONSISTENCY | DISEASE_PRESCRIPTION_CONSISTENCY | SYMPTOM_DISEASE_CONSISTENCY | SYMPTOM_XRAY_CONSISTENCY | DATA_QUALITY",
      "status": "PASS | WARNING | CRITICAL | INSUFFICIENT_DATA",
      "message": "검증 내용 요약",
      "evidence": ["판단 근거"],
      "relatedDiseases": [],
      "relatedPrescriptions": [],
      "recommendedAction": "의료진 확인 조치"
    }}
  ],
  "suspectedIssues": [
    {{
      "severity": "LOW | MEDIUM | HIGH",
      "category": "POSSIBLE_CODE_ERROR | POSSIBLE_MISSING_DISEASE | POSSIBLE_UNRELATED_PRESCRIPTION | INSUFFICIENT_DATA | XRAY_CONFLICT",
      "description": "의심 문제",
      "reason": "판단 이유"
    }}
  ],
  "suggestedReviewItems": ["확인 항목"],
  "candidatePrescriptions": [],
  "shouldNotifyDoctor": true,
  "shouldBlockAutoPrescription": false
}}

검증 컨텍스트:
{json.dumps(payload, ensure_ascii=False)}
"""
    try:
        response = llm.invoke([
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ])
        parsed = _parse_json_object(str(response.content))
        if parsed:
            parsed["candidatePrescriptions"] = state.get("candidate_prescriptions", [])
            return _normalize_final_result(parsed)
    except Exception:
        return None
    return None


def _rule_based_finalize(state: ValidationState) -> Dict[str, Any]:
    disease_check = state.get("disease_check") or {}
    prescription_check = state.get("prescription_check") or {}
    disease_status = disease_check.get("status")
    prescription_status = prescription_check.get("status")

    suspected_issues: List[Dict[str, Any]] = []
    checks: List[Dict[str, Any]] = []

    if disease_status in {"MISMATCH", "PARTIAL_MATCH"}:
        severity = "HIGH" if disease_status == "MISMATCH" else "MEDIUM"
        suspected_issues.append({
            "severity": severity,
            "category": "XRAY_CONFLICT",
            "description": "저장 상병과 X-ray 추론 결과의 불일치 가능성이 있습니다.",
            "reason": "; ".join(map(str, disease_check.get("evidence") or [])),
        })
        checks.append({
            "type": "DISEASE_XRAY_CONSISTENCY",
            "status": "CRITICAL" if severity == "HIGH" else "WARNING",
            "message": "X-ray 추론 상병 일부가 저장 상병에 반영되지 않았을 수 있습니다.",
            "evidence": disease_check.get("evidence") or [],
            "relatedDiseases": state.get("saved_diseases", []),
            "relatedPrescriptions": [],
            "recommendedAction": "의료진이 저장 상병과 영상판독 결과를 함께 재확인하세요.",
        })

    if prescription_status == "INSUFFICIENT_DATA":
        checks.append({
            "type": "DISEASE_PRESCRIPTION_CONSISTENCY",
            "status": "INSUFFICIENT_DATA",
            "message": "처방 검증에 필요한 데이터가 부족합니다.",
            "evidence": prescription_check.get("evidence") or [],
            "relatedDiseases": state.get("saved_diseases", []),
            "relatedPrescriptions": state.get("saved_prescriptions", []),
            "recommendedAction": "상병, 증상, 처방 입력이 모두 저장되었는지 확인하세요.",
        })
    elif prescription_status:
        checks.append({
            "type": "DISEASE_PRESCRIPTION_CONSISTENCY",
            "status": "PASS",
            "message": "저장 상병/증상과 처방 검증에 필요한 기본 데이터가 확인되었습니다.",
            "evidence": prescription_check.get("evidence") or [],
            "relatedDiseases": state.get("saved_diseases", []),
            "relatedPrescriptions": state.get("saved_prescriptions", []),
            "recommendedAction": "의료진 최종 검토를 유지하세요.",
        })

    if not checks:
        checks.append({
            "type": "DATA_QUALITY",
            "status": "PASS",
            "message": "검증 가능한 범위에서 큰 불일치가 발견되지 않았습니다.",
            "evidence": ["기본 검증 규칙을 통과했습니다."],
            "relatedDiseases": state.get("saved_diseases", []),
            "relatedPrescriptions": state.get("saved_prescriptions", []),
            "recommendedAction": "일반적인 의료진 검토 절차를 따르세요.",
        })

    if any(issue.get("severity") == "HIGH" for issue in suspected_issues):
        overall = "CRITICAL"
    elif suspected_issues:
        overall = "WARNING"
    elif any(check.get("status") == "INSUFFICIENT_DATA" for check in checks):
        overall = "NEEDS_REVIEW"
    else:
        overall = "PASS"

    return _normalize_final_result({
        "overallStatus": overall,
        "summary": _summary_for(overall),
        "reason": _reason_from_checks(checks, suspected_issues),
        "checks": checks,
        "suspectedIssues": suspected_issues,
        "suggestedReviewItems": _review_items(overall),
        "candidatePrescriptions": state.get("candidate_prescriptions", []),
        "shouldNotifyDoctor": overall in {"WARNING", "CRITICAL", "NEEDS_REVIEW"},
        "shouldBlockAutoPrescription": overall == "CRITICAL",
    })


def _compact_state(state: ValidationState) -> Dict[str, Any]:
    return {
        "eventId": state.get("event_id"),
        "eventType": state.get("event_type"),
        "historyId": state.get("history_id"),
        "patientSummary": state.get("patient_summary"),
        "symptoms": state.get("symptoms"),
        "savedDiseases": state.get("saved_diseases"),
        "savedPrescriptions": state.get("saved_prescriptions"),
        "xrayInference": state.get("xray_inference"),
        "xrayCheck": state.get("xray_check"),
        "diseaseCheck": state.get("disease_check"),
        "prescriptionCheck": state.get("prescription_check"),
        "candidatePrescriptions": state.get("candidate_prescriptions"),
    }


def _parse_json_object(raw: str) -> Optional[Dict[str, Any]]:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start:end + 1]
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _normalize_final_result(result: Dict[str, Any]) -> Dict[str, Any]:
    allowed = {"PASS", "WARNING", "CRITICAL", "NEEDS_REVIEW"}
    overall = str(result.get("overallStatus") or "NEEDS_REVIEW").upper()
    if overall not in allowed:
        overall = "NEEDS_REVIEW"
    return {
        "jobId": result.get("jobId"),
        "historyId": result.get("historyId"),
        "overallStatus": overall,
        "summary": str(result.get("summary") or _summary_for(overall)),
        "reason": str(result.get("reason") or _reason_from_checks(
            result.get("checks") if isinstance(result.get("checks"), list) else [],
            result.get("suspectedIssues") if isinstance(result.get("suspectedIssues"), list) else [],
        )),
        "recommendedPrescriptions": (
            result.get("recommendedPrescriptions")
            if isinstance(result.get("recommendedPrescriptions"), list)
            else result.get("candidatePrescriptions")
            if isinstance(result.get("candidatePrescriptions"), list)
            else []
        ),
        "validation": result.get("validation") if isinstance(result.get("validation"), dict) else {},
        "reasoningTrace": result.get("reasoningTrace") if isinstance(result.get("reasoningTrace"), list) else [],
        "checks": result.get("checks") if isinstance(result.get("checks"), list) else [],
        "suspectedIssues": result.get("suspectedIssues") if isinstance(result.get("suspectedIssues"), list) else [],
        "suggestedReviewItems": (
            result.get("suggestedReviewItems")
            if isinstance(result.get("suggestedReviewItems"), list)
            else _review_items(overall)
        ),
        "candidatePrescriptions": (
            result.get("candidatePrescriptions")
            if isinstance(result.get("candidatePrescriptions"), list)
            else []
        ),
        "shouldNotifyDoctor": bool(result.get("shouldNotifyDoctor", overall != "PASS")),
        "shouldBlockAutoPrescription": bool(result.get("shouldBlockAutoPrescription", overall == "CRITICAL")),
    }


def _summary_for(overall: str) -> str:
    return {
        "PASS": "검증 가능한 범위에서 큰 불일치가 발견되지 않았습니다.",
        "WARNING": "일부 데이터에서 의료진 확인이 필요한 불일치 가능성이 있습니다.",
        "CRITICAL": "상병, 처방 또는 X-ray 추론 결과 사이에 강한 불일치 가능성이 있습니다.",
        "NEEDS_REVIEW": "자동 검증에 필요한 데이터가 부족하여 의료진 검토가 필요합니다.",
    }.get(overall, "의료진 검토가 필요합니다.")


def _reason_from_checks(checks: List[Dict[str, Any]], suspected_issues: List[Dict[str, Any]]) -> str:
    issue_reasons = [
        str(issue.get("reason") or issue.get("description") or "").strip()
        for issue in suspected_issues
        if str(issue.get("reason") or issue.get("description") or "").strip()
    ]
    if issue_reasons:
        return " / ".join(issue_reasons[:2])

    check_reasons = [
        str(check.get("message") or check.get("recommendedAction") or "").strip()
        for check in checks
        if str(check.get("message") or check.get("recommendedAction") or "").strip()
    ]
    if check_reasons:
        return " / ".join(check_reasons[:2])

    return "검증 결과를 판단할 세부 근거가 충분하지 않아 기본 요약을 사용했습니다."


def _with_pubmed_reason(reason: str, pubmed_evidence: List[Dict[str, Any]]) -> str:
    evidence_lines = []
    for article in pubmed_evidence[:3]:
        citation = _format_pubmed_article(article, include_abstract=True)
        if not citation:
            continue
        evidence_lines.append(citation)

    if not evidence_lines:
        return reason

    pubmed_reason = "PubMed 근거 후보: " + " / ".join(evidence_lines)
    if reason:
        return f"{reason} {pubmed_reason}"
    return pubmed_reason


def _review_items(overall: str) -> List[str]:
    if overall == "PASS":
        return []
    return [
        "저장 상병 코드와 상병명을 확인하세요.",
        "저장 처방이 현재 상병 및 증상과 관련 있는지 확인하세요.",
        "X-ray 추론 결과와 실제 영상 소견을 함께 확인하세요.",
    ]
