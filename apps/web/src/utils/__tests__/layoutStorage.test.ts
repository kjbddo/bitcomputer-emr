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
    const state = {
      columns: [320, null, 400],
      rows: { left: [200, null], middle: [null, null, null], right: [null, null] },
    };
    saveLayout("진료실", state);
    expect(loadLayout("진료실")).toEqual(state);
  });

  it("clearLayout 은 그 탭만 지운다", () => {
    saveLayout("진료실", {
      columns: [320, null, 400],
      rows: { left: [null, null], middle: [null, null, null], right: [null, null] },
    });
    saveLayout("진단서", {
      columns: [300, null, null],
      rows: { middle: [null, null] },
    });
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

  it("rows 에 열 키가 하나라도 빠지면 — 그 열은 저장된 값 없이 렌더링돼 패널이 깨진다", () => {
    window.localStorage.setItem(
      storageKey("진료실"),
      JSON.stringify({
        columns: [320, null, 400],
        // "middle" 이 빠졌다 — 진료실은 left/middle/right 세 열이 모두 있어야 한다.
        rows: { left: [200, null], right: [null, null] },
      })
    );
    expect(loadLayout("진료실")).toEqual(DEFAULT_LAYOUTS["진료실"]);
  });

  it("rows 행 배열 길이가 현재 패널 수와 다르면 — 패널이 추가/삭제된 뒤 남은 옛 트랙 수가 새 패널 수와 안 맞아 넘치거나 찌그러진다", () => {
    window.localStorage.setItem(
      storageKey("진료실"),
      JSON.stringify({
        columns: [320, null, 400],
        // 진료실의 middle 열은 패널 3개(트랙 3개)인데 2개만 저장돼 있다.
        rows: { left: [null, null], middle: [null, null], right: [null, null] },
      })
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

  describe("둘 다 1fr 인 경계 — 물질화", () => {
    it("2트랙 축은 a 만 물질화하고 b 는 1fr 로 남긴다", () => {
      const result = applyDelta([null, null], 0, 100, MIN_COLUMN_PX, 800);
      expect(result).toEqual([500, null]);
      expect(result.some((t) => t === null)).toBe(true);
    });

    it("3트랙 축은 a·b 를 물질화하고 나머지 null 은 그대로 둔다", () => {
      const result = applyDelta([null, null, null], 0, 60, MIN_COLUMN_PX, 900);
      expect(result).toEqual([360, 240, null]);
      expect(result[2]).toBeNull();
    });

    it("물질화 후에도 min 클램핑이 적용된다", () => {
      const result = applyDelta([null, null], 0, -1000, MIN_COLUMN_PX, 800);
      expect(result).toEqual([MIN_COLUMN_PX, null]);
    });
  });

  describe("null 이웃이 둘 이상이면 상한이 그만큼 낮아진다", () => {
    // 컨테이너(usable) 784, min 200. [300, null, null] 에서 index 0 을 밀면
    // 이웃(null)이 두 개(인덱스 1, 2) 이므로 상한은 784 - 0(고정 트랙 합) - 400
    // (null 이웃 2개 * min) = 384 여야 한다. 옛 코드는 이웃이 하나라고 가정하고
    // "- min" 만 빼서 584 까지 올라갔다 — 렌더된 값(384)과 저장값(최대 584)이
    // 어긋나 되돌릴 때 먹통 구간이 생겼다.
    it("이웃이 1fr 이면 그 트랙만 바뀐다 분기: 재현 사례 — 상한이 384 를 넘지 않는다", () => {
      const result = applyDelta([300, null, null], 0, 1000, MIN_COLUMN_PX, 784);
      expect(result).toEqual([384, null, null]);
    });

    it("null 이웃이 하나뿐이면 기존과 같다 — 상한 584", () => {
      const result = applyDelta([300, null], 0, 1000, MIN_COLUMN_PX, 784);
      expect(result).toEqual([584, null]);
    });

    it("null 이웃이 0개(나머지가 전부 고정)면 상한 계산에 개입할 필요가 없다 — 옆 트랙 자신의 min 클램프가 이미 막는다", () => {
      // [null, 200, 200] 에서 index 0 을 크게 밀면(양의 delta) index 1 이 자기
      // min(200) 아래로는 못 내려가므로, 그 자리에서 이미 멈춘다. 이때 null 인
      // 첫 트랙의 실제 렌더 폭은 784 - 200 - 200 = 384(= containerPx - 400) 를
      // 넘지 않는다.
      const result = applyDelta([null, 200, 200], 0, 1000, MIN_COLUMN_PX, 784);
      expect(result).toEqual([null, 200, 200]);
    });

    it("마지막 분기(a 가 1fr, b 가 고정)도 같은 상한을 쓴다", () => {
      // [null, 300, null] 에서 index 0 을 밀어 b(인덱스 1)를 키우면, 다른 null
      // 이웃(인덱스 2)도 min 을 요구하므로 상한은 784 - 0 - 400 = 384 다.
      const result = applyDelta([null, 300, null], 0, -1000, MIN_COLUMN_PX, 784);
      expect(result).toEqual([null, 384, null]);
    });
  });
});
