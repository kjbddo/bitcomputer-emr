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

// 구조 검사(STRUCTURAL_CHECK_IDS): 출력의 형태만 보고 조회 데이터와 대조하지
// 않는다 — grounding 을 확립하지 못한다(GC-2). 값은
// services/prescription/verification_contract.py 및
// services/validation-agent/app/verification_contract.py 의 동일 이름
// 상수와 반드시 일치해야 한다(그 두 파일은 본문 동일성 테스트로 서로
// 묶여 있다). 어긋나면 __tests__/structuralCheckIds.sync.test.ts 가
// 두 파이썬 소스를 직접 파싱해 이 배열과 비교하며 실패한다 — 이 배열을
// 손으로 고칠 때는 그 테스트도 함께 통과하는지 반드시 확인할 것.
export const STRUCTURAL_CHECK_IDS: ReadonlySet<string> = new Set([
  "schema_top3",
  "confidence_in_range",
  "trace_step_has_observation",
  "candidates_from_finder",
  // 처방코드가 이 데이터셋의 약제 코드 형태인지만 본다 — 조회 데이터와
  // 대조하지 않으므로 grounding 을 확립하지 못한다(F-H1). 다만 flagged 는
  // 항목 배지를 그대로 빨갛게 만든다: 구조 검사의 거부권을 뺀 것은 skipped
  // 에 대해서지 flagged 에 대해서가 아니다.
  "code_is_medication",
]);

// 항목 단위 표시(spec §7.2). 전역 배지 하나로 뭉치면 어느 처방이 문제인지
// 알 수 없고, 그건 표시하지 않는 것과 크게 다르지 않다.
//
// IMP-2: 항목의 검사 중 구조 검사(예: confidence_in_range)만 skipped 이고
// 나머지 근거 검사(code_in_candidates·name_matches_code)가 실제 조회 후보와
// 대조해 전부 ok 인 경우, 구조 검사 하나가 그 grounding 을 혼자 뒤집어서는
// 안 된다 — Python 의 aggregate_status(verification_contract.py)가
// `status` 필드에서 "구조 검사만으로는 passed 가 되지 않지만, 구조 검사가
// 근거 검사의 ok 를 무효화하지도 않는다"는 원칙을 이미 지키고 있는데, 이
// 항목 단위 접기만 그 원칙에서 벗어나 있었다. 다만 거부권만 없앨 뿐
// 발언권을 주지는 않는다: 근거 검사가 하나도 없으면(GC-3 fail-closed)
// 여전히 skipped 이고, 구조 검사가 실제로 flagged 면(형식이 진짜로
// 깨졌다는 신호) 여전히 눈에 띈다.
//
// 응답 단위(responseVerificationOutcome)는 이 예외를 적용하지 않는다 — 거기서
// schema_top3(prescription) 류 구조 검사는 grounding 의 일부가 아니라
// "응답 형태 자체가 온전한가"라는 그 자체로 완결된, 다른 주장(spec §7.2
// 응답 줄)이기 때문이다. 항목 줄만 "이 행이 실제 후보와 대조됐나"라는
// grounding 주장이라 구조 검사의 거부권을 특별히 배제한다.
export function itemVerificationOutcome(
  verification: Verification | null | undefined,
  target: string
): VerificationOutcome {
  const checks = verification?.checks;
  if (!Array.isArray(checks)) return "skipped";
  const mine = checks.filter((c) => c && c.target === target);
  if (mine.length === 0) return "skipped";
  if (mine.some((c) => c.outcome === "flagged")) return "flagged";
  const grounding = mine.filter((c) => !STRUCTURAL_CHECK_IDS.has(c.id));
  if (grounding.length === 0) return "skipped";
  if (grounding.every((c) => c.outcome === "ok")) return "ok";
  return "skipped";
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
