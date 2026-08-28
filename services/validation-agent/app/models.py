from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class ValidationAgentRequest(BaseModel):
    jobId: Optional[str] = None
    eventId: int = 0
    eventType: str = "AI_PRESCRIPTION_RECOMMEND"
    triggerType: Optional[str] = None
    historyId: int
    patientId: Optional[int] = None
    employeeId: Optional[int] = None
    deptId: Optional[int] = None
    eventPayload: Dict[str, Any] = Field(default_factory=dict)
    patientSummary: Dict[str, Any] = Field(default_factory=dict)
    symptoms: Optional[str] = None
    savedDiseases: List[Dict[str, Any]] = Field(default_factory=list)
    savedPrescriptions: List[Dict[str, Any]] = Field(default_factory=list)
    xrayInference: Optional[Dict[str, Any]] = None


class ValidationAgentResponse(BaseModel):
    jobId: Optional[str] = None
    historyId: Optional[int] = None
    overallStatus: str
    summary: str
    reason: str = ""
    recommendedPrescriptions: List[Dict[str, Any]] = Field(default_factory=list)
    validation: Dict[str, Any] = Field(default_factory=dict)
    # 각 항목은 최소 `thought`/`action`/`actionInput`/`observation`/`source` 를 갖는다.
    # `source` 값 공간: "llm" | "stub" | "rule" | "fallback" (spec §6.3).
    # - llm: 실제 LLM 결정/생성에서 나왔다.
    # - stub: LLM_PROVIDER=stub 결정론적 순서에서 나왔다.
    # - rule: 결정 루프 밖에서 항상 실행되는 규칙 기반 후처리다(LLM이 애초에 관여할 여지가 없음).
    # - fallback: LLM 을 시도했으나(또는 시도할 수 없어) 휴리스틱으로 대체됐다.
    reasoningTrace: List[Dict[str, Any]] = Field(default_factory=list)
    checks: List[Dict[str, Any]] = Field(default_factory=list)
    suspectedIssues: List[Dict[str, Any]] = Field(default_factory=list)
    suggestedReviewItems: List[str] = Field(default_factory=list)
    candidatePrescriptions: List[Dict[str, Any]] = Field(default_factory=list)
    shouldNotifyDoctor: bool = False
    shouldBlockAutoPrescription: bool = False
    # LLM 을 실제로 썼는지. 설정이 아니라 실행 경로에서 도출한다(spec §6.2).
    # 기본값은 "fallback" 로 fail-closed 한다 — 이 필드가 누락된 채 역직렬화되면
    # "모델이 돌았다"고 오인되는 대신 "LLM 미사용" 쪽으로만 틀리게 한다(리뷰 finding 5).
    llmStatus: Literal["real", "stub", "fallback"] = "fallback"
