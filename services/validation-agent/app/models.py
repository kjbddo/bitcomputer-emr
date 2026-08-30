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
    #
    # ReAct 도구 선택 루프를 제거한 뒤(아키텍처 리뷰 §5) `source` 는 "이 스텝을
    # 누가 골랐나" 가 아니라 **"이 스텝이 실제로 쓴 내용이 어디서 왔나"** 를
    # 뜻한다. 실행 순서는 이제 고정 파이프라인이라 "골랐다" 는 말 자체가 성립
    # 하지 않는다.
    # - llm: 이 스텝이 쓴 내용을 모델이 만들었다. 지금 이 값을 가질 수 있는
    #        스텝은 PubMed 질의가 모델 번역에서 나온 `Pubmed Loader` 하나뿐이다.
    # - stub: LLM_PROVIDER=stub 경로이거나, 이 스텝이 실어온 상류 데이터가
    #        스텁에서 왔다(Prescription Finder 의 recommendationLlmStatus).
    # - rule: 고정 파이프라인이 실행했고 내용도 결정론적이다. 모델이 관여할
    #        여지가 애초에 없는 스텝이다.
    # - fallback: 모델을 시도했으나(또는 시도할 수 없어) 결정론적 대체물을 썼다.
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
    # 출력이 도구 관측값으로 추적되는지. llmStatus 와 다른 축이다.
    # 기본값을 두지 않는 이유는 llmStatus 와 같다 — 없는 것을 있는 것처럼
    # 보이게 하면 안 된다. 웹은 None 을 "미검증"으로 렌더한다.
    #
    # 이 필드는 validation-agent 자기 자신의 검증(app/verification.py)이다.
    # 검사 셋 전부 target="response" 다 — 절대 "prescription[N]" 을 만들지
    # 않는다(spec §6.3). prescription_api 의 항목 단위 검증과 섞으면 Task 6
    # llmStatus 회귀와 같은 부류의 결함이 된다(tools.py:205-211 참고).
    verification: Optional[Dict[str, Any]] = None
    # prescription_api 자신의 항목 단위 검증 — target="prescription[N]" 을
    # 갖는 유일한 출처다(services/prescription/verification.py). 위
    # `verification`(validation-agent 자신의 판정) 과는 별개의 서비스,
    # 별개의 판정이라 절대 병합하지 않는다(최종 리뷰 C1).
    prescriptionVerification: Optional[Dict[str, Any]] = None
    # prescription_api 자신의 `llmStatus`. 위 `llmStatus`(validation-agent 가
    # 자기 결정을 어떻게 냈는지)와는 다른 서비스, 다른 축이라 절대 병합하지
    # 않는다 — 섞으면 Task 6 회귀다(tools.py:205-211). 처방 표의 모델 출처
    # 배지는 이 값을 읽어야 한다(F-H3).
    #
    # 기본값을 "fallback" 으로 두지 않고 None 으로 둔다. validation-agent 자신의
    # llmStatus 와 달리 이 값은 "조회를 아예 안 했다" 라는 상태가 실재한다 —
    # 그 경우 "폴백으로 만들었다" 고 말하면 하지 않은 주장을 하는 것이다(GC-2).
    # 웹은 None 을 "출처 미확인" 으로 렌더한다(GC-3).
    prescriptionLlmStatus: Optional[str] = None
