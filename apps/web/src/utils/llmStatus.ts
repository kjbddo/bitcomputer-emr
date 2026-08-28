// llmStatus 는 이번 요청이 실제로 어느 경로로 갔는지다(설정이 아니다).
// "real" 이 아닌 모든 경우 — 값이 없는 경우 포함 — 를 드러낸다. 필드가 빠진 응답을
// 조용히 "모델이 돌았다"로 읽으면 이 표시가 존재할 이유가 사라진다.
export function llmStatusNotice(
  llmStatus: string | null | undefined
): { label: string; tone: "warning" | "neutral" } | null {
  if (llmStatus === "real") return null;
  if (llmStatus === "stub") {
    return { label: "스텁 응답 (모델 미사용)", tone: "neutral" };
  }
  return { label: "규칙 기반 결과 — 모델 미사용", tone: "warning" };
}
