// graphLookup 은 "이 추천이 그래프 조회 결과 위에 서 있나"다. verification
// ("출력이 조회 결과로 추적되나")·llmStatus("모델이 돌았나")와 다른 축이므로
// 별도로 낸다.
//
// 세 상태를 구분한다(설계 문서 §3.2, GC-3 fail-closed).
//
//   근거 있음      과거 처방/코호트 처방을 실제로 참고했다 — 표시하지 않는다
//   0건            조회했고 뒷받침하는 처방이 정말 없다. E78(고지혈증)이 실제 사례다
//   확인 못 함     조회 실패, 또는 후보 조회 단계 자체를 돌지 않았다
//
// "확인 못 함"을 "0건"으로 읽히게 하면 모르는 것을 아는 것처럼 말하게 된다.

export type GraphLookup = {
  status?: string | null;
  usedArangoTopRx?: boolean | null;
  arangoTopRxCount?: number | null;
  usedCohortRx?: boolean | null;
  cohortRxCount?: number | null;
  foundNothing?: boolean | null;
  evidence?: unknown;
};

export type GraphLookupNotice = {
  label: string;
  tone: "warning" | "neutral";
  lines: string[];
};

function evidenceLines(lookup: GraphLookup): string[] {
  return Array.isArray(lookup.evidence)
    ? lookup.evidence.map((line) => String(line)).filter(Boolean)
    : [];
}

export function graphLookupNotice(
  lookup: GraphLookup | null | undefined
): GraphLookupNotice | null {
  // 후보 조회 단계를 아예 돌지 않았다. 트레이스가 그 사실을 남기지만 화면에도
  // 드러나야 한다 — 조용히 생략하면 "확인했는데 문제 없었다"로 읽힌다.
  if (!lookup || typeof lookup !== "object") {
    return {
      label: "그래프 근거 미확인",
      tone: "warning",
      lines: ["처방 그래프 조회 결과를 확인하지 못했습니다."],
    };
  }
  if (lookup.status === "FAILED") {
    return {
      label: "그래프 근거 미확인",
      tone: "warning",
      lines: evidenceLines(lookup).length
        ? evidenceLines(lookup)
        : ["처방 그래프를 조회하지 못했습니다."],
    };
  }
  if (lookup.foundNothing === true) {
    return {
      label: "그래프 근거 0건",
      tone: "warning",
      lines: [
        ...evidenceLines(lookup),
        "그래프 근거 없이 생성된 추천입니다. 평소보다 보수적으로 확인하세요.",
      ],
    };
  }
  // 근거가 있으면 배지를 띄우지 않는다. verificationNotice("passed" 무표시)와
  // 같은 원칙 — 정상 경로에 표시를 쌓지 않는다.
  return null;
}
