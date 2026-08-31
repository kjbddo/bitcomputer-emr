from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional

import httpx
from langchain_core.tools import tool


DISEASE_KEYWORDS = {
    "pneumonia": ["폐렴", "pneumonia"],
    "edema": ["부종", "edema"],
    "cardiomegaly": ["심비대", "cardiomegaly"],
    "pleural_effusion": ["흉수", "pleural", "effusion"],
    "atelectasis": ["무기폐", "atelectasis"],
    "pneumothorax": ["기흉", "pneumothorax"],
    "consolidation": ["경화", "consolidation"],
    "lung_opacity": ["폐음영", "opacity"],
}


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _disease_name(row: Dict[str, Any]) -> str:
    return _text(row.get("name") or row.get("disease") or row.get("code"))


def _xray_disease_name(row: Dict[str, Any]) -> str:
    return _text(row.get("disease") or row.get("name") or row.get("label"))


def _xray_score(row: Dict[str, Any]) -> float:
    try:
        return float(row.get("score") or row.get("confidence") or 0)
    except (TypeError, ValueError):
        return 0.0


def _high_confidence_xray(xray_inference: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not xray_inference:
        return []
    raw = xray_inference.get("predictedDiseases") or []
    if not isinstance(raw, list):
        return []
    return [
        row for row in raw
        if isinstance(row, dict) and _xray_score(row) >= 0.35 and _xray_disease_name(row)
    ]


def _matches_saved_disease(xray_name: str, saved_diseases: List[Dict[str, Any]]) -> bool:
    saved_text = " ".join(_disease_name(row).lower() for row in saved_diseases)
    normalized = xray_name.strip().lower().replace(" ", "_")
    keywords = DISEASE_KEYWORDS.get(normalized, [normalized, xray_name.lower()])
    return any(keyword.lower() in saved_text for keyword in keywords)


@tool
def xray_result_loader(xray_inference: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Return the X-ray inference result already loaded by Spring for this validation event."""
    if not xray_inference:
        return {
            "status": "INSUFFICIENT_DATA",
            "evidence": ["저장된 X-ray 추론 결과가 없습니다."],
            "xrayInference": None,
        }
    return {
        "status": "LOADED",
        "evidence": ["Spring DB에 저장된 최신 영상판독 결과를 사용합니다."],
        "xrayInference": xray_inference,
    }


@tool
def disease_validator(
    symptoms: Optional[str],
    saved_diseases: List[Dict[str, Any]],
    xray_inference: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Validate consistency between saved diseases, symptoms, and X-ray inference."""
    high_xray = _high_confidence_xray(xray_inference)
    if not saved_diseases and not high_xray:
        return {
            "status": "INSUFFICIENT_DATA",
            "evidence": ["저장 상병과 X-ray 추론 결과가 모두 부족합니다."],
            "suspiciousItems": [],
        }

    missing = []
    for row in high_xray:
        name = _xray_disease_name(row)
        if not _matches_saved_disease(name, saved_diseases):
            missing.append({
                "disease": name,
                "score": _xray_score(row),
                "reason": row.get("reason"),
            })

    evidence = []
    if saved_diseases:
        evidence.append(f"저장 상병 {len(saved_diseases)}건이 있습니다.")
    if high_xray:
        evidence.append(f"점수 0.35 이상 X-ray 추론 상병 {len(high_xray)}건이 있습니다.")
    if symptoms:
        evidence.append(f"증상/진료 기록: {symptoms}")

    if missing and saved_diseases:
        status = "MISMATCH"
    elif missing:
        status = "PARTIAL_MATCH"
    else:
        status = "MATCH"

    return {
        "status": status,
        "evidence": evidence,
        "suspiciousItems": missing,
    }


@tool
def prescription_validator(
    symptoms: Optional[str],
    saved_diseases: List[Dict[str, Any]],
    saved_prescriptions: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Validate whether saved prescriptions can be reviewed against saved diseases and symptoms."""
    if not saved_prescriptions:
        return {
            "status": "INSUFFICIENT_DATA",
            "evidence": ["저장된 처방이 없습니다."],
            "suspiciousItems": [],
        }
    if not saved_diseases and not symptoms:
        return {
            "status": "INSUFFICIENT_DATA",
            "evidence": ["처방은 있으나 상병과 증상 정보가 부족합니다."],
            "suspiciousItems": saved_prescriptions,
        }

    return {
        "status": "APPROPRIATE",
        "evidence": [
            f"저장 처방 {len(saved_prescriptions)}건, 저장 상병 {len(saved_diseases)}건을 확인했습니다.",
            # 이 문장은 evidence[] 를 타고 checks[] 와 트레이스로 의사 화면에 간다.
            # 이전 문구("상세 약물 적합성 판단은 LLM 최종 검토 단계에서 근거와 함께
            # 보수적으로 평가합니다")가 가리키던 단계는 도달 불가능한 `_llm_finalize`
            # 였고(F-M2), 그 단계는 삭제됐다. 하지도 않을 일을 약속하지 않는다.
            "이 검사는 저장 처방과 상병/증상이 함께 존재하는지만 확인했습니다 — "
            "약물 적합성은 판단하지 않습니다.",
        ],
        "suspiciousItems": [],
    }


def _int_or_zero(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _graph_lookup_loaded(body: Dict[str, Any]) -> Dict[str, Any]:
    """prescription_api 의 ArangoDB 조회 플래그를 화면까지 갈 형태로 정리한다(F-M6).

    그래프가 빈손이면 추천은 모델의 일반지식에만 기대게 된다. 그 차이가 화면에
    보이지 않으면 의사는 두 경우를 구분할 수 없으므로, 로그가 아니라 관측값으로
    싣는다(설계 문서 §3.2).
    """
    arango_count = _int_or_zero(body.get("arango_top_rx_count"))
    cohort_count = _int_or_zero(body.get("cohort_rx_count"))

    evidence: List[str] = []
    if arango_count:
        evidence.append(f"환자 그래프에서 이 환자의 과거 처방 {arango_count}건을 참고했습니다.")
    else:
        evidence.append("환자 그래프에서 이 환자의 과거 처방을 찾지 못했습니다 (0건).")
    if cohort_count:
        evidence.append(f"같은 상병 코호트의 처방 {cohort_count}건을 참고했습니다.")
    else:
        evidence.append("같은 상병 코호트의 처방을 그래프에서 찾지 못했습니다 (0건).")

    return {
        "status": "LOADED",
        "usedArangoTopRx": bool(body.get("used_arango_top_rx")),
        "arangoTopRxCount": arango_count,
        "usedCohortRx": bool(body.get("used_cohort_rx")),
        "cohortRxCount": cohort_count,
        "foundNothing": not (arango_count or cohort_count),
        "evidence": evidence,
    }


def _graph_lookup_failed(error: str) -> Dict[str, Any]:
    """조회 실패는 "0건" 이 아니다.

    GC-3 fail-closed: 확인하지 못한 것을 "확인했는데 없었다" 로 읽히게 하면
    안 된다. `foundNothing` 은 False 로 남기고 status 로만 구분한다.
    """
    return {
        "status": "FAILED",
        "usedArangoTopRx": False,
        "arangoTopRxCount": 0,
        "usedCohortRx": False,
        "cohortRxCount": 0,
        "foundNothing": False,
        "evidence": [f"처방 그래프를 조회하지 못했습니다: {error}"],
    }


@tool
def prescription_finder(
    patient_id: str,
    diseases: List[Dict[str, Any]],
    symptoms: Optional[str],
) -> Dict[str, Any]:
    """Fetch reference prescription candidates from the existing prescription RAG service."""
    base_url = os.environ.get("PRESCRIPTION_AGENT_BASE_URL", "http://prescription-api:8001")
    path = os.environ.get("PRESCRIPTION_AGENT_PATH", "/api/agent/prescription/recommend")
    disease_codes = [
        str(row.get("code")).strip()
        for row in diseases
        if row.get("code") is not None and str(row.get("code")).strip()
    ]
    payload = {
        "patient_id": patient_id,
        "symptoms": symptoms or "",
        "history": "",
        "top_rx": [],
        "similar_outcomes": "",
        "disease_codes": disease_codes,
        "fetch_top_rx_from_arango": True,
        "fetch_cohort_rx_from_arango": True,
    }

    # 최종 리뷰 IMPORTANT: prescription-api 자신의 게이트웨이 호출 총 예산
    # (LLM_GATEWAY_TIMEOUT_SECONDS, 기본 180s) 보다 짧으면 이 호출이 먼저
    # 포기해버려 prescription_finder 가 게이트웨이 처리 도중에 "실패"로
    # 기록된다 — prescription-api 는 여전히 응답을 만들고 있는데도. 이
    # 호출자의 타임아웃은 prescription-api 의 총 예산과 맞추거나 더 커야
    # 한다(infra/.env.example 의 LLM_GATEWAY_TIMEOUT_SECONDS 주석 참고).
    timeout = float(os.environ.get("PRESCRIPTION_AGENT_TIMEOUT_SECONDS", "180"))
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(f"{base_url}{path}", json=payload)
            response.raise_for_status()
            body = response.json()
    except Exception as exc:  # noqa: BLE001 - tool result should capture external service failures
        return {
            "status": "FAILED",
            "evidence": [f"처방 RAG 호출 실패: {exc}"],
            "candidatePrescriptions": [],
            "recommendationLlmStatus": "fallback",
            "recommendationVerification": None,
            "graphLookup": _graph_lookup_failed(str(exc)),
            # 관문을 돌리지 못했다. clear 를 지어내면 "확인해 보니 해당 없음" 이
            # 되어 이 부품이 있는 이유가 사라진다(renal_gate.py 모듈 주석).
            "recommendationRenalGate": None,
        }

    graph_lookup = _graph_lookup_loaded(body)
    return {
        "status": "LOADED",
        "evidence": [
            "기존 처방 RAG에서 참고 처방 후보를 조회했습니다.",
            *graph_lookup["evidence"],
        ],
        "candidatePrescriptions": body.get("prescriptions") or [],
        # ArangoDB 처방 그래프 조회 결과(F-M6). 이 스텝의 근거 출처이지 검증
        # 판정이 아니므로 최상위 상태와 섞지 않고 validation.graphLookup 으로만
        # 나간다 — recommendationVerification 과 같은 원칙.
        "graphLookup": graph_lookup,
        # 처방 RAG 자신이 모델을 썼는지. 이 스텝의 페이로드 출처이지, 검증 결정의
        # 출처가 아니다 — 최상위 llmStatus 에 섞으면 안 된다(Task 6 회귀).
        "recommendationLlmStatus": body.get("llmStatus"),
        # prescription_api 자신의 검증 결과. 이 스텝의 근거 정보이지
        # 검증 에이전트 자신의 판정이 아니다 — 최상위에 섞지 않는다.
        "recommendationVerification": body.get("verification"),
        # prescription_api 의 신기능 금기 관문(services/prescription/renal_gate.py).
        # warn / clear / unknown 세 결과와 항목별 evidence 를 그대로 넘긴다 —
        # 여기서 요약하거나 outcome 만 뽑으면 `clear` 가 뜻하는 "이 표의 범위
        # 안에서 해당 없음" 이 "안전함" 으로 바뀐다.
        "recommendationRenalGate": body.get("renalGate"),
    }


@tool
def pubmed_loader(query: str, max_results: int = 3) -> Dict[str, Any]:
    """Search PubMed evidence for disease/symptom/prescription combinations."""
    if not query:
        return {
            "status": "INSUFFICIENT_DATA",
            "evidence": [],
            "articles": [],
        }
    try:
        with httpx.Client(timeout=12.0) as client:
            search = client.get(
                "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
                params={
                    "db": "pubmed",
                    "term": query,
                    "retmode": "json",
                    "retmax": max_results,
                },
            )
            search.raise_for_status()
            ids = search.json().get("esearchresult", {}).get("idlist", [])
            if not ids:
                return {"status": "NO_RESULT", "evidence": [f"PubMed 검색 결과 없음: {query}"], "articles": []}
            summary = client.get(
                "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
                params={"db": "pubmed", "id": ",".join(ids), "retmode": "json"},
            )
            summary.raise_for_status()
            result = summary.json().get("result", {})
            abstracts = _fetch_pubmed_abstracts(client, ids)
            articles = []
            for pmid in ids:
                item = result.get(pmid, {})
                abstract = abstracts.get(pmid, "")
                articles.append({
                    "pmid": pmid,
                    "title": item.get("title", ""),
                    "source": item.get("source", ""),
                    "pubdate": item.get("pubdate", ""),
                    "abstract": abstract,
                    "abstractSnippet": _truncate_text(abstract, 700),
                })
            return {
                "status": "LOADED",
                "evidence": [f"PubMed에서 {len(articles)}건의 근거 후보를 조회했습니다."],
                "articles": articles,
            }
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "FAILED",
            "evidence": [f"PubMed 검색 실패: {exc}"],
            "articles": [],
        }


def _fetch_pubmed_abstracts(client: httpx.Client, ids: List[str]) -> Dict[str, str]:
    if not ids:
        return {}
    try:
        response = client.get(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
            params={"db": "pubmed", "id": ",".join(ids), "retmode": "xml"},
        )
        response.raise_for_status()
    except Exception:
        return {}

    try:
        root = ET.fromstring(response.text)
    except ET.ParseError:
        return {}

    abstracts: Dict[str, str] = {}
    for article in root.findall(".//PubmedArticle"):
        pmid = article.findtext(".//PMID") or ""
        if not pmid:
            continue
        abstract_parts = []
        for abstract_text in article.findall(".//Abstract/AbstractText"):
            text = " ".join(part.strip() for part in abstract_text.itertext() if part and part.strip())
            if not text:
                continue
            label = abstract_text.attrib.get("Label") or abstract_text.attrib.get("NlmCategory")
            abstract_parts.append(f"{label}: {text}" if label else text)
        abstracts[pmid] = _truncate_text(" ".join(abstract_parts), 2000)
    return abstracts


def _truncate_text(value: str, max_length: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= max_length:
        return text
    return text[: max_length - 3].rstrip() + "..."
