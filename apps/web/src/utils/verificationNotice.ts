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

// 한 target 에 붙은 검사들을 하나의 판정으로 접는다. fail-closed:
// checks 가 없거나 그 target 의 검사가 하나도 없으면 "통과" 가 아니라 skipped 다.
// "ok"/"flagged" 정확 일치가 아닌 계약 밖 값도 ok 로 새지 않는다.
function outcomeForTarget(
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

// 항목 단위 표시(spec §7.2). 전역 배지 하나로 뭉치면 어느 처방이 문제인지
// 알 수 없고, 그건 표시하지 않는 것과 크게 다르지 않다.
export function itemVerificationOutcome(
  verification: Verification | null | undefined,
  target: string
): VerificationOutcome {
  return outcomeForTarget(verification, target);
}

// 응답 단위 표시(spec §7.2, 최종 리뷰 M1). schema_top3 는 target="response" 라
// 항목별 집계에 절대 들어가지 않는다 — 항목 outcome 만 세면 이 검사는 무엇을
// 보고하든 처방 화면에 나타나지 않는다.
//
// 항목 판정과 **합치지 않고 따로** 낸다. "표의 어느 행이 문제인가" 와 "응답
// 전체의 형태가 문제인가" 는 의사에게 다른 정보이고, 한 숫자로 뭉치면 어느
// 쪽인지 알 수 없다 — §7.3 이 flagged 와 skipped 를 뭉치지 말라고 하는 것과
// 같은 이유다.
export const RESPONSE_TARGET = "response";

export function responseVerificationOutcome(
  verification: Verification | null | undefined
): VerificationOutcome {
  return outcomeForTarget(verification, RESPONSE_TARGET);
}
