// 신기능 금기 관문(services/prescription/renal_gate.py)의 화면 표시.
//
// **축이 둘이다.** 하나로 합치면 이 부품이 무의미해진다.
//
//   renalStatus  환자 상태. 자유텍스트 노트 파싱 결과
//                impaired | suspected | undetermined
//   status/outcome  판정. 그 약이 신배설 금기 표 안에 있는가
//                warn | clear | unknown
//
// 파싱 실패는 item outcome 이 아니라 renalStatus 에 나타난다. 그래서
// `renalStatus="undetermined"` 인데 항목이 전부 `clear` 인 조합이 실재하고,
// 그때의 `clear` 는 "금기 없음"을 뜻하지 않는다 — 화면이 renalStatus 를 빼고
// outcome 만 렌더하면 정확히 그 오독이 생긴다.
//
// `clear` 를 환자 근거로 내는 경로는 파이썬에 아예 없다. 자유텍스트가 "신장
// 정상"이라고 말해 주지 않기 때문이다. 그러므로 **완전히 깨끗한 상태가 없고**,
// 관문 결과가 있으면 배너를 항상 띄운다 — llmStatus/verification 처럼 "정상이면
// 무표시" 하지 않는다. 대신 tone 으로 심각도를 가른다.
//
// 항목별 `evidence` 는 표의 좁은 범위를 문장으로 들고 다닌다("신배설 금기
// 표(11개 성분)에 없는 성분입니다 — 이 표의 범위 안에서 해당 없음"). 버리면
// 그 한정이 사라져 "안전함"으로 읽힌다.

export type RenalGateItem = {
  rank?: number | null;
  name?: string | null;
  prescriptionCode?: string | null;
  outcome?: string | null;
  ingredient?: string | null;
  evidence?: string | null;
};

export type RenalGate = {
  status?: string | null;
  renalStatus?: string | null;
  renalEvidence?: string | null;
  undeterminedReason?: string | null;
  items?: RenalGateItem[] | null;
};

export type RenalGateNotice = {
  label: string;
  tone: "danger" | "warning" | "neutral";
  /** 환자 축. 판정 축과 절대 합치지 않는다. */
  patientLine: string;
  /** 판정 축. 항목별 evidence 원문. */
  lines: string[];
};

const UNVERIFIED: RenalGateNotice = {
  label: "신기능 관문 미확인",
  tone: "warning",
  patientLine: "신기능 금기 관문 결과를 확인하지 못했습니다.",
  lines: ["관문을 돌리지 못한 것은 '금기 없음'이 아닙니다."],
};

function patientLine(gate: RenalGate): string {
  const evidence = String(gate.renalEvidence ?? "").trim();
  const reason = String(gate.undeterminedReason ?? "").trim();
  const detail = evidence || reason;
  const suffix = detail ? ` — ${detail}` : "";
  switch (gate.renalStatus) {
    case "impaired":
      return `신기능 저하 확인${suffix}`;
    case "suspected":
      return `신기능 저하 의심${suffix}`;
    default:
      // undetermined 및 계약 밖 값. "확인 못 함"이지 "정상"이 아니다.
      return `신기능 미확정${suffix}`;
  }
}

function itemLines(gate: RenalGate): string[] {
  const items = Array.isArray(gate.items) ? gate.items : [];
  return items
    .map((item) => {
      const evidence = String(item?.evidence ?? "").trim();
      if (!evidence) return "";
      const name = String(item?.name ?? "").trim();
      const rank = item?.rank;
      const head = [rank != null ? `[${rank}]` : "", name].filter(Boolean).join(" ");
      return head ? `${head}: ${evidence}` : evidence;
    })
    .filter(Boolean);
}

export function renalGateNotice(
  gate: RenalGate | null | undefined
): RenalGateNotice | null {
  if (!gate || typeof gate !== "object") return UNVERIFIED;

  const lines = itemLines(gate);
  const line = patientLine(gate);

  if (gate.status === "warn") {
    return { label: "신배설 금기 경고", tone: "danger", patientLine: line, lines };
  }
  if (gate.status === "clear") {
    // 표 밖이라는 판정. 환자 축이 어떻든 "안전함"이 아니므로 배너는 남는다.
    return { label: "신배설 금기 표 범위 밖", tone: "neutral", patientLine: line, lines };
  }
  // unknown 및 계약 밖 값 — fail-closed.
  return { label: "신기능 판정 불가", tone: "warning", patientLine: line, lines };
}

export function renalItemNotice(
  gate: RenalGate | null | undefined,
  rank: number
): { label: string; tone: "danger" | "warning" } | null {
  if (!gate || typeof gate !== "object") {
    return { label: "신기능 미확인", tone: "warning" };
  }
  const items = Array.isArray(gate.items) ? gate.items : [];
  const mine = items.find((item) => item?.rank === rank);
  // 그 순위의 판정이 없으면 통과로 읽지 않는다(GC-3).
  if (!mine) return { label: "신기능 미확인", tone: "warning" };
  if (mine.outcome === "warn") return { label: "신배설 금기", tone: "danger" };
  if (mine.outcome === "clear") return null;
  return { label: "신기능 판정 불가", tone: "warning" };
}
