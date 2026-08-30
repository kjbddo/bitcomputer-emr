"""이 서비스가 게이트웨이로 보내는 프롬프트 전부.

프롬프트가 둘뿐인 이유는 모델 호출이 둘뿐이기 때문이다(gateway.py 참조).
옛 도구 선택 프롬프트(`availableTools` 를 싣던 것)와 옛 최종화 프롬프트
(도달 불가였던 `_llm_finalize`)는 함께 지웠다.

프롬프트를 전용 모듈에 두는 것은 prescription / certificate 가 이미 쓰는
방식이다 — validation-agent 만 프롬프트를 실행 코드와 같은 파일에 두고 있었다
(아키텍처 리뷰 §6 표).
"""
from __future__ import annotations

import json
from typing import Any, Dict, List

PUBMED_QUERY_SYSTEM = "You generate concise English PubMed search queries and return JSON only."
PUBMED_SUMMARY_SYSTEM = (
    "You summarize PubMed abstracts as cautious clinical validation evidence in Korean."
)


def pubmed_query_prompt(compacted_state: Dict[str, Any], reason: str) -> str:
    """한국어 임상 맥락 -> 영어 PubMed 질의.

    이 번역이 이 서비스에서 모델이 유일하게 대체 불가한 일이다. 하드코딩
    사전(`pubmed.KOREAN_PUBMED_TERMS`, 15항목)은 라이브에서 관측된
    "acute cough symptomatic treatment dextromethorphan guaifenesin
    levodropropizine adults" 같은 질의를 만들 수 없다(아키텍처 리뷰 §5.5).
    """
    return f"""다음 진료 검증 컨텍스트를 PubMed ESearch에 적합한 영어 검색어로 정규화하라.

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
{json.dumps(compacted_state, ensure_ascii=False)}
"""


def pubmed_summary_prompt(payload: Dict[str, Any]) -> str:
    return f"""다음 PubMed 초록 내용을 진료 데이터 검증 근거로 4문장 이내 한국어로 요약하라.

주의:
- 논문이 직접적으로 현재 환자 처방을 승인한다고 단정하지 않는다.
- 초록에서 확인되는 질환/증상/약물/치료 관련 내용만 말한다.
- PMID를 최소 1개 포함한다.
- JSON이 아닌 평문 한 문단으로 답한다.

자료:
{json.dumps(payload, ensure_ascii=False)}
"""


def pubmed_summary_payload(
    overall: str,
    state_view: Dict[str, Any],
    articles: List[Dict[str, Any]],
) -> Dict[str, Any]:
    return {
        "overallStatus": overall,
        "savedDiseases": state_view.get("savedDiseases") or [],
        "savedPrescriptions": state_view.get("savedPrescriptions") or [],
        "candidatePrescriptions": state_view.get("candidatePrescriptions") or [],
        "symptoms": state_view.get("symptoms") or "",
        "articles": [
            {
                "pmid": article.get("pmid"),
                "title": article.get("title"),
                "source": article.get("source"),
                "pubdate": article.get("pubdate"),
                "abstract": article.get("abstract") or article.get("abstractSnippet") or "",
            }
            for article in articles[:3]
        ],
    }
