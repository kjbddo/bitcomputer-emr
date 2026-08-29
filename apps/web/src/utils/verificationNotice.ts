// verification 은 "출력이 조회 결과로 추적되나"다. llmStatus("모델이 돌았나")와
// 다른 축이므로 같은 자리에 같은 모양으로 쌓지 않는다(spec §7.1).
//
// "passed" 정확 일치만 무표시다. 값이 없거나 계약 밖이면 미검증으로 본다 —
// 이 프로젝트의 다른 모든 경계와 같은 방향(fail-closed)이다.

export type VerificationOutcome = "ok" | "flagged" | "skipped";

export type VerificationCheck = {
  id: string;
  target: string;
  outcome: string;
  evidence: string;
};

export type Verification = {
  status?: string | null;
  checks?: VerificationCheck[] | null;
  skippedReason?: string | null;
};

export function verificationNotice(
  status: string | null | undefined
): { label: string; tone: "danger" | "warning" } | null {
  if (status === "passed") return null;
  if (status === "flagged") {
    return { label: "근거 불일치", tone: "danger" };
  }
  return { label: "미검증", tone: "warning" };
}

// 항목 단위 표시(spec §7.2). 전역 배지 하나로 뭉치면 어느 처방이 문제인지
// 알 수 없고, 그건 표시하지 않는 것과 크게 다르지 않다.
export function itemVerificationOutcome(
  verification: Verification | null | undefined,
  target: string
): VerificationOutcome {
  const checks = verification?.checks;
  if (!Array.isArray(checks)) return "skipped";
  const mine = checks.filter((c) => c && c.target === target);
  if (mine.length === 0) return "skipped";
  if (mine.some((c) => c.outcome === "flagged")) return "flagged";
  if (mine.every((c) => c.outcome === "ok")) return "ok";
  return "skipped";
}
