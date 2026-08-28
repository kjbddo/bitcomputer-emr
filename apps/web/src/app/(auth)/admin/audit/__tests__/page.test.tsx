import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AuditPage from "../page";

vi.mock("@/services/admin", () => ({
  getAuditLogs: vi.fn(),
}));

import { getAuditLogs } from "@/services/admin";

const page = {
  content: [
    {
      id: 2,
      occurredAt: "2026-03-01T10:00:00",
      actorUsername: "front.park",
      actorRole: "RECEPTIONIST",
      action: "ACCESS_DENIED",
      targetPatientId: null,
      targetHistoryId: null,
      requestIp: "172.19.0.1",
      outcome: "DENIED",
      detail: "POST /api/agent/prescription/recommend",
    },
    {
      id: 1,
      occurredAt: "2026-01-01T10:00:00",
      actorUsername: "dr.kim",
      actorRole: "DOCTOR",
      action: "PATIENT_VIEW",
      targetPatientId: 1,
      targetHistoryId: null,
      requestIp: "172.19.0.1",
      outcome: "GRANTED",
      detail: "GET /api/patients/1",
    },
  ],
  totalElements: 2,
  totalPages: 1,
  number: 0,
  size: 50,
};

describe("감사 로그 화면", () => {
  beforeEach(() => {
    vi.mocked(getAuditLogs).mockResolvedValue(page);
  });

  it("로그 행을 표시한다", async () => {
    render(<AuditPage />);
    expect(await screen.findByText("dr.kim")).toBeTruthy();
    expect(await screen.findByText("front.park")).toBeTruthy();
  });

  it("초기 조회는 필터 없이 최신순 50건", async () => {
    render(<AuditPage />);
    await waitFor(() => expect(getAuditLogs).toHaveBeenCalledWith({ page: 0, size: 50 }));
  });

  it("필터를 적용하면 파라미터가 전달된다", async () => {
    const user = userEvent.setup();
    render(<AuditPage />);
    await screen.findByText("dr.kim");

    await user.type(screen.getByLabelText("행위자"), "dr.");
    await user.selectOptions(screen.getByLabelText("결과"), "DENIED");
    await user.click(screen.getByRole("button", { name: "조회" }));

    await waitFor(() =>
      expect(getAuditLogs).toHaveBeenLastCalledWith(
        expect.objectContaining({ actorUsername: "dr.", outcome: "DENIED", page: 0 })
      )
    );
  });

  it("거부된 행에 구분 클래스를 붙인다", async () => {
    render(<AuditPage />);
    const denied = await screen.findByText("DENIED");
    expect(denied.closest("tr")?.className).toContain("denied");
  });

  it("거부/허용 결과를 Badge 텍스트로도 전달한다", async () => {
    render(<AuditPage />);
    expect(await screen.findByText("DENIED")).toBeTruthy();
    expect(await screen.findByText("GRANTED")).toBeTruthy();
  });

  it("환자 ID 를 비워두면 targetPatientId 파라미터를 보내지 않는다", async () => {
    const user = userEvent.setup();
    render(<AuditPage />);
    await screen.findByText("dr.kim");

    // 다른 필터만 채우고 환자 ID 는 그대로 비워둔 채 조회한다.
    await user.type(screen.getByLabelText("행위"), "PATIENT_VIEW");
    await user.click(screen.getByRole("button", { name: "조회" }));

    await waitFor(() => {
      const lastCall = vi.mocked(getAuditLogs).mock.calls.at(-1)?.[0];
      expect(lastCall).not.toHaveProperty("targetPatientId");
      expect(lastCall).toMatchObject({ action: "PATIENT_VIEW", page: 0 });
    });
  });

  it("환자 ID 에 0 을 입력하면 그대로 전달한다", async () => {
    const user = userEvent.setup();
    render(<AuditPage />);
    await screen.findByText("dr.kim");

    await user.type(screen.getByLabelText("환자 ID"), "0");
    await user.click(screen.getByRole("button", { name: "조회" }));

    await waitFor(() =>
      expect(getAuditLogs).toHaveBeenLastCalledWith(
        expect.objectContaining({ targetPatientId: 0, page: 0 })
      )
    );
  });

  it("총 페이지가 1개면 이전/다음 버튼을 비활성화하지만 감추지는 않는다", async () => {
    render(<AuditPage />);
    await screen.findByText("dr.kim");

    expect(screen.getByRole("button", { name: "이전" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "다음" })).toBeDisabled();
  });

  it("다음 페이지가 있으면 다음 버튼을 눌러 다음 페이지를 조회한다", async () => {
    vi.mocked(getAuditLogs).mockResolvedValue({ ...page, totalPages: 2, number: 0 });
    const user = userEvent.setup();
    render(<AuditPage />);
    await screen.findByText("dr.kim");

    const nextButton = screen.getByRole("button", { name: "다음" });
    expect(nextButton).not.toBeDisabled();
    expect(screen.getByRole("button", { name: "이전" })).toBeDisabled();

    vi.mocked(getAuditLogs).mockResolvedValue({ ...page, totalPages: 2, number: 1 });
    await user.click(nextButton);

    await waitFor(() =>
      expect(getAuditLogs).toHaveBeenLastCalledWith(expect.objectContaining({ page: 1 }))
    );
  });

  it("현재 페이지 위치를 상태 영역으로 안내한다", async () => {
    render(<AuditPage />);
    await screen.findByText("dr.kim");
    expect(screen.getByRole("status")).toHaveTextContent("1 / 1 페이지 (총 2건)");
  });

  it("조회 결과가 없으면 안내 문구를 보여준다", async () => {
    vi.mocked(getAuditLogs).mockResolvedValue({
      content: [],
      totalElements: 0,
      totalPages: 0,
      number: 0,
      size: 50,
    });
    render(<AuditPage />);
    expect(await screen.findByText("조건에 맞는 기록이 없습니다")).toBeTruthy();
  });

  it("조회에 실패하면 에러 문구와 다시 시도 버튼을 보여준다", async () => {
    vi.mocked(getAuditLogs).mockRejectedValue(new Error("네트워크 오류"));
    render(<AuditPage />);
    expect(await screen.findByText("네트워크 오류")).toBeTruthy();
    expect(screen.getByRole("button", { name: "다시 시도" })).toBeTruthy();
  });
});
