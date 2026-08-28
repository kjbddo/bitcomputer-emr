"use client";

import { Fragment, useCallback, useEffect, useRef, useState } from "react";
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
      reasons.push(`${action}: ${observationText}`);
    }
  });

  return Array.from(new Set(reasons.filter(Boolean))).slice(0, 6);
}

function extractPubmedReferences(job: ValidationJobResponse | null): string[] {
  const validation = job?.result?.validation;
  const pubmedEvidence =
    validation && typeof validation === "object" && Array.isArray(validation.pubmedEvidence)
      ? validation.pubmedEvidence
      : [];
  const summary =
    validation && typeof validation === "object"
      ? asText(validation.pubmedEvidenceSummary)
      : "";

  const references = pubmedEvidence.slice(0, 3).flatMap((article) => {
    if (!article || typeof article !== "object") return [];
    const row = article as Record<string, unknown>;
    const title = asText(row.title);
    const pmid = asText(row.pmid);
    const source = asText(row.source);
    const pubdate = asText(row.pubdate);
    const abstractSnippet = asText(row.abstractSnippet);
    if (!title) return [];
    const meta = [source, pubdate, pmid ? `PMID ${pmid}` : ""].filter(Boolean).join(", ");
    return [`${title}${meta ? ` (${meta})` : ""}${abstractSnippet ? ` - 초록: ${abstractSnippet}` : ""}`];
  });
  return summary ? [`근거 요약: ${summary}`, ...references] : references;
}

export default function Diagnosis({ clinicVisit, ensureHistory, employeeId, onHistoryUpdated }: DiagnosisProps) {
  const { diseases, diagnoses, prescriptionFeedback, addDiagnosis, removeDiagnosis, clearDiagnoses, setPrescriptionFeedback, clearPrescriptionFeedback } = useMedicalSelection();
  const [saving, setSaving] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [aiRecommendations, setAiRecommendations] = useState<RecommendedPrescriptionItem[]>([]);
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
      setSelectedRecommendationKeys([]);
      setPrescriptionPicker(null);
      setAiSessionHistoryId(null);
      setAiSessionHistoryDiagnoseId(null);
    }
  }, [clearDiagnoses, clearPrescriptionFeedback, clinicVisit?.patientId]);

  useEffect(() => {
    clearPrescriptionFeedback();
    setAiRecommendations([]);
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
        alert(
          "AI 추천/검증 결과가 비어 있습니다. 검증 요약을 확인해주세요."
        );
        setValidationModal(job);
        return;
      }

      setAiRecommendations(recommended);
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
    setPrescriptionPicker(null);
  }, [prescriptionPicker]);

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
  const pubmedReferences = extractPubmedReferences(validationModal);
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
            </div>
            <p className={styles.modalReason}>
              {validationModal.result?.summary ?? validationModal.summary ?? "검증 결과를 확인했습니다."}
            </p>
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
            {pubmedReferences.length > 0 && (
              <div className={styles.modalReferences}>
                <strong>PubMed 참고 근거</strong>
                <ul>
                  {pubmedReferences.map((reference) => (
                    <li key={reference}>{reference}</li>
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
              <strong>AI 추천 처방</strong>
              <Button type="button" variant="secondary" size="sm" onClick={handleApplySelectedRecommendations}>
                선택 처방 반영
              </Button>
            </div>
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
