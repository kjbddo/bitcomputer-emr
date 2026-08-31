"""PubMed 질의 생성·정규화·요약·포매팅.

`agent.py` 에서 떼어냈다. 이 모듈은 **도구를 부르지 않는다** — 검색 자체(그리고
그 트레이스 기록)는 `agent.py` 가 한다. 여기 있는 것은 순수 문자열 가공과,
게이트웨이를 부르는 두 함수뿐이다.

두 게이트웨이 함수는 클라이언트를 직접 만들지 않고 `llm_factory` 를 주입받는다.
`certificate_verification.py` 가 `call_llm`/`clock` 을 주입해 순수 함수로 남긴
것과 같은 이유다 — 그래야 호출부(`agent.py`)가 대역을 끼워 넣을 수 있고,
이 모듈이 환경변수를 몰라도 된다.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from langchain_core.messages import HumanMessage, SystemMessage

from .gateway import ModelCallLedger, parse_json_object
from .prompts import (
    PUBMED_QUERY_SYSTEM,
    PUBMED_SUMMARY_SYSTEM,
    pubmed_query_prompt,
    pubmed_summary_payload,
    pubmed_summary_prompt,
)
from .state import ValidationState, compact_state

logger = logging.getLogger("validation_agent.pubmed")

LlmFactory = Callable[[], Optional[Any]]

# 규칙 기반 질의 빌더가 쓰는 한→영 사전. 15항목뿐이고 그 한계가 곧 모델 호출을
# 남긴 이유다 — 이 사전으로는 임상 맥락을 반영한 질의를 만들 수 없다.
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


# ---------------------------------------------------------------------------
# 모델 호출 1/2 — 질의 생성
# ---------------------------------------------------------------------------

def generate_queries_with_llm(
    state: ValidationState,
    reason: str,
    ledger: ModelCallLedger,
    llm_factory: LlmFactory,
    provider: str = "real",
) -> Tuple[List[str], str]:
    """PubMed 검색어를 모델로 생성한다. `(질의 목록, 출처)` 를 돌려준다.

    출처는 호출부가 **트레이스 표기에만** 쓴다 — `llmStatus` 는 오직 `ledger`
    에서 나오고, 호출부가 이 반환값을 다시 장부에 넣으면 같은 호출이 두 번
    세어진다. 그 오염이 llmStatus 를 거짓으로 만드는 경로였다(Task 6).
    """
    if provider == "stub":
        # stub 모드는 게이트웨이를 부르지 않는다. 규칙 기반 빌더가 질의를 만들고,
        # llmStatus 는 그 사실대로 "stub" 이 된다.
        return [], ledger.record("pubmed_query_generation", "stub")

    llm = llm_factory()
    if not llm:
        return [], ledger.record("pubmed_query_generation", "fallback")

    prompt = pubmed_query_prompt(compact_state(state), reason)
    try:
        response = llm.invoke([
            SystemMessage(content=PUBMED_QUERY_SYSTEM),
            HumanMessage(content=prompt),
        ])
        parsed = parse_json_object(str(response.content))
    except Exception as exc:  # noqa: BLE001
        # 타입만 로그한다 — 메시지/트레이스백은 LLM_GATEWAY_BASE_URL 에 잘못
        # 심긴 자격증명을 실을 수 있다(GC-7).
        logger.warning("게이트웨이 PubMed 쿼리 생성 실패, 폴백으로 전환: %s", type(exc).__name__)
        return [], ledger.record("pubmed_query_generation", "fallback")

    if not parsed or not isinstance(parsed.get("queries"), list):
        return [], ledger.record("pubmed_query_generation", "fallback")
    queries = dedupe_queries([
        query for query in parsed["queries"]
        if isinstance(query, str) and clean_query(query)
    ])
    if not queries:
        return [], ledger.record("pubmed_query_generation", "fallback")
    return queries, ledger.record("pubmed_query_generation", "llm")


# ---------------------------------------------------------------------------
# 모델 호출 2/2 — 근거 요약
# ---------------------------------------------------------------------------

def summarize_evidence(
    state: ValidationState,
    articles: List[Dict[str, Any]],
    overall: str,
    ledger: ModelCallLedger,
    llm_factory: LlmFactory,
    provider: str = "real",
) -> Tuple[str, str]:
    """`(요약문, 출처)` 를 돌려준다.

    출처가 `"llm"` 이 아니면 호출부는 `checks[]` 메시지에 "(규칙 기반)" 라벨을
    붙인다 — 문자열 조합 요약이 모델이 쓴 것처럼 노출되면 안 된다.
    """
    if not articles:
        # 요약할 것이 없으면 호출 자체가 없다. 없는 호출을 장부에 적지 않는다.
        return "", "fallback"

    if provider == "stub":
        ledger.record("pubmed_evidence_summary", "stub")
        return fallback_summary(articles), "stub"

    llm = llm_factory()
    if not llm:
        ledger.record("pubmed_evidence_summary", "fallback")
        return fallback_summary(articles), "fallback"

    payload = pubmed_summary_payload(overall, compact_state(state), articles)
    try:
        response = llm.invoke([
            SystemMessage(content=PUBMED_SUMMARY_SYSTEM),
            HumanMessage(content=pubmed_summary_prompt(payload)),
        ])
        summary = " ".join(str(response.content).split())
        if summary:
            ledger.record("pubmed_evidence_summary", "llm")
            return summary[:900], "llm"
    except Exception as exc:  # noqa: BLE001
        logger.warning("게이트웨이 PubMed 요약 실패, 규칙 기반으로 전환: %s", type(exc).__name__)

    ledger.record("pubmed_evidence_summary", "fallback")
    return fallback_summary(articles), "fallback"


def fallback_summary(articles: List[Dict[str, Any]]) -> str:
    lines = []
    for article in articles[:2]:
        title = str(article.get("title") or "").strip()
        pmid = str(article.get("pmid") or "").strip()
        snippet = str(article.get("abstractSnippet") or article.get("abstract") or "").strip()
        if not title:
            continue
        if snippet:
            lines.append(f"{title} (PMID {pmid}) 초록 내용: {truncate_text(snippet, 260)}")
        else:
            lines.append(f"{title} (PMID {pmid})는 관련 문헌 후보이나 초록을 가져오지 못했습니다.")
    return " / ".join(lines)


# ---------------------------------------------------------------------------
# 규칙 기반 질의 빌더
# ---------------------------------------------------------------------------

def build_query(state: ValidationState, reason: str) -> str:
    xray_terms = _xray_terms(state)
    suspicious_terms = unique_terms(
        pubmed_term(row.get("disease") or row.get("name") or row.get("label"))
        for row in ((state.get("disease_check") or {}).get("suspiciousItems") or [])
        if isinstance(row, dict)
    )
    disease_terms = _disease_terms(state)
    prescription_terms = _prescription_terms(state)
    symptoms = unique_terms(pubmed_term(state.get("symptoms") or "").split())

    # PubMed ESearch treats overly long mixed clinical text as a very narrow query.
    # Use the most important inferred disease plus prescription/treatment terms first.
    disease_focus = (xray_terms or suspicious_terms or disease_terms)[:2]
    prescription_focus = prescription_terms[:2]
    symptom_focus = symptoms[:2] if not prescription_focus else []
    query = " ".join([*disease_focus, *prescription_focus, *symptom_focus, "treatment"]).strip()
    return query[:500] or "pneumonia treatment"


def build_reference_query(state: ValidationState) -> str:
    symptom_terms = unique_terms(pubmed_term(state.get("symptoms") or "").split())
    focus = (_xray_terms(state) or _disease_terms(state) or symptom_terms)[:3]
    return " ".join([*focus, "treatment"]).strip()[:500] or "clinical treatment"


def build_disease_query(state: ValidationState) -> str:
    focus = (_xray_terms(state) or _disease_terms(state))[:3]
    return " ".join([*focus, "diagnosis treatment"]).strip()[:500] or "clinical diagnosis treatment"


def build_prescription_query(state: ValidationState) -> str:
    focus = [*_prescription_terms(state)[:2], *_disease_terms(state)[:1]]
    return " ".join([*focus, "indication"]).strip()[:500] or "medication indication"


def build_query_candidates(
    state: ValidationState,
    reason: str,
    llm_queries: List[str],
) -> List[str]:
    """모델 질의를 앞에, 규칙 기반 빌더 질의를 뒤에 놓은 후보 목록."""
    queries: List[str] = list(llm_queries)
    queries.append(build_query(state, reason))
    queries.append(build_reference_query(state))
    queries.append(build_disease_query(state))
    queries.append(build_prescription_query(state))
    return dedupe_queries(queries)


def _xray_terms(state: ValidationState) -> List[str]:
    xray_inference = state.get("xray_inference") or {}
    predicted = xray_inference.get("predictedDiseases") if isinstance(xray_inference, dict) else []
    if not isinstance(predicted, list):
        predicted = []
    return unique_terms(
        pubmed_term(row.get("disease") or row.get("name") or row.get("label"))
        for row in predicted
        if isinstance(row, dict)
    )


def _disease_terms(state: ValidationState) -> List[str]:
    return unique_terms(
        pubmed_term(row.get("name") or row.get("code") or "")
        for row in (state.get("saved_diseases") or [])
    )


def _prescription_terms(state: ValidationState) -> List[str]:
    return unique_terms(
        pubmed_term(row.get("name") or row.get("prescription_name") or row.get("code") or "")
        for row in (state.get("candidate_prescriptions") or state.get("saved_prescriptions") or [])
    )


# ---------------------------------------------------------------------------
# 문자열 가공
# ---------------------------------------------------------------------------

def clean_query(query: str) -> str:
    query = " ".join(str(query or "").replace("\n", " ").split())
    tokens: List[str] = []
    seen: set[str] = set()
    for token in query.split():
        key = token.lower()
        if key not in seen:
            tokens.append(token)
            seen.add(key)
    return " ".join(tokens)[:500]


def pubmed_term(value: Any) -> str:
    text = translate_terms(str(value or ""))
    ascii_text = text.encode("ascii", "ignore").decode("ascii")
    ascii_text = ascii_text.replace("_", " ")
    ascii_text = re.sub(r"[^A-Za-z0-9 +\"()/-]+", " ", ascii_text)
    ascii_text = ascii_text.replace("/", " ")
    return " ".join(ascii_text.split())


def translate_terms(text: str) -> str:
    translated = text
    for korean, english in KOREAN_PUBMED_TERMS.items():
        translated = translated.replace(korean, f" {english} ")
    return translated


def unique_terms(values: Any) -> List[str]:
    if values is None:
        return []
    terms: List[str] = []
    seen: set[str] = set()
    for value in values:
        term = pubmed_term(value)
        key = term.lower()
        if term and key not in seen:
            terms.append(term)
            seen.add(key)
    return terms


def dedupe_queries(queries: List[str]) -> List[str]:
    deduped: List[str] = []
    seen: set[str] = set()
    for query in queries:
        cleaned = clean_query(query)
        key = cleaned.lower()
        if cleaned and key not in seen:
            deduped.append(cleaned)
            seen.add(key)
    return deduped


def dedupe_articles(articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
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


def format_article(article: Dict[str, Any], include_abstract: bool = False) -> str:
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
            citation = f"{citation} - 초록: {truncate_text(snippet, 350)}"
    return citation


def truncate_text(value: str, max_length: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= max_length:
        return text
    return text[: max_length - 3].rstrip() + "..."
