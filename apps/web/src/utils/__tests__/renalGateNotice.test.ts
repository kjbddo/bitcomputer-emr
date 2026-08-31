import { describe, expect, it } from "vitest";

import { renalGateNotice, renalItemNotice } from "@/utils/renalGateNotice";

const WARN_GATE = {
  status: "warn",
  renalStatus: "impaired",
  renalEvidence: "GFR 13",
  undeterminedReason: null,
  items: [
    {
      rank: 1,
      name: "다이아벡스정500mg",
      prescriptionCode: "641600390",
      outcome: "warn",
      ingredient: "메트포르민",
      evidence: "메트포르민: 젖산산증 위험. 특이사항에서 확인된 신기능 지표: GFR 13",
    },
    {
      rank: 2,
      name: "레바트정",
      prescriptionCode: "693900170",
      outcome: "clear",
      ingredient: null,
      evidence: "신배설 금기 표(11개 성분)에 없는 성분입니다 — 이 표의 범위 안에서 해당 없음.",
    },
  ],
};

describe("renalGateNotice — 두 축을 합치지 않는다", () => {
  it("warn 이면 danger 이고 환자 축과 판정 축을 따로 낸다", () => {
    const notice = renalGateNotice(WARN_GATE);

    expect(notice?.tone).toBe("danger");
    expect(notice?.patientLine).toContain("신기능 저하 확인");
    expect(notice?.patientLine).toContain("GFR 13");
    // 항목 evidence 가 표의 범위를 문장으로 들고 다닌다 — 버리면 안 된다.
    expect(notice?.lines.some((l) => l.includes("젖산산증"))).toBe(true);
  });

  it("clear 라도 신기능 미확정이면 '해당 없음'으로 읽히면 안 된다", () => {
    const notice = renalGateNotice({
      status: "clear",
      renalStatus: "undetermined",
      renalEvidence: "",
      undeterminedReason: "노트에 신기능 지표가 없습니다",
      items: [
        {
          rank: 1,
          name: "레바트정",
          prescriptionCode: "693900170",
          outcome: "clear",
          ingredient: null,
          evidence: "신배설 금기 표(11개 성분)에 없는 성분입니다 — 이 표의 범위 안에서 해당 없음.",
        },
      ],
    });

    // 배너 자체가 사라지면 안 된다. clear 는 "안전함"이 아니다.
    expect(notice).not.toBeNull();
    expect(notice?.patientLine).toContain("신기능 미확정");
    expect(notice?.patientLine).toContain("노트에 신기능 지표가 없습니다");
    expect(notice?.lines.some((l) => l.includes("이 표의 범위 안에서"))).toBe(true);
  });

  it("신기능 저하가 확인됐는데 약이 표 밖이면 그 사실을 그대로 말한다", () => {
    const notice = renalGateNotice({
      status: "clear",
      renalStatus: "impaired",
      renalEvidence: "CKD",
      undeterminedReason: null,
      items: [
        {
          rank: 1,
          name: "레바트정",
          prescriptionCode: "693900170",
          outcome: "clear",
          ingredient: null,
          evidence: "신배설 금기 표(11개 성분)에 없는 성분입니다 — 이 표의 범위 안에서 해당 없음.",
        },
      ],
    });

    expect(notice?.patientLine).toContain("신기능 저하 확인");
    expect(notice?.patientLine).toContain("CKD");
  });

  it("unknown 은 warning 이고 판정 불가라고 말한다", () => {
    const notice = renalGateNotice({
      status: "unknown",
      renalStatus: "suspected",
      renalEvidence: "r/o CKD",
      undeterminedReason: null,
      items: [
        {
          rank: 1,
          name: "다이아벡스정500mg",
          prescriptionCode: "641600390",
          outcome: "unknown",
          ingredient: "메트포르민",
          evidence: "메트포르민: 젖산산증 위험. 이 환자의 신기능을 확정하지 못했습니다 (r/o CKD) — '해당 없음'이 아닙니다.",
        },
      ],
    });

    expect(notice?.tone).toBe("warning");
    expect(notice?.patientLine).toContain("신기능 저하 의심");
    expect(notice?.lines.some((l) => l.includes("'해당 없음'이 아닙니다"))).toBe(true);
  });

  // PR #21 이후의 실제 조합: 신기능 저하는 확인됐는데 추천 항목이 전부
  // 플레이스홀더라 대조 자체가 불가능한 경우. E78(고지혈증)이 약제 후보 0건이라
  // 이 경로를 그대로 탄다. 환자 축은 impaired 인데 판정 축은 unknown 이다 —
  // 두 축을 합치면 이 조합을 표현할 수 없다.
  it("신기능 저하 확인 + 대조 불가면 환자 축과 판정 축이 서로 다른 말을 한다", () => {
    const notice = renalGateNotice({
      status: "unknown",
      renalStatus: "impaired",
      renalEvidence: "신부전 4/5단계 GFR 13",
      undeterminedReason: null,
      items: [
        {
          rank: 1,
          name: "데이터 부족",
          prescriptionCode: "미기재",
          outcome: "unknown",
          ingredient: null,
          evidence: "추천 항목이 없는 순위입니다 — 대조할 약이 없습니다.",
        },
      ],
    });

    expect(notice?.label).toBe("신기능 판정 불가");
    expect(notice?.tone).toBe("warning");
    expect(notice?.patientLine).toContain("신기능 저하 확인");
    expect(notice?.patientLine).toContain("GFR 13");
    expect(notice?.lines.some((l) => l.includes("대조할 약이 없습니다"))).toBe(true);
  });

  it("관문 결과가 없으면 clear 라고 하지 않고 미확인으로 낸다", () => {
    expect(renalGateNotice(null)?.label).toBe("신기능 관문 미확인");
    expect(renalGateNotice(undefined)?.tone).toBe("warning");
  });
});

describe("renalItemNotice — 항목별 배지", () => {
  it("warn 항목은 danger", () => {
    expect(renalItemNotice(WARN_GATE, 1)).toEqual({
      label: "신배설 금기",
      tone: "danger",
    });
  });

  it("clear 항목은 배지를 붙이지 않는다 — 범위 한정은 배너가 들고 있다", () => {
    expect(renalItemNotice(WARN_GATE, 2)).toBeNull();
  });

  it("unknown 항목은 warning", () => {
    const gate = {
      ...WARN_GATE,
      items: [{ ...WARN_GATE.items[0], outcome: "unknown" }],
    };
    expect(renalItemNotice(gate, 1)?.tone).toBe("warning");
  });

  it("관문 결과가 없으면 항목도 미확인이다", () => {
    expect(renalItemNotice(null, 1)?.label).toBe("신기능 미확인");
  });

  it("그 rank 의 판정이 없으면 통과로 읽지 않는다", () => {
    expect(renalItemNotice(WARN_GATE, 9)?.label).toBe("신기능 미확인");
  });
});
