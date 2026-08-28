from __future__ import annotations

from typing import Any, Dict, List, Optional

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
    reasoningTrace: List[Dict[str, Any]] = Field(default_factory=list)
    checks: List[Dict[str, Any]] = Field(default_factory=list)
    suspectedIssues: List[Dict[str, Any]] = Field(default_factory=list)
    suggestedReviewItems: List[str] = Field(default_factory=list)
    candidatePrescriptions: List[Dict[str, Any]] = Field(default_factory=list)
    shouldNotifyDoctor: bool = False
    shouldBlockAutoPrescription: bool = False
    # LLM 을 실제로 썼는지. 설정이 아니라 실행 경로에서 도출한다(spec §6.2).
    llmStatus: str = "real"
