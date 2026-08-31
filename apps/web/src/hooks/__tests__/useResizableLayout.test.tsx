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
  // 핸들이 2개(HANDLE_TRACK_PX=6 씩, 총 12px)다. index=1 경계를 오른쪽
  // 끝까지 밀면(delta 를 아주 크게 음수로 주면) right 트랙이 핸들 몫을
  // 빼지 않은 상한(300px)까지 자라 버려, middle(1fr) 의 실제 남는 폭이
  // 800 - 300(left) - 300(right) - 12(handle) = 188px 로 MIN_COLUMN_PX(200)
  // 아래로 내려간다. 훅이 containerPx 에서 핸들 몫을 미리 빼고 넘겨야
  // right 트랙 상한이 288px 로 줄어, middle 이 정확히 200px 로 클램프된다.
  it("컨테이너 폭에서 핸들 트랙 몫을 미리 빼 1fr 열이 최소폭 밑으로 내려가지 않는다", () => {
    const { result } = renderHook(() => useResizableLayout("진료실"));
    act(() => result.current.resizeColumn(1, -1000, 800));
    const columns = loadLayout("진료실").columns;
    const right = columns[2];
    expect(right).toBe(288);
    const left = columns[0] as number;
    const remainingForOneFr = 800 - left - (right as number) - 2 * 6; // 핸들 2개
    expect(remainingForOneFr).toBeGreaterThanOrEqual(200);
  });
});
