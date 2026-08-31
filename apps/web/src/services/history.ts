import { get, post, put } from "./http/client";
import type { PaginatedResponse } from "@/types/api";
import type { HistoryEntry } from "@/types/history";
import type { Verification } from "@/utils/verificationNotice";
import type { RenalGate } from "@/utils/renalGateNotice";

export interface HistoryPayload {
  employeeId: number;
  patientId: number;
  deptId: number;
  symptomDetail?: string | null;
  memo?: string | null;
  entryDate: string;
}

export interface HistoryResponse extends HistoryPayload {
  id: number;
}

export interface HistoryDiseasePayload {
  id?: number;
  historyId?: number;
  code: string;
  name: string;
  degree?: string | null;
}

export interface HistoryDiseaseResponse {
  id: number;
  historyId: number;
  code: string;
  name: string;
  degree: string | null;
}

export interface HistoryDiagnosePayload {
  id: number;
}

export interface HistoryDiagnoseResponse {
  id: number;
  historyId: number;
  code: string;
  name: string;
  dose: number;
  time: number;
  days: number;
}

export interface PrescriptionRecommendRequestPayload {
  history_id?: number;
  history_diagnose_id?: number;
  arango_patient_id?: string;
  use_example_context?: boolean;
  /** 상병 코드(E11 등). 생략 시 백엔드가 현재 진료 저장 상병으로 채움 */
  disease_codes?: string[];
}

export interface RecommendedPrescriptionItem {
  id: number;
  rank: number;
  prescription_code: string;
  prescription_name: string;
  reason: string;
  confidence_score: number;
  dose: number;
  time: number;
  days: number;
}

export interface PrescriptionSearchItem {
  id: number;
  code: string;
  name: string;
  dose: number;
  time: number;
  days: number;
}

export interface PrescriptionRecommendResponse {
  history_diagnose_id?: number;
  recommended_prescriptions: RecommendedPrescriptionItem[];
}

export type ValidationJobStatus = "PENDING" | "RUNNING" | "DONE" | "FAILED";

export interface ValidationJobStartResponse {
  jobId: string;
  historyId: number;
  status: ValidationJobStatus;
}

export interface ValidationJobResponse {
  jobId: string;
  historyId: number;
  status: ValidationJobStatus;
  summary?: string | null;
  result?: {
    overallStatus?: string;
    summary?: string;
    reason?: string;
    // Java DTO 는 이 필드를 그대로 왕복시킬 뿐 값을 검증하지 않는다(null 이나
    // "real"|"stub"|"fallback" 밖의 문자열도 그대로 저장·전달된다). 유니온 타입은
    // "이 셋 중 하나만 온다"는 보장을 실제로는 없는데 있는 것처럼 표시한다.
    llmStatus?: string | null;
    recommendedPrescriptions?: RecommendedPrescriptionItem[];
    candidatePrescriptions?: RecommendedPrescriptionItem[];
    checks?: Array<Record<string, unknown>>;
    suspectedIssues?: Array<Record<string, unknown>>;
    reasoningTrace?: Array<Record<string, unknown>>;
    validation?: Record<string, unknown>;
    // validation-agent 자기 자신의 검증. checks[].target 은 항상 "response" 다 —
    // "prescription[N]" 은 절대 만들지 않는다(services/validation-agent/app/verification.py).
    // 처방 항목 배지는 이 필드가 아니라 아래 prescriptionVerification 을 읽어야
    // 한다(최종 리뷰 C1).
    verification?: Verification | null;
    // prescription_api 자신의 항목 단위 검증. checks[].target 이 "prescription[N]"
    // 인 유일한 출처다(services/prescription/verification.py). 위 verification
    // 과는 다른 서비스, 다른 판정이므로 병합하지 않는다.
    prescriptionVerification?: Verification | null;
    // prescription_api 자신의 llmStatus. 위 llmStatus(validation-agent 가 자기
    // 결정을 어떻게 냈는지)와는 다른 서비스, 다른 축이다 — 처방 표의 모델 출처
    // 배지는 이 값을 읽어야 한다(F-H3). 값이 없으면 "미확인"으로 렌더한다.
    prescriptionLlmStatus?: string | null;
    // prescription_api 의 신기능 금기 관문(services/prescription/renal_gate.py).
    // status(warn|clear|unknown) 는 판정 축이고 renalStatus(impaired|suspected|
    // undetermined) 는 환자 축이다 — 둘을 합치면 "신기능 저하인데 이 약들은 표
    // 밖" 과 "신기능을 못 읽어서 판정 불가" 가 같아 보인다. 값이 없으면
    // "관문 미확인" 으로 렌더한다(GC-3).
    prescriptionRenalGate?: RenalGate | null;
    [key: string]: unknown;
  } | null;
  lastError?: string | null;
}

export interface HistoryListResponse {
  patientId: number;
  histories: HistoryEntry[];
}

export async function createHistory(payload: HistoryPayload): Promise<HistoryResponse> {
  return post<HistoryResponse, HistoryPayload>("/api/histories/write_history", payload);
}

export async function getPatientHistories(
  employeeId: number,
  patientId: number,
  startDate?: string,
  endDate?: string
): Promise<HistoryListResponse> {
  const params: Record<string, string> = {
    patientId: String(patientId),
  };
  if (startDate) params.startDate = startDate;
  if (endDate) params.endDate = endDate;
  return get<HistoryListResponse>(`/api/histories/search_history/${employeeId}`, { params });
}

export async function setHistoryDiseases(
  historyId: number,
  employeeId: number,
  diseases: HistoryDiseasePayload[]
): Promise<HistoryDiseaseResponse[]> {
  return put<HistoryDiseaseResponse[], HistoryDiseasePayload[]>(
    `/api/histories/${historyId}/set_diseases`,
    diseases,
    {
      params: { employeeId },
    }
  );
}

export async function setHistoryDiagnoses(
  historyId: number,
  employeeId: number,
  diagnoses: HistoryDiagnosePayload[]
): Promise<HistoryDiagnoseResponse[]> {
  return put<HistoryDiagnoseResponse[], HistoryDiagnosePayload[]>(
    `/api/histories/${historyId}/set_diagnoses`,
    diagnoses,
    {
      params: { employeeId },
    }
  );
}

export async function getHistoryDiseases(
  historyId: number,
  employeeId: number
): Promise<HistoryDiseaseResponse[]> {
  return get<HistoryDiseaseResponse[]>(`/api/histories/${historyId}/get_diseases`, {
    params: { employeeId },
  });
}

export async function getHistoryDiagnoses(
  historyId: number,
  employeeId: number
): Promise<HistoryDiagnoseResponse[]> {
  return get<HistoryDiagnoseResponse[]>(`/api/histories/${historyId}/get_diagnoses`, {
    params: { employeeId },
  });
}

/** Spring → Python prescription_api → Gemini 등 연쇄 호출용 (기본 axios 15초 초과 방지) */
const PRESCRIPTION_RECOMMEND_TIMEOUT_MS = 180_000;

export async function recommendPrescriptions(
  payload: PrescriptionRecommendRequestPayload
): Promise<ValidationJobStartResponse> {
  return post<ValidationJobStartResponse, PrescriptionRecommendRequestPayload>(
    "/api/agent/prescription/recommend",
    payload,
    { timeout: PRESCRIPTION_RECOMMEND_TIMEOUT_MS }
  );
}

export async function getValidationJob(jobId: string): Promise<ValidationJobResponse> {
  return get<ValidationJobResponse>(`/api/validation-jobs/${jobId}`);
}

export async function searchPrescriptions(
  query: string,
  page = 0,
  size = 20
): Promise<PaginatedResponse<PrescriptionSearchItem>> {
  return get<PaginatedResponse<PrescriptionSearchItem>>("/api/diagnoses", {
    params: {
      page,
      size,
      ...(query.trim() ? { query: query.trim() } : {}),
    },
  });
}

export interface PrescriptionFeedbackItemPayload {
  rank: number;
  prescriptionId?: number;
  prescriptionCode: string;
  prescriptionName: string;
  confidenceScore?: number;
  reason?: string;
  /** accepted: 체크 선택, rejected: 체크 미선택, missed: AI 미추천이지만 의사가 직접 추가·저장 */
  status: "accepted" | "rejected" | "missed";
}

export interface SavePrescriptionFeedbackPayload {
  historyId: number;
  historyDiagnoseId?: number;
  feedbackItems: PrescriptionFeedbackItemPayload[];
}

export async function savePrescriptionFeedback(payload: SavePrescriptionFeedbackPayload): Promise<void> {
  return post<void, SavePrescriptionFeedbackPayload>("/api/agent/prescription/feedback", payload);
}

