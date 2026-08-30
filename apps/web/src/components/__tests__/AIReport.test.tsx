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

function makeResponse(
  engineStatus?: string,
  uncertainty?: RadiologyReportResponse["uncertainty"]
): RadiologyReportResponse {
  return {
    heatmapUrl: null,
    predictedDiseases: [],
    // predictedDiseases 가 비어 있어도 warning 이 있으면 결과 영역이 렌더된다.
    warning: "테스트 경고",
    engineStatus,
    uncertainty,
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

// F-H4: xray-rag 는 노이즈 이미지에 대해 uncertainty="high" 와 구체적인 사유를
// 정확히 계산한다. 그 값이 Spring 경계에서 버려지는 동안 의사가 보는 것은
// 병명과 점수뿐이었다. 값이 화면까지 왔을 때 실제로 보이는지 확인한다.
describe("AIReport uncertainty 경고", () => {
  beforeEach(() => {
    mockedUpload.mockReset();
  });

  it("uncertainty.level 이 high 면 사유와 함께 경고를 표시한다", async () => {
    mockedUpload.mockResolvedValue(
      makeResponse("real", {
        level: "high",
        reasons: [
          "Top-1 similarity(0.63) is below threshold(0.65)",
          "Only 5 similar cases found",
        ],
      })
    );
    render(<AIReport {...baseProps} />);

    await uploadAndClickAnalyze();

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Only 5 similar cases found");
    // level 만 렌더하고 사유를 버리면 "확신 없음"의 근거가 화면에서 사라진다.
    expect(alert).toHaveTextContent("Top-1 similarity(0.63) is below threshold(0.65)");
  });

  it("uncertainty.level 이 low 면 경고를 표시하지 않는다", async () => {
    mockedUpload.mockResolvedValue(
      makeResponse("real", { level: "low", reasons: [] })
    );
    render(<AIReport {...baseProps} />);

    await uploadAndClickAnalyze();

    await waitFor(() => expect(screen.getByText("테스트 경고")).toBeInTheDocument());
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("uncertainty 자체가 없으면 경고를 표시하지 않는다", async () => {
    // 상류가 이 축을 안 보낸 것은 "확신 없음"의 근거가 아니다. 여기서 경고를
    // 띄우면 하지 않은 주장을 하는 셈이다(GC-2) — 대신 엔진 출처 축이
    // fail-closed 로 미확인을 알린다(아래 테스트).
    mockedUpload.mockResolvedValue(makeResponse("real", undefined));
    render(<AIReport {...baseProps} />);

    await uploadAndClickAnalyze();

    await waitFor(() => expect(screen.getByText("테스트 경고")).toBeInTheDocument());
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("AIReport engineStatus fail-closed", () => {
  beforeEach(() => {
    mockedUpload.mockReset();
  });

  // GC-3: 값이 없으면 "괜찮다"가 아니라 "모른다"다. 이전에는 engineStatus 가
  // 없을 때 경고 자체가 렌더되지 않아, 필드를 떨어뜨리는 경계 결함이 화면에서
  // 정상 상태와 구별되지 않았다 — 그것이 F-H4 가 눈에 띄지 않은 이유다.
  it("engineStatus 가 없으면 미확인 경고를 표시한다", async () => {
    mockedUpload.mockResolvedValue(makeResponse(undefined));
    render(<AIReport {...baseProps} />);

    await uploadAndClickAnalyze();

    const status = await screen.findByRole("status");
    expect(status).toHaveTextContent("미확인");
  });
});
