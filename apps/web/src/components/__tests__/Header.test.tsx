import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/services/auth", () => ({
  getMe: vi.fn(),
}));

import { getMe } from "@/services/auth";
import ThemeProvider from "@/components/theme/ThemeProvider";
import Header from "../Header";

function renderHeader() {
  return render(
    <ThemeProvider>
      <Header />
    </ThemeProvider>
  );
}

describe("Header", () => {
  beforeEach(() => {
    vi.mocked(getMe).mockReset();
  });

  it("서비스명을 Global EMR 로 표시한다", () => {
    vi.mocked(getMe).mockResolvedValue({ id: 1, name: "김의사" } as never);
    renderHeader();
    expect(screen.getByRole("heading", { name: "Global EMR" })).toBeInTheDocument();
  });

  it("로그인한 사용자 이름을 표시한다", async () => {
    vi.mocked(getMe).mockResolvedValue({ id: 7, name: "이간호" } as never);
    renderHeader();
    await waitFor(() => expect(screen.getByText("이간호")).toBeInTheDocument());
  });

  it("사용자 조회에 실패해도 헤더가 렌더된다", async () => {
    vi.mocked(getMe).mockRejectedValue(new Error("401"));
    renderHeader();
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "Global EMR" })).toBeInTheDocument()
    );
    expect(screen.queryByText("김동국")).toBeNull();
  });

  it("테마 토글을 포함한다", () => {
    vi.mocked(getMe).mockResolvedValue({ id: 1, name: "김의사" } as never);
    renderHeader();
    expect(screen.getByRole("button", { name: /테마/ })).toBeInTheDocument();
  });
});
