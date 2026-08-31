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
  // 모델을 부르지 않았다. "fallback"(불렀는데 실패)과 구분한다 — 둘 다 "모델이
  // 만들지 않았다" 지만, 이쪽은 설계대로 돈 결정론적 판정이지 장애가 아니다.
  // validation-agent 는 모델을 부르는 자리가 없어져 정상 실행이 언제나 이 값이다.
  // 여기에 warning 을 붙이면 모든 검증마다 경고가 떠서 곧 아무도 읽지 않게 되고,
  // 그러면 진짜 fallback 이 그 소음에 묻힌다. tone 만 낮추고 표시는 유지한다 —
  // "모델이 만든 것이 아니다" 는 여전히 화면에 남아야 한다(GC-3).
  if (llmStatus === "rule") {
    return { label: "규칙 기반 판정 — 모델 미호출", tone: "neutral" };
  }
  // 조회 후보가 0건이라 처방 서비스가 모델을 아예 부르지 않았다(설계 §3.2).
  // "미확인"으로 뭉개면 아는 것을 모른다고 말하는 것이고, tone 은 경고가
  // 아니다 — 무언가 잘못돼서 모델이 빠진 것이 아니라, 설명할 항목이 없어서
  // 부르지 않은 정상 경로다.
  if (llmStatus === "skipped") {
    return { label: "조회 후보 없음 — 모델 미호출", tone: "neutral" };
  }
  return { label: "모델 출처 미확인", tone: "warning" };
}
