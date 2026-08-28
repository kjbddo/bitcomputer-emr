import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AdminUsersPage from "../page";
import { Role } from "@/types/user";

vi.mock("@/services/admin", () => ({
  getAllUsers: vi.fn(),
  getDepts: vi.fn(),
  createUser: vi.fn(),
  setRole: vi.fn(),
}));

import { getAllUsers, getDepts } from "@/services/admin";

const depts = [
  { id: 1, dept: "UNASSIGNED", employeeCount: 1 },
  { id: 2, dept: "내과", employeeCount: 2 },
];

const users = [
  { id: 10, name: "김의사", username: "dr.kim", role: Role.DOCTOR, deptId: 2 },
  { id: 11, name: "미배정자", username: "no.dept", role: Role.NURSE, deptId: undefined },
];

describe("관리자 유저 화면", () => {
  beforeEach(() => {
    vi.mocked(getDepts).mockResolvedValue(depts);
    vi.mocked(getAllUsers).mockResolvedValue(users);
  });

  // M14: 부서 ID 숫자 대신 이름을 보여준다. "직원 추가" 폼의 부서 select 에도
  // 같은 이름의 option 이 있으므로, 유저 목록 표(role="table") 안에서만 찾는다.
  it("부서 ID 대신 부서명을 표시한다", async () => {
    render(<AdminUsersPage />);
    await screen.findByText("김의사");
    const table = screen.getByRole("table");
    expect(await within(table).findByText("내과")).toBeTruthy();
    expect(within(table).queryByText("2")).toBeFalsy();
  });

  it("일치하는 부서가 없으면 ID 로 폴백한다", async () => {
    vi.mocked(getAllUsers).mockResolvedValue([
      { id: 12, name: "미상", username: "unknown.dept", role: Role.NURSE, deptId: 999 },
    ]);
    render(<AdminUsersPage />);
    expect(await screen.findByText("999")).toBeTruthy();
  });

  it("부서가 없는 유저는 대시(-)로 표시한다", async () => {
    render(<AdminUsersPage />);
    await screen.findByText("김의사");
    expect(await screen.findByText("-")).toBeTruthy();
  });

  // M4: 목록 로딩 실패는 "등록된 유저가 없습니다"(빈 목록)와 구분되는
  // 에러+재시도 상태를 보여줘야 한다.
  it("목록 로딩에 실패하면 에러 문구와 다시 시도 버튼을 보여준다", async () => {
    vi.mocked(getAllUsers).mockRejectedValue(new Error("네트워크 오류"));
    render(<AdminUsersPage />);

    expect(await screen.findByText("유저 목록을 불러오지 못했습니다")).toBeTruthy();
    expect(await screen.findByText("네트워크 오류")).toBeTruthy();
    expect(screen.getByRole("button", { name: "다시 시도" })).toBeTruthy();
    // 빈 목록 문구와는 다른 상태여야 한다.
    expect(screen.queryByText("등록된 유저가 없습니다")).toBeFalsy();
  });

  it("다시 시도 버튼을 누르면 목록을 다시 불러온다", async () => {
    vi.mocked(getAllUsers).mockRejectedValueOnce(new Error("네트워크 오류"));
    const user = userEvent.setup();
    render(<AdminUsersPage />);
    await screen.findByText("유저 목록을 불러오지 못했습니다");

    vi.mocked(getAllUsers).mockResolvedValue(users);
    await user.click(screen.getByRole("button", { name: "다시 시도" }));

    await waitFor(() => expect(getAllUsers).toHaveBeenCalledTimes(2));
    expect(await screen.findByText("김의사")).toBeTruthy();
  });

  it("실제로 유저 목록이 비어 있으면 빈 목록 문구를 보여준다", async () => {
    vi.mocked(getAllUsers).mockResolvedValue([]);
    render(<AdminUsersPage />);
    expect(await screen.findByText("등록된 유저가 없습니다")).toBeTruthy();
  });
});
