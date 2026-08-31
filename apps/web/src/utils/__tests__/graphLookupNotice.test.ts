import { describe, expect, it } from "vitest";

import { graphLookupFoundNothing, graphLookupNotice } from "@/utils/graphLookupNotice";

describe("graphLookupNotice", () => {
  it("근거가 있으면 표시하지 않는다", () => {
    expect(
      graphLookupNotice({
        status: "LOADED",
        arangoTopRxCount: 7,
        cohortRxCount: 3,
        foundNothing: false,
        evidence: ["환자 그래프에서 이 환자의 과거 처방 7건을 참고했습니다."],
      })
    ).toBeNull();
  });

  it("0건이면 근거 문장과 경고를 함께 낸다", () => {
    const notice = graphLookupNotice({
      status: "LOADED",
      arangoTopRxCount: 0,
      cohortRxCount: 0,
      foundNothing: true,
      evidence: ["환자 그래프에서 이 환자의 과거 처방을 찾지 못했습니다 (0건)."],
    });

    expect(notice?.label).toBe("그래프 근거 0건");
    expect(notice?.lines[0]).toContain("찾지 못했습니다");
    expect(notice?.lines.at(-1)).toContain("보수적으로");
  });

  it("조회 실패는 0건과 다른 문구를 낸다", () => {
    const notice = graphLookupNotice({
      status: "FAILED",
      foundNothing: false,
      evidence: ["처방 그래프를 조회하지 못했습니다: boom"],
    });

    expect(notice?.label).toBe("그래프 근거 미확인");
    expect(notice?.lines[0]).toContain("조회하지 못했습니다");
  });

  it("값이 없으면 0건이라고 주장하지 않고 미확인으로 낸다", () => {
    expect(graphLookupNotice(null)?.label).toBe("그래프 근거 미확인");
    expect(graphLookupNotice(undefined)?.label).toBe("그래프 근거 미확인");
  });
});

// 설계 §3.2: 추천이 0건일 때 "조회했고 없었다" 와 "확인 못 함" 을 화면이
// 구분해야 한다. 두 경우 모두 목록 길이는 0 이므로 길이만으로는 구분되지
// 않는다 — 구분을 지고 있는 것은 graphLookup 이다.
describe("graphLookupFoundNothing", () => {
  it("조회했고 0건이면 true", () => {
    expect(
      graphLookupFoundNothing({ status: "LOADED", foundNothing: true })
    ).toBe(true);
  });

  it("조회 실패는 0건이 아니다", () => {
    expect(
      graphLookupFoundNothing({ status: "FAILED", foundNothing: false })
    ).toBe(false);
  });

  // fail-closed: status 가 FAILED 인데 foundNothing 이 true 로 실려 와도
  // "확인했고 없었다" 로 읽지 않는다.
  it("실패 상태에서는 foundNothing 이 실려 있어도 0건이라고 하지 않는다", () => {
    expect(
      graphLookupFoundNothing({ status: "FAILED", foundNothing: true })
    ).toBe(false);
  });

  it("조회 단계를 돌지 않았으면 0건이 아니다", () => {
    expect(graphLookupFoundNothing(undefined)).toBe(false);
    expect(graphLookupFoundNothing(null)).toBe(false);
  });

  it("근거가 있으면 0건이 아니다", () => {
    expect(
      graphLookupFoundNothing({
        status: "LOADED",
        arangoTopRxCount: 7,
        foundNothing: false,
      })
    ).toBe(false);
  });
});
