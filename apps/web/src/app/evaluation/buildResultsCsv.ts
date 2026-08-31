// Next.js App Router 의 page.tsx 는 정해진 이름만 export 할 수 있다.
// 테스트가 이 함수를 부르려면 별도 모듈이어야 한다.
import type { DocumentEvaluateResponse } from "@/services/agent";

export type BatchResult = {
  rowNumber: number;
  diseaseCode: string;
  prescriptionCode: string;
  prescriptionName: string;
  status: "success" | "error";
  medicalCertificate?: string;
  /** 소견이 실제로 모델에서 나왔는지: "real" | "stub" | "fallback". CSV로도 내보내진다. */
  llmStatus?: string | null;
  generateRawResponse?: unknown;
  evaluateRawResponse?: DocumentEvaluateResponse;
  error?: string;
};

function escapeCsvCell(value: unknown): string {
  const text = String(value ?? "");
  const escaped = text.replace(/"/g, '""');
  return `"${escaped}"`;
}

export function buildResultsCsv(results: BatchResult[]): string {
  const header = [
    "rowNumber",
    "diseaseCode",
    "prescriptionCode",
    "prescriptionName",
    "status",
    "medicalCertificate",
    "llmStatus",
    "score",
    "entailmentCount",
    "totalPairs",
    "premise",
    "details",
    "error",
  ];

  const lines = results.map((item) => {
    const evaluation = item.evaluateRawResponse;
    return [
      item.rowNumber,
      item.diseaseCode,
      item.prescriptionCode,
      item.prescriptionName,
      item.status,
      item.medicalCertificate ?? "",
      item.llmStatus ?? "",
      evaluation?.score ?? "",
      evaluation?.entailmentCount ?? "",
      evaluation?.totalPairs ?? "",
      evaluation?.premise ?? "",
      evaluation ? JSON.stringify(evaluation.details) : "",
      item.error ?? "",
    ]
      .map(escapeCsvCell)
      .join(",");
  });

  return [header.map(escapeCsvCell).join(","), ...lines].join("\r\n");
}
