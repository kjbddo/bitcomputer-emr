import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  DEFAULT_LAYOUTS,
  MIN_COLUMN_PX,
  MIN_ROW_PX,
  applyDelta,
  clearLayout,
  loadLayout,
  saveLayout,
  storageKey,
  toTrackList,
} from "../layoutStorage";

beforeEach(() => {
  window.localStorage.clear();
  vi.restoreAllMocks();
});

describe("저장 키", () => {
  it("탭마다 다른 키를 쓴다", () => {
    expect(storageKey("환자접수")).not.toBe(storageKey("진료실"));
    expect(storageKey("환자접수")).toContain("v1");
  });
});

describe("왕복", () => {
  it("저장한 값을 그대로 돌려준다", () => {
    const state = { columns: [320, null, 400], rows: { left: [200, null] } };
    saveLayout("진료실", state);
    expect(loadLayout("진료실")).toEqual(state);
  });

  it("clearLayout 은 그 탭만 지운다", () => {
    saveLayout("진료실", { columns: [320, null, 400], rows: {} });
    saveLayout("진단서", { columns: [300, null, null], rows: {} });
    clearLayout("진료실");
    expect(loadLayout("진료실")).toEqual(DEFAULT_LAYOUTS["진료실"]);
    expect(loadLayout("진단서").columns).toEqual([300, null, null]);
  });
});

describe("손상값은 기본값으로 떨어진다", () => {
  it("JSON 이 아니면", () => {
    window.localStorage.setItem(storageKey("진료실"), "{{{");
    expect(loadLayout("진료실")).toEqual(DEFAULT_LAYOUTS["진료실"]);
  });

  it("열 개수가 안 맞으면", () => {
    window.localStorage.setItem(
      storageKey("진료실"),
      JSON.stringify({ columns: [300, null], rows: {} })
    );
    expect(loadLayout("진료실")).toEqual(DEFAULT_LAYOUTS["진료실"]);
  });

  it("숫자도 null 도 아닌 값이 섞이면", () => {
    window.localStorage.setItem(
      storageKey("진료실"),
      JSON.stringify({ columns: [300, "wide", 400], rows: {} })
    );
    expect(loadLayout("진료실")).toEqual(DEFAULT_LAYOUTS["진료실"]);
  });

  it("최소값보다 작은 값이 있으면", () => {
    window.localStorage.setItem(
      storageKey("진료실"),
      JSON.stringify({ columns: [10, null, 400], rows: {} })
    );
    expect(loadLayout("진료실")).toEqual(DEFAULT_LAYOUTS["진료실"]);
  });

  it("1fr 트랙이 하나도 없으면 — 창 크기 변경 시 레이아웃이 무너진다", () => {
    window.localStorage.setItem(
      storageKey("진료실"),
      JSON.stringify({ columns: [300, 400, 500], rows: {} })
    );
    expect(loadLayout("진료실")).toEqual(DEFAULT_LAYOUTS["진료실"]);
  });

  it("localStorage 가 예외를 던져도 기본값을 돌려준다", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(loadLayout("진료실")).toEqual(DEFAULT_LAYOUTS["진료실"]);
  });

  it("saveLayout 이 예외를 던져도 호출자가 죽지 않는다", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("quota");
    });
    expect(() => saveLayout("진료실", DEFAULT_LAYOUTS["진료실"])).not.toThrow();
  });
});

describe("toTrackList", () => {
  it("null 은 1fr 로, 숫자는 px 로 바꾸고 사이에 핸들 자리를 넣는다", () => {
    expect(toTrackList([300, null, 350], MIN_COLUMN_PX)).toBe(
      "minmax(200px, 300px) 6px minmax(200px, 1fr) 6px minmax(200px, 350px)"
    );
  });

  it("트랙이 하나면 핸들 자리가 없다", () => {
    expect(toTrackList([null], MIN_ROW_PX)).toBe("minmax(120px, 1fr)");
  });
});

describe("applyDelta", () => {
  it("인접한 두 트랙이 크기를 주고받는다", () => {
    expect(applyDelta([300, 400, null], 0, 50, MIN_COLUMN_PX, 1400)).toEqual([
      350, 350, null,
    ]);
  });

  it("최소값 아래로는 내려가지 않는다", () => {
    expect(applyDelta([300, 400, null], 0, -500, MIN_COLUMN_PX, 1400)).toEqual([
      200, 500, null,
    ]);
  });

  it("이웃이 1fr 이면 그 트랙만 바뀐다 — 1fr 이 나머지를 흡수한다", () => {
    expect(applyDelta([300, null, 350], 0, 40, MIN_COLUMN_PX, 1400)).toEqual([
      340, null, 350,
    ]);
  });

  it("행에도 같은 규칙이 적용된다", () => {
    expect(applyDelta([200, null], 0, -100, MIN_ROW_PX, 800)).toEqual([
      120, null,
    ]);
  });
});
