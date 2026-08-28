import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import DeptsPage from "../page";

vi.mock("@/services/admin", () => ({
  getDepts: vi.fn(),
  createDept: vi.fn(),
  renameDept: vi.fn(),
}));

import { createDept, getDepts } from "@/services/admin";

describe("부서 관리 화면", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getDepts).mockResolvedValue([
      { id: 1, dept: "UNASSIGNED", employeeCount: 16 },
      { id: 2, dept: "내과", employeeCount: 0 },
    ]);
    vi.mocked(createDept).mockResolvedValue({ id: 3, dept: "외과", employeeCount: 0 });
  });

  it("부서 목록과 소속 인원을 표시한다", async () => {
    render(<DeptsPage />);
    expect(await screen.findByText("UNASSIGNED")).toBeTruthy();
    expect(await screen.findByText("내과")).toBeTruthy();
    expect(await screen.findByText("16")).toBeTruthy();
  });

  it("부서를 추가하면 API 를 호출한다", async () => {
    const user = userEvent.setup();
    render(<DeptsPage />);
    await screen.findByText("UNASSIGNED");

    await user.type(screen.getByLabelText("새 부서명"), "외과");
    await user.click(screen.getByRole("button", { name: "추가" }));

    await waitFor(() => expect(createDept).toHaveBeenCalledWith("외과"));
  });

  it("빈 이름으로는 추가 버튼이 동작하지 않는다", async () => {
    const user = userEvent.setup();
    render(<DeptsPage />);
    await screen.findByText("UNASSIGNED");

    await user.click(screen.getByRole("button", { name: "추가" }));
    expect(createDept).not.toHaveBeenCalled();
  });
});
