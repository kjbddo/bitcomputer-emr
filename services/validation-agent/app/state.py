"""검증 실행 중 도구 관측값이 쌓이는 자리.

`agent.py` 에서 떼어냈다. `pubmed.py`·`finalize.py` 가 둘 다 이 타입을 읽으므로
공통 하위 모듈에 둬야 순환 import 가 생기지 않는다.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict


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
    # 도구 관측값 원본. 응답에 실리는 candidate_prescriptions 는 정규화(코드/키 통일)를
    # 거치므로, 검증기(app.verification)에 넘길 대조 기준은 이 원본이어야 한다 —
    # 정규화된 값을 넘기면 응답이 자기 자신과 비교돼 항상 통과한다(spec §4.1).
    pubmed_articles: List[Dict[str, Any]]
    finder_candidates: List[Dict[str, Any]]
    # prescription_api 자신의 항목 단위 검증(target="prescription[N]") 원본.
    # validation-agent 자신의 verification 과는 다른 서비스, 다른 판정이라
    # 응답 최상위에 별도 필드(prescriptionVerification)로만 얹는다 — 섞지
    # 않는다(최종 리뷰 C1, tools.py 의 recommendationVerification 주석).
    prescription_verification: Optional[Dict[str, Any]]


def compact_state(state: ValidationState) -> Dict[str, Any]:
    """모델에게 보낼 컨텍스트. 내부 키 이름을 응답 어휘로 바꾼다."""
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
