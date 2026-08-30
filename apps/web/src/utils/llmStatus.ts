// llmStatus 는 이번 요청이 실제로 어느 경로로 갔는지다(설정이 아니다).
// "real" 이 아닌 모든 경우 — 값이 없는 경우 포함 — 를 드러낸다. 필드가 빠진 응답을
// 조용히 "모델이 돌았다"로 읽으면 이 표시가 존재할 이유가 사라진다.
//
// 값이 없거나 계약 밖인 경우는 "폴백"과 구분한다. 둘 다 배지가 뜨는 것은
// 같지만(fail-closed) 말하는 내용이 다르다 — "규칙으로 만들었다"는 확립된
// 사실일 때만 할 수 있는 주장이고, 필드가 없을 때 그 문구를 쓰면 모르는 것을
// 아는 것처럼 말하게 된다(GC-2). 계약값은 "real" | "stub" | "fallback" 뿐이다
// (services/validation-agent/app/models.py, services/prescription/*_api.py).
export function llmStatusNotice(
  llmStatus: string | null | undefined
): { label: string; tone: "warning" | "neutral" } | null {
  if (llmStatus === "real") return null;
  if (llmStatus === "stub") {
    return { label: "스텁 응답 (모델 미사용)", tone: "neutral" };
  }
  if (llmStatus === "fallback") {
    return { label: "규칙 기반 결과 — 모델 미사용", tone: "warning" };
  }
  return { label: "모델 출처 미확인", tone: "warning" };
}
