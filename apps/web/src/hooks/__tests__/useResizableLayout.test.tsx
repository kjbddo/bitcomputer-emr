import { StrictMode } from "react";
import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DEFAULT_LAYOUTS, loadLayout, saveLayout, storageKey } from "../../utils/layoutStorage";
import { useResizableLayout } from "../useResizableLayout";

function setViewport(width: number) {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: width >= 1025,
    media: query,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    onchange: null,
    dispatchEvent: vi.fn(),
  }));
}

beforeEach(() => {
  window.localStorage.clear();
  vi.unstubAllGlobals();
  setViewport(1400);
});

describe("복원", () => {
  it("저장값이 있으면 그 값으로 트랙을 만든다", () => {
    saveLayout("진료실", { ...DEFAULT_LAYOUTS["진료실"], columns: [420, null, 350] });
    const { result } = renderHook(() => useResizableLayout("진료실"));
    expect(result.current.columnStyle["--col-tracks" as never]).toContain("420px");
  });

  it("저장값이 없으면 기본 배치를 쓴다", () => {
    const { result } = renderHook(() => useResizableLayout("진료실"));
    expect(result.current.columnStyle["--col-tracks" as never]).toContain("300px");
  });
});

describe("뷰포트 가드", () => {
  it("1024px 이하에서는 변수를 붙이지 않는다 — 미디어쿼리가 살아나야 한다", () => {
    saveLayout("진료실", { ...DEFAULT_LAYOUTS["진료실"], columns: [420, null, 350] });
    setViewport(900);
    const { result } = renderHook(() => useResizableLayout("진료실"));
    expect(result.current.enabled).toBe(false);
    expect(result.current.columnStyle).toEqual({});
  });

  it("좁은 화면에서도 저장값을 지우지 않는다", () => {
    saveLayout("진료실", { ...DEFAULT_LAYOUTS["진료실"], columns: [420, null, 350] });
    setViewport(900);
    renderHook(() => useResizableLayout("진료실"));
    expect(loadLayout("진료실").columns).toEqual([420, null, 350]);
  });
});

describe("조절", () => {
  it("열 델타가 반영되고 저장된다", () => {
    const { result } = renderHook(() => useResizableLayout("진료실"));
    act(() => result.current.resizeColumn(0, 60, 1400));
    expect(result.current.columnStyle["--col-tracks" as never]).toContain("360px");
    expect(loadLayout("진료실").columns[0]).toBe(360);
  });

  // 브리프 원본은 시드 없이 기본값(rows.middle = [null, null, null], 즉 세
  // 트랙 전부 1fr)에 바로 드래그를 걸었다. applyDelta 는 "양쪽이 다 1fr 이면
  // 경계가 무의미하다"며 그대로 no-op 한다(layoutStorage.ts 주석, Task 1
  // 결정 사항) — 그리고 모든 탭의 모든 rows 기본값이 이 형태라 시드 없이는
  // 어떤 행 경계도 절대 움직이지 않는다. 컬럼 테스트들처럼 한쪽에 구체값을
  // 미리 심어야 실제로 값이 바뀌는 경로(이웃이 1fr)를 검증할 수 있다.
  it("행 델타가 그 열에만 반영된다", () => {
    saveLayout("진료실", {
      ...DEFAULT_LAYOUTS["진료실"],
      rows: { ...DEFAULT_LAYOUTS["진료실"].rows, middle: [200, null, null] },
    });
    const { result } = renderHook(() => useResizableLayout("진료실"));
    act(() => result.current.resizeRow("middle", 0, 40, 900));
    expect(loadLayout("진료실").rows.middle[0]).toBe(240);
    expect(loadLayout("진료실").rows.left).toEqual(DEFAULT_LAYOUTS["진료실"].rows.left);
  });

  it("reset 은 그 탭 키만 지운다", () => {
    saveLayout("진단서", { ...DEFAULT_LAYOUTS["진단서"], columns: [400, null, null] });
    const { result } = renderHook(() => useResizableLayout("진료실"));
    act(() => result.current.resizeColumn(0, 60, 1400));
    act(() => result.current.reset());
    expect(window.localStorage.getItem(storageKey("진료실"))).toBeNull();
    expect(loadLayout("진단서").columns).toEqual([400, null, null]);
  });

  // Task 1 리뷰에서 넘어온 결함: applyDelta 의 상한이 핸들 트랙이 먹는
  // 픽셀을 빼지 않는다. 진료실 columns = [300, null(middle), 350(right)] 는
  // 핸들이 2개(HANDLE_TRACK_PX=6 씩, 총 12px)고, 그리드 항목 5개 사이에
  // gap(16px)이 4개(64px) 낀다(C3 리뷰). index=1 경계를 오른쪽 끝까지
  // 밀면(delta 를 아주 크게 음수로 주면) right 트랙이 핸들·gap 몫을 빼지
  // 않은 상한까지 자라 버려 middle(1fr) 의 실제 남는 폭이 MIN_COLUMN_PX(200)
  // 아래로 내려간다. 훅이 containerPx 에서 핸들 몫(12px)과 gap 몫(64px)을
  // 미리 빼고 넘겨야 right 트랙 상한이 224px 로 줄어, middle 이 정확히
  // 200px(그 이상은 못 내려감)로 클램프된다.
  it("컨테이너 폭에서 핸들·gap 트랙 몫을 미리 빼 1fr 열이 최소폭 밑으로 내려가지 않는다", () => {
    const { result } = renderHook(() => useResizableLayout("진료실"));
    act(() => result.current.resizeColumn(1, -1000, 800));
    const columns = loadLayout("진료실").columns;
    const right = columns[2];
    expect(right).toBe(224);
    const left = columns[0] as number;
    const remainingForOneFr = 800 - left - (right as number) - 2 * 6 - 4 * 16; // 핸들 2개 + gap 4개
    expect(remainingForOneFr).toBe(200);
  });
});

describe("패널 조절", () => {
  it("panelStyle 은 기본(null) 상태에서 빈 객체다 — 폴백 1fr 이 산다", () => {
    const { result } = renderHook(() => useResizableLayout("환자접수"));
    expect(result.current.panelStyle("middle")).toEqual({});
  });

  it("resizePanel 이 null 을 containerPx 로 물질화한 뒤 델타를 반영하고 저장한다", () => {
    const { result } = renderHook(() => useResizableLayout("환자접수"));
    // containerPx=722 는 열 전체 높이(핸들 6px + gap 16px 포함) — panelUsablePx
    // 가 그 몫을 빼면 700 이 물질화 시작점이 된다.
    act(() => result.current.resizePanel("middle", -200, 722));

    expect(loadLayout("환자접수").panels.middle).toBe(500);
    expect(result.current.panelStyle("middle")["--panel-track" as never]).toBe("500px");
  });

  it("reset 은 panels 도 기본값(null)으로 되돌린다", () => {
    const { result } = renderHook(() => useResizableLayout("환자접수"));
    act(() => result.current.resizePanel("middle", -200, 722));
    act(() => result.current.reset());

    expect(loadLayout("환자접수")).toEqual(DEFAULT_LAYOUTS["환자접수"]);
    expect(result.current.panelStyle("middle")).toEqual({});
  });

  it("panels 에 없는 열 키를 주면 아무 것도 바꾸지 않는다", () => {
    // 진료실은 단일 패널 열이 없어 panels 가 {} 다.
    const setItemSpy = vi.spyOn(Storage.prototype, "setItem");
    const { result } = renderHook(() => useResizableLayout("진료실"));
    setItemSpy.mockClear();

    act(() => result.current.resizePanel("middle", -200, 722));

    expect(loadLayout("진료실")).toEqual(DEFAULT_LAYOUTS["진료실"]);
    expect(setItemSpy).not.toHaveBeenCalled();

    setItemSpy.mockRestore();
  });
});

describe("matchMedia 부재", () => {
  // 리뷰 지적: window.matchMedia 가 없으면(구형 브라우저, 테스트 환경,
  // 임베디드 웹뷰 등) 훅이 TypeError 를 던지며 죽는다. layoutStorage.ts 의
  // 원칙(주석 3~7행) — "손상된 값으로 화면을 깨뜨리는 것보다 기본 배치로
  // 되돌리는 편이 낫다" — 을 이 훅도 따라야 한다.
  //
  // 뷰포트를 판정할 수 없을 때 저장값을 붙이는 것과 붙이지 않는 것은
  // 비대칭이다: 잘못 붙이면 좁은 화면을 깨뜨릴 수 있지만(§5.2), 안 붙이면
  // 저장값이 이번 렌더에 적용되지 않는 것뿐이다 — 다음에 matchMedia 가 있는
  // 환경에서 다시 열면 그대로 복원된다. 그래서 판정 불가 = 좁은 화면과 같은
  // 편(enabled=false)으로 떨어뜨린다.
  it("matchMedia 가 없어도 던지지 않고 좁은 화면과 같은 기본 상태로 떨어진다", () => {
    const original = window.matchMedia;
    // @ts-expect-error -- 존재 자체를 지워서 부재를 재현한다.
    delete window.matchMedia;

    try {
      expect(() => {
        const { result } = renderHook(() => useResizableLayout("진료실"));
        expect(result.current.enabled).toBe(false);
        expect(result.current.columnStyle).toEqual({});
      }).not.toThrow();
    } finally {
      window.matchMedia = original;
    }
  });
});

describe("영속화 시점", () => {
  // 리뷰 지적(Minor): saveLayout 이 setState 의 함수형 업데이터 안에서
  // 불린다. React 는 StrictMode(개발 모드) 에서 업데이터 함수를 실전 커밋과
  // 무관하게 두 번 호출해 순수성을 검증한다 — 업데이터 안에 부수효과가 있으면
  // 그 부수효과(localStorage 쓰기)도 두 번 일어난다. next.config.ts 는 지금
  // reactStrictMode 를 켜지 않아 앱에서는 안 나타나지만, 테스트에서
  // <StrictMode> 로 직접 감싸면 재현된다 — 언젠가 그 설정이 켜지는 날 조용히
  // 터질 문제를 지금 막아 둔다.
  it("StrictMode 아래에서도 열 조절 한 번에 저장은 정확히 한 번만 된다", () => {
    const setItemSpy = vi.spyOn(Storage.prototype, "setItem");
    const { result } = renderHook(() => useResizableLayout("진료실"), {
      wrapper: StrictMode,
    });
    setItemSpy.mockClear();

    act(() => result.current.resizeColumn(0, 60, 1400));

    const key = storageKey("진료실");
    const writesForKey = setItemSpy.mock.calls.filter(([k]) => k === key);
    expect(writesForKey).toHaveLength(1);
    expect(loadLayout("진료실").columns[0]).toBe(360);

    setItemSpy.mockRestore();
  });

  it("StrictMode 아래에서도 행 조절 한 번에 저장은 정확히 한 번만 된다", () => {
    saveLayout("진료실", {
      ...DEFAULT_LAYOUTS["진료실"],
      rows: { ...DEFAULT_LAYOUTS["진료실"].rows, middle: [200, null, null] },
    });
    const setItemSpy = vi.spyOn(Storage.prototype, "setItem");
    const { result } = renderHook(() => useResizableLayout("진료실"), {
      wrapper: StrictMode,
    });
    setItemSpy.mockClear();

    act(() => result.current.resizeRow("middle", 0, 40, 900));

    const key = storageKey("진료실");
    const writesForKey = setItemSpy.mock.calls.filter(([k]) => k === key);
    expect(writesForKey).toHaveLength(1);
    expect(loadLayout("진료실").rows.middle[0]).toBe(240);

    setItemSpy.mockRestore();
  });
});
