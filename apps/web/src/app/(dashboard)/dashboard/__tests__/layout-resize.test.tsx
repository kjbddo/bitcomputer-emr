import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import DashboardPage from "../page";
import { DEFAULT_LAYOUTS, loadLayout, saveLayout, storageKey } from "@/utils/layoutStorage";
import ThemeProvider from "@/components/theme/ThemeProvider";

vi.mock("@/services/auth", () => ({
  getRole: vi.fn().mockResolvedValue("DOCTOR"),
  getMe: vi.fn().mockResolvedValue({ id: 1, name: "테스트", deptId: 1, role: "DOCTOR", username: "tester" }),
}));

function renderDashboard() {
  return render(
    <ThemeProvider>
      <DashboardPage />
    </ThemeProvider>
  );
}

function setWideViewport() {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: true,
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
  setWideViewport();
});

describe("대시보드 레이아웃 조절", () => {
  it("열 경계 핸들이 렌더된다", async () => {
    renderDashboard();
    const handles = await screen.findAllByRole("separator");
    expect(handles.length).toBeGreaterThan(0);
  });

  it("기본 배치로 버튼이 그 탭 키만 지운다", async () => {
    saveLayout("환자접수", { ...DEFAULT_LAYOUTS["환자접수"], columns: [420, null, null] });
    saveLayout("진료실", { ...DEFAULT_LAYOUTS["진료실"], columns: [420, null, 350] });
    renderDashboard();
    fireEvent.click(await screen.findByRole("button", { name: "기본 배치로" }));
    expect(window.localStorage.getItem(storageKey("환자접수"))).toBeNull();
    expect(loadLayout("진료실").columns).toEqual([420, null, 350]);
  });

  it("저장이 실패해도 화면이 죽지 않는다", async () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("quota");
    });
    renderDashboard();
    const handle = (await screen.findAllByRole("separator"))[0];
    expect(() => fireEvent.keyDown(handle, { key: "ArrowRight" })).not.toThrow();
    expect(await screen.findByRole("button", { name: "기본 배치로" })).toBeInTheDocument();
  });
});
