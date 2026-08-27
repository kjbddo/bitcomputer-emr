import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AIReport from "../AIReport";
import { uploadAndAnalyzeImage, type RadiologyReportResponse } from "@/services/radiology";

// AIReport 는 engineStatus 를 props 로 받지 않는다 - handleAnalyze() 가
// uploadAndAnalyzeImage() 응답에서 읽어 내부 state 로 들고 있다가, 분석 결과
// 영역이 렌더될 때(추론된 질병 또는 warning 이 있을 때)만 배지를 보여준다.
// 그래서 이 테스트는 실제 사용자 흐름(업로드 -> 분석 클릭)을 거쳐 배지 노출을
// 검증한다.
vi.mock("@/services/radiology", async () => {
  const actual = await vi.importActual<typeof import("@/services/radiology")>(
    "@/services/radiology"
  );
  return {
    ...actual,
    uploadAndAnalyzeImage: vi.fn(),
  };
});

const mockedUpload = vi.mocked(uploadAndAnalyzeImage);

const baseProps = {
  patientId: 1,
  employeeId: 1,
  deptId: 1,
  entryDate: "2026-01-01",
};

function makeResponse(engineStatus?: string): RadiologyReportResponse {
  return {
    heatmapUrl: null,
    predictedDiseases: [],
    // predictedDiseases 가 비어 있어도 warning 이 있으면 결과 영역이 렌더된다.
    warning: "테스트 경고",
    engineStatus,
  };
}

async function uploadAndClickAnalyze() {
  const file = new File(["fake-bytes"], "xray.png", { type: "image/png" });
  const input = document.querySelector('input[type="file"]') as HTMLInputElement;
  fireEvent.change(input, { target: { files: [file] } });

  const analyzeButton = await screen.findByRole("button", { name: "AI 분석" });
  await waitFor(() => expect(analyzeButton).not.toBeDisabled());
  fireEvent.click(analyzeButton);
}

describe("AIReport engineStatus 배지", () => {
  beforeEach(() => {
    mockedUpload.mockReset();
  });

  it("mock 엔진이면 경고를 표시한다", async () => {
    mockedUpload.mockResolvedValue(makeResponse("mock"));
    render(<AIReport {...baseProps} />);

    await uploadAndClickAnalyze();

    const status = await screen.findByRole("status");
    expect(status).toHaveTextContent("mock");
  });

  it("stub 엔진이면 경고를 표시한다", async () => {
    mockedUpload.mockResolvedValue(makeResponse("stub"));
    render(<AIReport {...baseProps} />);

    await uploadAndClickAnalyze();

    expect(await screen.findByRole("status")).toBeTruthy();
  });

  it("real 엔진이면 경고를 표시하지 않는다", async () => {
    mockedUpload.mockResolvedValue(makeResponse("real"));
    render(<AIReport {...baseProps} />);

    await uploadAndClickAnalyze();

    await waitFor(() => expect(screen.getByText("테스트 경고")).toBeInTheDocument());
    expect(screen.queryByRole("status")).toBeNull();
  });
});
