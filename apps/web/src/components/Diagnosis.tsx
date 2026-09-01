"use client";

import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useMedicalSelection, type PrescriptionFeedbackItem } from "@store/medicalSelection";
import { Badge, Button, EmptyState, Modal, Panel, Table } from "@/components/ui";
import styles from "./Diagnosis.module.css";
import { ClinicVisitContext } from "@/types/clinic";
import {
  getValidationJob,
  recommendPrescriptions,
  savePrescriptionFeedback,
  searchPrescriptions,
  setHistoryDiagnoses,
  type PrescriptionSearchItem,
  type RecommendedPrescriptionItem,
  type ValidationJobResponse,
} from "@/services/history";
import { HttpError } from "@/services/http/types";
import {
  graphLookupFoundNothing,
  graphLookupNotice,
  type GraphLookup,
} from "@/utils/graphLookupNotice";
import {
  renalGateNotice,
  renalItemNotice,
  type RenalGate,
} from "@/utils/renalGateNotice";
import { llmStatusNotice } from "@/utils/llmStatus";
import {
  itemVerificationOutcome,
  responseVerificationOutcome,
  verificationNotice,
  type Verification,
} from "@/utils/verificationNotice";

// reasoningTrace 스텝 각각의 출처. 최상위 llmStatus 배지는 작업 전체를
// 하나로 뭉뚱그리므로, fallback 작업 안에 llm 스텝이 섞여 있거나 그 반대인
// 경우를 가린다 — 사람이 트레이스만 보고 LLM 추론으로 오인할 수 없어야
// 한다(spec §6.3 완료 조건 6). llmStatus.ts 의 표시 어휘를 그대로 쓴다.
function sourceMark(source: unknown): string {
  const value = asText(source);
  // "llm" 정확 일치만 무표시다. 값이 없거나 계약 밖이면 표시를 붙인다 —
  // 이 브랜치의 다른 모든 경계와 같은 방향(fail-closed)이다. 반대로 두면
  // source 를 빠뜨린 스텝이 모델 추론과 구분되지 않는다.
  if (value === "llm") return "";
  if (value === "stub") return " (스텁)";
  return " (규칙 기반)";
}

type DiagnosisProps = {
  clinicVisit: ClinicVisitContext | null;
  ensureHistory: () => Promise<number>;
  employeeId: number;
  onHistoryUpdated?: () => void;
};

type PrescriptionPickerState = {
  item: RecommendedPrescriptionItem;
  key: string;
};

function asText(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function recommendationKey(item: RecommendedPrescriptionItem): string {
  return `${item.rank}:${item.prescription_code}:${item.prescription_name}`;
}

function buildPrescriptionSearchQuery(item: RecommendedPrescriptionItem): string {
  const name = asText(item.prescription_name);
  if (name && name !== "미기재") return name;
  const code = asText(item.prescription_code);
  if (code && code !== "미기재") return code;
  return "";
}

// AI 검증 엔진(services/validation-agent)이 내는 overallStatus 값 공간은
// PASS | WARNING | CRITICAL | NEEDS_REVIEW 4종으로 백엔드가 고정한다
// (_normalize_final_result 가 이 집합 밖의 값을 전부 NEEDS_REVIEW 로 되돌린다).
// 그 외 값(예: validationModal.status 로 대체 표시되는 작업 상태 PENDING/RUNNING/
// FAILED)은 이 스킴에 속하지 않으므로 neutral 로 떨어뜨린다.
function overallStatusTone(
  overallStatus: string | undefined
): "success" | "warning" | "danger" | "neutral" {
  switch (overallStatus) {
    case "PASS":
      return "success";
    case "WARNING":
    case "NEEDS_REVIEW":
      return "warning";
    case "CRITICAL":
      return "danger";
    default:
      return "neutral";
  }
}

function extractValidationReasons(job: ValidationJobResponse | null): string[] {
  const result = job?.result;
  if (!result) return [];

  const reasons: string[] = [];
  const overallReason = asText(result.reason);
  if (overallReason) reasons.push(overallReason);

  const checks = Array.isArray(result.checks) ? result.checks : [];
  checks.forEach((item) => {
    const message = asText(item.message);
    const action = asText(item.recommendedAction);
    if (message) reasons.push(message);
    if (action) reasons.push(`권고: ${action}`);
  });

  const suspectedIssues = Array.isArray(result.suspectedIssues) ? result.suspectedIssues : [];
  suspectedIssues.forEach((item) => {
    const description = asText(item.description);
    const reason = asText(item.reason);
    if (description) reasons.push(description);
    if (reason) reasons.push(`이유: ${reason}`);
  });

  const reasoningTrace = Array.isArray(result.reasoningTrace) ? result.reasoningTrace : [];
  reasoningTrace.slice(-3).forEach((step) => {
    const action = asText(step.action);
    const observation = step.observation;
    let observationText = "";
    if (typeof observation === "string") {
      observationText = observation;
    } else if (observation && typeof observation === "object") {
      const status = asText((observation as Record<string, unknown>).status);
      const evidence = (observation as Record<string, unknown>).evidence;
      const evidenceText = Array.isArray(evidence)
        ? evidence.map((item) => String(item)).join(", ")
        : "";
      observationText = [status, evidenceText].filter(Boolean).join(" - ");
    }
    if (action && observationText) {
      reasons.push(`${action}${sourceMark(step.source)}: ${observationText}`);
    }
  });

  return Array.from(new Set(reasons.filter(Boolean))).slice(0, 6);
}


export default function Diagnosis({ clinicVisit, ensureHistory, employeeId, onHistoryUpdated }: DiagnosisProps) {
  const { diseases, diagnoses, prescriptionFeedback, addDiagnosis, removeDiagnosis, clearDiagnoses, setPrescriptionFeedback, clearPrescriptionFeedback } = useMedicalSelection();
  const [saving, setSaving] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [aiRecommendations, setAiRecommendations] = useState<RecommendedPrescriptionItem[]>([]);
  // 검증 모달은 확인 클릭으로 사라지지만 "AI 추천 처방" 패널은 화면에 남는다.
  // llmStatus 를 모달 state 에만 두면 모달을 닫는 순간 모델 미사용 여부를 알
  // 방법이 사라진다 — aiRecommendations 와 생명주기를 맞춰 별도로 들고 있는다.
  const [aiLlmStatus, setAiLlmStatus] = useState<string | null | undefined>(undefined);
  // verification 은 llmStatus 와 다른 축("출력이 조회 결과로 추적되나")이므로
  // 별도 state 로 들고 있는다. 생명주기는 aiRecommendations/aiLlmStatus 와
  // 정확히 같아야 한다 — 다르면 배지가 자기가 설명하는 데이터와 어긋난다.
  // 불변식: aiVerification 은 `aiRecommendations.length > 0` 로 게이트된 패널
  // 안에서만 읽는다. 이 불변식 때문에 리셋 지점에서 이 상태를 지우는 것은
  // 방어적 조치일 뿐이다 — 패널을 다시 띄우는 유일한 경로(생성 성공)가 같은
  // 블록에서 이 값을 새 결과로 덮으므로 낡은 값이 화면에 닿을 수 없다.
  // 이 파일 밖이나 게이트 밖에서 aiVerification 을 읽기 시작하면 그 논증이
  // 깨지고, 검증된 적 없는 추천이 검증된 것처럼 보이는 결함이 되돌아온다.
  const [aiVerification, setAiVerification] = useState<Verification | null | undefined>(undefined);
  // 신기능 금기 관문. aiVerification 과 같은 생명주기이고 같은 게이트 안에서만
  // 읽는다. 다른 서비스(prescription_api)의 판정이므로 aiVerification 과 합치지
  // 않는다 — 축이 다르다(추적 가능성 vs 임상 금기).
  const [aiRenalGate, setAiRenalGate] = useState<RenalGate | null | undefined>(undefined);
  // 마지막 AI 실행이 "조회했고 뒷받침하는 후보가 0건" 으로 끝났는가(설계 §3.2).
  // E78(고지혈증)이 실제 사례다. 추천 0건은 오류가 아니라 답이므로 화면에
  // 남아야 하는데, aiRecommendations 는 이 경우와 "조회에 실패해서 0건" 과
  // "아직 한 번도 안 돌렸다" 를 전부 빈 배열 하나로 표현한다 — 그래서 구분이
  // 필요하다. 서버 상태를 복제하는 것이 아니라, 응답의 graphLookup 을 읽어
  // 한 번 판정한 결과를 다른 ai* state 와 같은 생명주기로 들고 있는 것이다.
  const [aiNoCandidates, setAiNoCandidates] = useState(false);
  // 처방 상세 선택으로 스왑된 랭크의 집합. rank 는 표의 "행 위치"고, aiVerification
  // 은 그 위치에 원래 앉아있던 처방을 검사한 결과다. 스왑 후에도 rank 는 그대로라
  // `prescription[${rank}]` 로 조회하면 새 처방이 옛 검사 결과를 뒤집어쓴다 —
  // 한 번도 검사 안 된 처방이 "검증됨"으로 보이는 정확히 그 반전이다. 그래서
  // 스왑된 rank 는 별도로 추적해 무조건 미검증으로 렌더한다. aiVerification 과
  // 생명주기를 정확히 같이 가야 한다(새 세대가 시작되면 이 집합도 깨끗해져야
  // 한다) — 다르면 이 브랜치가 이미 한 번 걸린 함정(Task 10 리뷰)을 새 state 로
  // 재현하는 꼴이다.
  const [swappedRanks, setSwappedRanks] = useState<Set<number>>(new Set());
  const [selectedRecommendationKeys, setSelectedRecommendationKeys] = useState<string[]>([]);
  const [validationModal, setValidationModal] = useState<ValidationJobResponse | null>(null);
  const [prescriptionPicker, setPrescriptionPicker] = useState<PrescriptionPickerState | null>(null);
  const [prescriptionSearchDraft, setPrescriptionSearchDraft] = useState("");
  const [prescriptionSearchResults, setPrescriptionSearchResults] = useState<PrescriptionSearchItem[]>([]);
  const [prescriptionSearchLoading, setPrescriptionSearchLoading] = useState(false);
  const [prescriptionSearchError, setPrescriptionSearchError] = useState<string | null>(null);
  const [aiSessionHistoryId, setAiSessionHistoryId] = useState<number | null>(null);
  const [aiSessionHistoryDiagnoseId, setAiSessionHistoryDiagnoseId] = useState<number | null>(null);
  const prevPatientIdRef = useRef<number | null>(null);

  useEffect(() => {
    const currentPatientId = clinicVisit?.patientId ?? null;
    if (prevPatientIdRef.current !== currentPatientId) {
      prevPatientIdRef.current = currentPatientId;
      clearDiagnoses();
      clearPrescriptionFeedback();
      setAiRecommendations([]);
      setAiLlmStatus(undefined);
      setAiVerification(undefined);
      setAiRenalGate(undefined);
      setAiNoCandidates(false);
      setSwappedRanks(new Set());
      setSelectedRecommendationKeys([]);
      setPrescriptionPicker(null);
      setAiSessionHistoryId(null);
      setAiSessionHistoryDiagnoseId(null);
    }
  }, [clearDiagnoses, clearPrescriptionFeedback, clinicVisit?.patientId]);

  useEffect(() => {
    clearPrescriptionFeedback();
    setAiRecommendations([]);
    setAiLlmStatus(undefined);
    setAiVerification(undefined);
    setAiRenalGate(undefined);
    setAiNoCandidates(false);
    setSwappedRanks(new Set());
    setSelectedRecommendationKeys([]);
    setPrescriptionPicker(null);
    setAiSessionHistoryId(null);
    setAiSessionHistoryDiagnoseId(null);
  }, [clearPrescriptionFeedback, clinicVisit?.historyId]);

  const handleSave = useCallback(async () => {
    if (!clinicVisit) {
      alert("환자를 먼저 선택해주세요.");
      return;
    }

    if (diagnoses.length === 0) {
      return;
    }

    setSaving(true);
    try {
      const historyId = await ensureHistory();
      const persistableDiagnoses = diagnoses.filter((item) => item.id > 0);
      if (persistableDiagnoses.length === 0) {
        alert("현재 목록은 DB 미매칭 AI 추천만 있어 저장할 수 없습니다.");
        return;
      }
      await setHistoryDiagnoses(
        historyId,
        employeeId,
        persistableDiagnoses.map((item) => ({
          id: item.id,
        }))
      );
      onHistoryUpdated?.();

      // AI가 추천하지 않았지만 의사가 직접 추가·저장한 처방 → missed로 기록
      // AI를 아예 안 쓴 경우에도 모든 저장 처방이 missed로 분류됨
      const aiRecommendedIds = new Set(prescriptionFeedback.map((f) => f.id).filter((id) => id > 0));
      const missedItems = persistableDiagnoses.filter((d) => !aiRecommendedIds.has(d.id));
      if (missedItems.length > 0) {
        try {
          await savePrescriptionFeedback({
            historyId,
            historyDiagnoseId: aiSessionHistoryDiagnoseId ?? undefined,
            feedbackItems: missedItems.map((d) => ({
              rank: 0,
              prescriptionId: d.id,
              prescriptionCode: d.code,
              prescriptionName: d.name,
              status: "missed" as const,
            })),
          });
        } catch (error) {
          console.error("missed 처방 피드백 저장 실패:", error);
        }
      }

      if (persistableDiagnoses.length !== diagnoses.length) {
        alert(
          `처방 정보가 저장되었습니다. (DB 매칭 ${persistableDiagnoses.length}건 저장, ${
            diagnoses.length - persistableDiagnoses.length
          }건은 미매칭으로 제외)`
        );
      } else {
        alert("처방 정보가 저장되었습니다.");
      }
    } catch (error) {
      console.error("처방 정보 저장 실패:", error);
      alert("처방 정보를 저장하지 못했습니다. 잠시 후 다시 시도해주세요.");
    } finally {
      setSaving(false);
    }
  }, [aiSessionHistoryDiagnoseId, clinicVisit, diagnoses, employeeId, ensureHistory, onHistoryUpdated, prescriptionFeedback]);

  const handleGenerateByAI = useCallback(async () => {
    if (!clinicVisit) {
      alert("환자를 먼저 선택해주세요.");
      return;
    }

    setGenerating(true);
    try {
      const historyId = await ensureHistory();
      const response = await recommendPrescriptions({
        history_id: historyId,
        arango_patient_id: clinicVisit.visitNumber || undefined,
        // true 이면 GraphDB/langchain_graph_qa/patient_ctx.example.json 이 증상·top_rx 등을 덮어씀(데모 전용). 실제 Arango/MySQL 기반 추천은 false.
        use_example_context: false,
        disease_codes: diseases.map((d) => d.code),
      });
      const job = await pollValidationJob(response.jobId);
      if (job.status === "FAILED") {
        throw new Error(job.lastError || "검증 에이전트 작업이 실패했습니다.");
      }
      const result = job.result ?? {};
      const recommended =
        result.recommendedPrescriptions ??
        result.candidatePrescriptions ??
        [];

      if (recommended.length === 0) {
        // 0건은 두 가지 서로 다른 사실이다(설계 §3.2, GC-3). 목록 길이로는
        // 갈리지 않으므로 graphLookup 을 읽는다.
        //   조회했고 후보가 없었다  -> 우리 데이터에 대한 답. 화면에 남는다
        //   조회에 실패했거나 단계를 안 돌았다 -> 확인 못 함. 답이 아니다
        const lookedAndFoundNothing = graphLookupFoundNothing(
          (result.validation as { graphLookup?: GraphLookup } | undefined)?.graphLookup
        );
        setAiRecommendations([]);
        setAiNoCandidates(lookedAndFoundNothing);
        // 항목이 없으므로 항목 단위 배지는 읽히지 않는다. 낡은 값이 남지
        // 않도록 명시적으로 비운다(aiVerification 불변식 유지).
        setAiVerification(undefined);
        setAiRenalGate(undefined);
        setAiLlmStatus(result.prescriptionLlmStatus);
        setSwappedRanks(new Set());
        setSelectedRecommendationKeys([]);
        setAiSessionHistoryId(historyId);
        setAiSessionHistoryDiagnoseId(null);
        clearPrescriptionFeedback();
        alert(
          lookedAndFoundNothing
            ? "이 상병에 대해 우리 데이터가 뒷받침하는 처방 후보가 0건입니다. 없는 추천을 만들지 않았습니다."
            : "AI 추천/검증 결과가 비어 있습니다. 검증 요약을 확인해주세요."
        );
        setValidationModal(job);
        return;
      }

      setAiRecommendations(recommended);
      setAiNoCandidates(false);
      // 이 배지는 아래 표 안의 처방에 붙는다. 그 처방을 실제로 만든 것은
      // prescription-api 이므로 읽어야 하는 값은 그쪽의 llmStatus 다.
      // result.llmStatus 는 validation-agent 가 자기 검증 결정을 어떻게 냈는지라
      // 표의 출처와 무관하다 — 그 값을 읽으면 prescription-api 가 스텁인데도
      // validation-agent 가 real 이라는 이유로 배지가 사라진다(F-H3, 라이브 재현).
      // 바로 아래 검증 축이 이미 지키고 있는 구분과 같은 구분이다.
      // 값이 없으면 llmStatusNotice 가 "모델 출처 미확인"을 낸다(GC-3).
      setAiLlmStatus(result.prescriptionLlmStatus);
      // 처방 항목 배지(getVerificationOutcome)는 `prescription[N]` 타깃을 조회한다.
      // result.verification 은 validation-agent 자기 자신의 검증이고 검사 전부
      // target="response" 다 — 그 값을 읽으면 조회가 영원히 0건이 되어 배지가
      // 항상 미검증으로 굳는다(최종 리뷰 C1). prescription_api 자신의 항목 단위
      // 검증인 result.prescriptionVerification 을 읽어야 한다.
      setAiVerification(result.prescriptionVerification);
      // 관문 결과가 없으면 undefined 가 남고 renalGateNotice 가 "관문 미확인"을
      // 낸다. 여기서 빈 객체로 채우면 "확인 못 함"이 "해당 없음"이 된다(GC-3).
      setAiRenalGate(result.prescriptionRenalGate);
      setSwappedRanks(new Set());
      setSelectedRecommendationKeys(recommended.map(recommendationKey));
      setAiSessionHistoryId(historyId);
      setAiSessionHistoryDiagnoseId(null);
      clearPrescriptionFeedback();
      setValidationModal(job);
    } catch (error) {
      console.error("AI 처방 생성 실패:", error);
      const hint =
        error instanceof HttpError
          ? `\n\n[HTTP ${error.status}] ${error.message}` +
            (error.data && typeof error.data === "object"
              ? `\n${JSON.stringify(error.data).slice(0, 400)}`
              : "")
          : error instanceof Error
            ? `\n\n${error.message}`
            : "";
      alert(`AI 처방 생성에 실패했습니다.${hint}`);
    } finally {
      setGenerating(false);
    }
  }, [clearPrescriptionFeedback, clinicVisit, diseases, ensureHistory]);

  const pollValidationJob = async (jobId: string): Promise<ValidationJobResponse> => {
    const maxAttempts = 90;
    for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
      const job = await getValidationJob(jobId);
      if (job.status === "DONE" || job.status === "FAILED") {
        return job;
      }
      await new Promise((resolve) => window.setTimeout(resolve, 2000));
    }
    throw new Error("검증 에이전트 응답 대기 시간이 초과되었습니다.");
  };

  const toggleRecommendation = useCallback((key: string) => {
    setSelectedRecommendationKeys((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]
    );
  }, []);

  const fetchPrescriptionCandidates = useCallback(async (query: string) => {
    setPrescriptionSearchLoading(true);
    setPrescriptionSearchError(null);
    try {
      const response = await searchPrescriptions(query, 0, 20);
      setPrescriptionSearchResults(response.items);
      if (response.items.length === 0) {
        setPrescriptionSearchError("조회된 처방이 없습니다. 다른 검색어를 입력해주세요.");
      }
    } catch (error) {
      console.error("처방 상세 조회 실패:", error);
      setPrescriptionSearchResults([]);
      setPrescriptionSearchError("처방 DB 조회에 실패했습니다.");
    } finally {
      setPrescriptionSearchLoading(false);
    }
  }, []);

  const openPrescriptionPicker = useCallback((item: RecommendedPrescriptionItem) => {
    const key = recommendationKey(item);
    const query = buildPrescriptionSearchQuery(item);
    setPrescriptionPicker({ item, key });
    setPrescriptionSearchDraft(query);
    setPrescriptionSearchResults([]);
    setPrescriptionSearchError(null);
    void fetchPrescriptionCandidates(query);
  }, [fetchPrescriptionCandidates]);

  const handlePrescriptionSearchSubmit = useCallback(() => {
    void fetchPrescriptionCandidates(prescriptionSearchDraft);
  }, [fetchPrescriptionCandidates, prescriptionSearchDraft]);

  const handleSelectPrescriptionDetail = useCallback((selected: PrescriptionSearchItem) => {
    if (!prescriptionPicker) return;

    const nextItem: RecommendedPrescriptionItem = {
      ...prescriptionPicker.item,
      id: selected.id,
      prescription_code: selected.code,
      prescription_name: selected.name,
      dose: selected.dose ?? 0,
      time: selected.time ?? 0,
      days: selected.days ?? 0,
    };
    const nextKey = recommendationKey(nextItem);

    setAiRecommendations((prev) =>
      prev.map((item) => recommendationKey(item) === prescriptionPicker.key ? nextItem : item)
    );
    setSelectedRecommendationKeys((prev) =>
      prev.includes(prescriptionPicker.key)
        ? prev.map((key) => key === prescriptionPicker.key ? nextKey : key)
        : prev
    );
    // rank 는 유지되지만 그 자리의 처방이 바뀌었다 — aiVerification 은 옛 처방을
    // 검사한 결과이므로 더 이상 화면의 처방을 설명하지 않는다. 다른 rank 의
    // 검증은 여전히 유효하므로 전체를 지우지 않고 이 rank 만 무효화한다.
    setSwappedRanks((prev) => {
      const next = new Set(prev);
      next.add(prescriptionPicker.item.rank);
      return next;
    });
    setPrescriptionPicker(null);
  }, [prescriptionPicker]);

  // 스왑된 rank 는 aiVerification 에 무엇이 담겨 있든 무조건 미검증으로 본다 —
  // 그 rank 의 검사는 지금 화면의 처방이 아니라 스왑되기 전 처방을 대상으로 했다.
  const getVerificationOutcome = useCallback(
    (rank: number) => {
      if (swappedRanks.has(rank)) return "skipped" as const;
      return itemVerificationOutcome(aiVerification, `prescription[${rank}]`);
    },
    [aiVerification, swappedRanks]
  );

  // 스왑된 rank 는 관문 판정도 무효다 — 그 판정은 지금 화면의 약이 아니라
  // 스왑되기 전 약을 대조한 결과다. 검증 축에서 하는 것과 정확히 같은 이유이고,
  // 여기서 빼먹으면 금기 약으로 바꿔 넣어도 옛 `clear` 가 그대로 남는다.
  const getRenalItemNotice = useCallback(
    (rank: number) => {
      if (swappedRanks.has(rank)) return { label: "신기능 미확인", tone: "warning" as const };
      return renalItemNotice(aiRenalGate, rank);
    },
    [aiRenalGate, swappedRanks]
  );

  // 응답 단위 판정(최종 리뷰 M1). schema_top3 는 target="response" 라
  // getVerificationOutcome(`prescription[N]`) 조회에 절대 걸리지 않는다 —
  // 항목 배지만 있으면 이 검사는 flagged 여도 처방 화면에 아무 표시가 없다.
  //
  // 스왑이 하나라도 있으면 미검증이다. schema_top3 는 "rank 집합이 {1,2,3}
  // 인가" 와 "코드 중복이 없는가" 를 그때 화면에 있던 처방코드 집합에 대해
  // 판정한 결과인데, 스왑은 그 집합을 바꾼다. 스왑으로 들어온 코드가 다른
  // 행과 겹쳐도 옛 판정은 여전히 ok 이므로, 그대로 두면 검사된 적 없는
  // 조합이 "응답 단위 이상 없음" 으로 보인다 — 항목 배지에서 막은 것과
  // 정확히 같은 반전이다.
  const responseOutcome = useMemo(() => {
    if (swappedRanks.size > 0) return "skipped" as const;
    return responseVerificationOutcome(aiVerification);
  }, [aiVerification, swappedRanks]);

  const handleApplySelectedRecommendations = useCallback(async () => {
    if (aiRecommendations.length === 0) {
      alert("먼저 AI 추천을 생성해주세요.");
      return;
    }
    // selectedRecommendationKeys가 0이어도 전체 거부 피드백으로 저장

    const feedback: PrescriptionFeedbackItem[] = [];
    let mappedCount = 0;
    let unmappedCount = 0;

    for (const item of aiRecommendations) {
      const key = recommendationKey(item);
      const isAccepted = selectedRecommendationKeys.includes(key);

      feedback.push({
        rank: item.rank,
        id: item.id,
        prescription_code: item.prescription_code ?? "",
        prescription_name: item.prescription_name ?? "",
        confidence_score: item.confidence_score ?? 0,
        reason: item.reason ?? "",
        status: isAccepted ? "accepted" : "rejected",
      });

      if (!isAccepted) continue;

      const isMapped = Boolean(item.id && item.id > 0);
      const diagnosisId = isMapped ? item.id : -Math.max(1, item.rank ?? unmappedCount + 1);
      addDiagnosis({
        id: diagnosisId,
        code: item.prescription_code ?? "",
        name: item.prescription_name ?? "",
        dose: item.dose ?? 0,
        time: item.time ?? 0,
        days: item.days ?? 0,
        reason: isMapped
          ? item.reason ?? ""
          : `[DB 미매칭] ${item.reason ?? "현재 진료 DB에 동일 처방 코드/명이 없습니다."}`,
      });
      if (isMapped) mappedCount += 1;
      else unmappedCount += 1;
    }

    setPrescriptionFeedback(feedback);

    if (aiSessionHistoryId !== null) {
      try {
        await savePrescriptionFeedback({
          historyId: aiSessionHistoryId,
          historyDiagnoseId: aiSessionHistoryDiagnoseId ?? undefined,
          feedbackItems: feedback.map((f) => ({
            rank: f.rank,
            prescriptionId: f.id > 0 ? f.id : undefined,
            prescriptionCode: f.prescription_code,
            prescriptionName: f.prescription_name,
            confidenceScore: f.confidence_score,
            reason: f.reason,
            status: f.status,
          })),
        });
      } catch (error) {
        console.error("처방 피드백 저장 실패:", error);
      }
    }

    const acceptedCount = feedback.filter((f) => f.status === "accepted").length;
    if (acceptedCount === 0) {
      alert("추천 처방을 모두 거부하였습니다. 피드백이 기록되었습니다.");
    } else if (mappedCount === 0) {
      alert("선택한 추천은 화면 반영만 되었고, DB 저장 가능한 항목은 없습니다.");
    } else {
      alert(`선택 반영 완료: DB 매칭 ${mappedCount}건, DB 미매칭 ${unmappedCount}건`);
    }
  }, [addDiagnosis, aiRecommendations, aiSessionHistoryDiagnoseId, aiSessionHistoryId, selectedRecommendationKeys, setPrescriptionFeedback]);

  const validationReasons = extractValidationReasons(validationModal);
  // 검증 결과가 아직 없는 동안(PENDING/RUNNING)에는 "그래프 근거 미확인" 을
  // 띄우지 않는다 — 아직 조회할 차례가 오지 않은 것이지 확인에 실패한 것이
  // 아니다. 결과가 도착한 뒤부터 세 상태를 구분해 표시한다.
  const graphNotice = validationModal?.result
    ? graphLookupNotice(
        (validationModal.result.validation as { graphLookup?: GraphLookup } | undefined)
          ?.graphLookup
      )
    : null;
  const validationTopItems = (
    validationModal?.result?.recommendedPrescriptions ??
    validationModal?.result?.candidatePrescriptions ??
    []
  ).slice(0, 3);

  return (
    <>
      <Modal
        open={Boolean(validationModal)}
        onClose={() => setValidationModal(null)}
        title="검증 완료"
        size="md"
        footer={
          <Button type="button" variant="secondary" onClick={() => setValidationModal(null)}>
            확인
          </Button>
        }
      >
        {validationModal && (
          <div className={styles.modalCard}>
            <div className={styles.modalCardHead}>
              <Badge tone={overallStatusTone(validationModal.result?.overallStatus)}>
                {validationModal.result?.overallStatus ?? validationModal.status}
              </Badge>
              {(() => {
                const notice = llmStatusNotice(validationModal.result?.llmStatus);
                if (!notice) return null;
                // overallStatus 배지(검증 결과)와 tone 이 같은 경우(WARNING/
                // NEEDS_REVIEW + fallback)가 있어 색만으로는 어느 쪽이 검증
                // 결과이고 어느 쪽이 모델 사용 여부인지 구분이 안 된다. 라벨
                // 텍스트("모델 미사용" 등)는 그대로 두고 앞에 짧은 구분자만 붙인다.
                return (
                  <span className={styles.llmStatusGroup}>
                    <span className={styles.llmStatusGroupLabel}>모델</span>
                    <Badge tone={notice.tone}>{notice.label}</Badge>
                  </span>
                );
              })()}
            </div>
            <p className={styles.modalReason}>
              {validationModal.result?.summary ?? validationModal.summary ?? "검증 결과를 확인했습니다."}
            </p>
            {(() => {
              const notice = verificationNotice(validationModal.result?.verification?.status);
              return notice ? (
                <div className={styles.modalVerification}>
                  <span className={styles.modalVerificationLabel}>근거</span>
                  <Badge tone={notice.tone}>{notice.label}</Badge>
                </div>
              ) : null;
            })()}
            {validationReasons.length > 0 && (
              <div className={styles.modalReasons}>
                <strong>검증 이유</strong>
                <ul>
                  {validationReasons.map((reason) => (
                    <li key={reason}>{reason}</li>
                  ))}
                </ul>
              </div>
            )}
            {graphNotice && (
              <div className={styles.modalGraphNotice}>
                <div className={styles.modalGraphNoticeHead}>
                  <span className={styles.modalVerificationLabel}>그래프</span>
                  <Badge tone={graphNotice.tone}>{graphNotice.label}</Badge>
                </div>
                <ul>
                  {graphNotice.lines.map((line) => (
                    <li key={line}>{line}</li>
                  ))}
                </ul>
              </div>
            )}
            {validationTopItems.map((item) => (
              <div
                key={`${item.rank}-${item.prescription_code}-${item.prescription_name}`}
                className={styles.modalName}
              >
                [{item.rank}] {item.prescription_name} ({item.prescription_code})
              </div>
            ))}
          </div>
        )}
      </Modal>

      <Modal
        open={Boolean(prescriptionPicker)}
        onClose={() => setPrescriptionPicker(null)}
        title="처방 상세 선택"
        size="md"
        footer={
          <Button type="button" variant="secondary" onClick={() => setPrescriptionPicker(null)}>
            닫기
          </Button>
        }
      >
        {prescriptionPicker && (
          <div className={styles.modalCard}>
            <p className={styles.modalReason}>
              AI 추천 처방과 가장 가까운 DB 처방을 검색해서 선택해주세요.
            </p>
            <div className={styles.prescriptionSearchRow}>
              <input
                type="text"
                value={prescriptionSearchDraft}
                className={styles.prescriptionSearchInput}
                placeholder="처방명 또는 코드 검색"
                aria-label="처방명 또는 코드 검색"
                onChange={(event) => setPrescriptionSearchDraft(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault();
                    handlePrescriptionSearchSubmit();
                  }
                }}
              />
              <Button
                type="button"
                variant="secondary"
                size="sm"
                disabled={prescriptionSearchLoading}
                onClick={handlePrescriptionSearchSubmit}
              >
                검색
              </Button>
            </div>
            {prescriptionSearchLoading ? (
              <EmptyState title="조회 중..." />
            ) : prescriptionSearchResults.length > 0 ? (
              <div className={styles.prescriptionResultList}>
                {prescriptionSearchResults.map((item) => (
                  <div key={item.id} className={styles.prescriptionResultItem}>
                    <div>
                      <div className={styles.modalCode}>{item.code}</div>
                      <div className={styles.modalName}>{item.name}</div>
                    </div>
                    <Button
                      type="button"
                      variant="secondary"
                      size="sm"
                      onClick={() => handleSelectPrescriptionDetail(item)}
                    >
                      선택
                    </Button>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyState title={prescriptionSearchError ?? "검색어를 입력해 처방을 조회해주세요."} />
            )}
          </div>
        )}
      </Modal>

      <Panel
        className={styles.container}
        title="처방"
        actions={
          <>
            {/*
              DR 구성에도 남는다. 누르면 서버가 503 과 함께 무슨 배포인지 문구로
              답하고(config/AiFeatures.java), handleGenerateByAI 의 catch 가 그
              문구를 alert 에 붙인다. 프론트가 배포 종류를 알게 하려면 그 값을
              번들에 박아야 하고, 그러면 DR 프론트가 별도 이미지가 된다.
            */}
            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={handleGenerateByAI}
              disabled={generating}
              loading={generating}
            >
              AI 처방 추천
            </Button>
            <Button
              type="button"
              variant="primary"
              size="sm"
              onClick={handleSave}
              disabled={diagnoses.length === 0 || saving}
              loading={saving}
            >
              저장
            </Button>
            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={clearDiagnoses}
              disabled={diagnoses.length === 0}
            >
              전체 삭제
            </Button>
          </>
        }
      >
        {aiRecommendations.length > 0 ? (
          <div className={styles.aiPanel}>
            <div className={styles.aiPanelHeader}>
              <span className={styles.aiPanelTitle}>
                <strong>AI 추천 처방</strong>
                {(() => {
                  const notice = llmStatusNotice(aiLlmStatus);
                  return notice ? <Badge tone={notice.tone}>{notice.label}</Badge> : null;
                })()}
                {(() => {
                  const outcomes = aiRecommendations.map((r) => getVerificationOutcome(r.rank));
                  const flagged = outcomes.filter((o) => o === "flagged").length;
                  const skipped = outcomes.filter((o) => o === "skipped").length;
                  if (flagged === 0 && skipped === 0 && responseOutcome === "ok") return null;
                  // flagged 와 skipped 를 한 숫자로 뭉치지 않는다(spec §7.3).
                  // "근거와 어긋난다"와 "대조할 근거가 없었다"는 다른 정보다.
                  const parts: string[] = [];
                  if (flagged > 0) parts.push(`근거 불일치 ${flagged}건`);
                  if (skipped > 0) parts.push(`미검증 ${skipped}건`);
                  // 항목 단위와 응답 단위를 한 숫자로 합치지 않고 두 줄로 낸다
                  // (최종 리뷰 M1). "3건 중 1건" 에 응답 단위 판정을 더하면
                  // 의사가 어느 처방 행을 봐야 하는지 알 수 없어진다.
                  const responseNotice =
                    responseOutcome === "ok" ? null : verificationNotice(responseOutcome);
                  return (
                    <>
                      {parts.length > 0 ? (
                        <span className={styles.verificationSummary}>
                          {`검증: ${aiRecommendations.length}건 중 ${parts.join(", ")}`}
                        </span>
                      ) : null}
                      {responseNotice ? (
                        <span className={styles.verificationSummary}>
                          {`검증(응답 전체): ${responseNotice.label}`}
                        </span>
                      ) : null}
                    </>
                  );
                })()}
              </span>
              <Button type="button" variant="secondary" size="sm" onClick={handleApplySelectedRecommendations}>
                선택 처방 반영
              </Button>
            </div>
            {(() => {
              const notice = renalGateNotice(aiRenalGate);
              if (!notice) return null;
              return (
                <div className={styles.renalBanner} data-tone={notice.tone}>
                  <div className={styles.renalBannerHead}>
                    <span className={styles.modalVerificationLabel}>신기능</span>
                    <Badge tone={notice.tone}>{notice.label}</Badge>
                  </div>
                  {/* 환자 축. 판정 축과 한 줄로 합치지 않는다 — "신기능 저하인데
                      이 약들은 표 밖" 과 "신기능을 못 읽어서 판정 불가" 가 같아
                      보이면 이 관문이 있는 이유가 사라진다. */}
                  <p className={styles.renalBannerPatient}>{notice.patientLine}</p>
                  {notice.lines.length > 0 && (
                    <ul>
                      {notice.lines.map((line) => (
                        <li key={line}>{line}</li>
                      ))}
                    </ul>
                  )}
                </div>
              );
            })()}
            <Table dense>
              <thead>
                <tr>
                  <th scope="col">선택</th>
                  <th scope="col">추천 처방</th>
                  <th scope="col">상세 선택</th>
                </tr>
              </thead>
              <tbody>
                {aiRecommendations.map((item) => {
                  const key = recommendationKey(item);
                  return (
                    <tr key={key}>
                      <td>
                        <input
                          type="checkbox"
                          checked={selectedRecommendationKeys.includes(key)}
                          onChange={() => toggleRecommendation(key)}
                          aria-label={`${item.prescription_name} 반영 여부`}
                        />
                      </td>
                      <td>
                        [{item.rank}] {item.prescription_name} ({item.prescription_code})
                        {(() => {
                          const outcome = getVerificationOutcome(item.rank);
                          if (outcome === "ok") return null;
                          const notice = verificationNotice(
                            outcome === "flagged" ? "flagged" : "skipped"
                          );
                          return <Badge tone={notice!.tone}>{notice!.label}</Badge>;
                        })()}
                        {(() => {
                          const notice = getRenalItemNotice(item.rank);
                          return notice ? <Badge tone={notice.tone}>{notice.label}</Badge> : null;
                        })()}
                      </td>
                      <td>
                        <Button type="button" variant="secondary" size="sm" onClick={() => openPrescriptionPicker(item)}>
                          처방 상세 선택
                        </Button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </Table>
          </div>
        ) : aiNoCandidates ? (
          // 설계 §3.2 가 말하는 "유용한 신호". 추천 표가 사라지기만 하면
          // 의사는 요청이 실패한 것과 구분할 수 없다. 조회 실패는 이 자리에
          // 오지 않는다 — graphLookupFoundNothing 이 걸러낸다(GC-3).
          <div className={styles.aiPanel}>
            <div className={styles.aiPanelHeader}>
              <span className={styles.aiPanelTitle}>
                <strong>AI 추천 처방</strong>
                <Badge tone="warning">데이터가 뒷받침하는 처방 후보 없음</Badge>
                {(() => {
                  const notice = llmStatusNotice(aiLlmStatus);
                  return notice ? <Badge tone={notice.tone}>{notice.label}</Badge> : null;
                })()}
              </span>
            </div>
            <EmptyState
              title="이 상병에 대해 조회된 처방 후보가 0건입니다."
              description="없는 추천을 만들지 않았습니다 — 조회 실패가 아니라 조회 결과입니다. 검증 요약에서 그래프 조회 근거를 확인하세요."
            />
          </div>
        ) : null}
        {diagnoses.length === 0 ? (
          <EmptyState
            title="선택된 처방이 없습니다."
            description="오른쪽 데이터베이스에서 더블클릭하여 추가하세요."
          />
        ) : (
          <Table>
            <thead>
              <tr>
                <th scope="col">No.</th>
                <th scope="col">ID</th>
                <th scope="col">코드</th>
                <th scope="col">처방명</th>
                <th scope="col">삭제</th>
              </tr>
            </thead>
            <tbody>
              {diagnoses.map((item, index) => (
                <Fragment key={`${item.id}-${index}`}>
                  <tr>
                    <td>{index + 1}</td>
                    <td>{item.id > 0 ? item.id : "미매칭"}</td>
                    <td className={styles.code}>{item.code}</td>
                    <td>{item.name}</td>
                    <td>
                      <Button type="button" variant="danger" size="sm" onClick={() => removeDiagnosis(item.id)}>
                        삭제
                      </Button>
                    </td>
                  </tr>
                  <tr className={styles.reasonRow}>
                    <td colSpan={5} className={styles.reasonCell}>
                      <strong>AI 추천 사유</strong>
                      <p className={styles.reasonText}>{item.reason ?? "-"}</p>
                    </td>
                  </tr>
                </Fragment>
              ))}
            </tbody>
          </Table>
        )}
      </Panel>
    </>
  );
}
