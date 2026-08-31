"""스위트를 오프라인으로 고정한다.

루프 제거 전에는 도구 선택 결정 대역(`_llm_tool_decision`)이 어떤 도구가
불릴지 통제했기 때문에, 대역을 깔지 않은 테스트는 우연히 PubMed/처방 RAG 를
건드리지 않았다. 지금은 파이프라인이 고정 순서라 **모든** 실행이 Pubmed Loader
와 Prescription Finder 를 거친다 — 대역이 없으면 스위트가 NCBI 에 실제 요청을
보내고, CI 가 외부 네트워크와 NCBI rate limit 에 종속된다.

그래서 두 외부 도구에 기본 대역을 깐다. 이 대역들은 "네트워크가 없다" 를
정직하게 표현한다(결과 0건 / 후보 0건). 실제 관측값이 필요한 테스트는 자기
대역을 그 위에 덮어쓴다 — monkeypatch 는 나중 것이 이긴다.
"""
from __future__ import annotations

import pytest

import app.agent as agent


class _OfflinePubmedLoader:
    def invoke(self, payload=None):
        query = (payload or {}).get("query", "")
        return {
            "status": "NO_RESULT",
            "evidence": [f"PubMed 검색 결과 없음: {query}"],
            "articles": [],
        }


class _OfflinePrescriptionFinder:
    def invoke(self, payload=None):
        return {
            "status": "FAILED",
            "evidence": ["처방 RAG 호출 실패: 오프라인 테스트 기본 대역"],
            "candidatePrescriptions": [],
            "recommendationLlmStatus": "fallback",
            "recommendationVerification": None,
        }


@pytest.fixture(autouse=True)
def offline_external_tools(monkeypatch):
    monkeypatch.setattr(agent, "pubmed_loader", _OfflinePubmedLoader())
    monkeypatch.setattr(agent, "prescription_finder", _OfflinePrescriptionFinder())
