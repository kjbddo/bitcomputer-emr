import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import Diagnosis, { llmStatusNotice } from "../Diagnosis";
import { MedicalSelectionProvider } from "@store/medicalSelection";
import {
  getValidationJob,
  recommendPrescriptions,
  type ValidationJobResponse,
} from "@/services/history";

// jsdom 은 <dialog> 의 모달 동작을 구현하지 않는다. open 속성만 흉내 낸다.
// (apps/web/src/components/ui/__tests__/Modal.test.tsx 와 동일한 폴리필)
beforeAll(() => {
  HTMLDialogElement.prototype.showModal = function showModal(this: HTMLDialogElement) {
    this.open = true;
  };
  HTMLDialogElement.prototype.close = function close(this: HTMLDialogElement) {
    this.open = false;
    this.dispatchEvent(new Event("close"));
  };
});

vi.mock("@/services/history", async () => {
  const actual = await vi.importActual<typeof import("@/services/history")>(
    "@/services/history"
  );
  return {
    ...actual,
    recommendPrescriptions: vi.fn(),
    getValidationJob: vi.fn(),
  };
});

const mockedRecommend = vi.mocked(recommendPrescriptions);
const mockedGetJob = vi.mocked(getValidationJob);

describe("llmStatusNotice", () => {
  it("모델이 실제로 돌았으면 아무것도 표시하지 않는다", () => {
    expect(llmStatusNotice("real")).toBeNull();
  });

  it("폴백이면 모델 미사용을 명시한다", () => {
    const notice = llmStatusNotice("fallback");
    expect(notice).not.toBeNull();
    expect(notice!.label).toContain("모델 미사용");
    expect(notice!.tone).toBe("warning");
  });

  it("스텁이면 폴백과 구분되는 문구를 쓴다", () => {
    const stub = llmStatusNotice("stub");
    const fallback = llmStatusNotice("fallback");
    expect(stub).not.toBeNull();
    expect(stub!.label).not.toBe(fallback!.label);
  });

  // 필드가 없는 응답을 "모델이 돌았다"로 해석하면 이 태스크의 목적이 무너진다.
  it("필드가 없으면 모델이 돌았다고 가정하지 않는다", () => {
    expect(llmStatusNotice(undefined)).not.toBeNull();
  });
});

// llmStatusNotice 단위 테스트만으로는 실제 모달이 validationModal.result?.llmStatus
// 를 제대로 읽어 배지에 넘기는지 확인할 수 없다 — 이 배선이 끊겨도(예: 엉뚱한 필드를
// 읽거나 하드코딩된 값을 넘겨도) 위 단위 테스트는 전부 통과한다. 그래서 실제 렌더
// 경로(AI 처방 추천 클릭 -> 작업 폴링 -> 모달 오픈)를 통해 배지 문구가 실제로
// 나타나는지 확인한다.
describe("검증 모달의 llmStatus 배선", () => {
  const clinicVisit = { patientId: 1, deptId: 1 };

  function renderDiagnosis() {
    return render(
      <MedicalSelectionProvider>
        <Diagnosis clinicVisit={clinicVisit} ensureHistory={async () => 10} employeeId={1} />
      </MedicalSelectionProvider>
    );
  }

  it("결과의 llmStatus 가 fallback 이면 모달에 모델 미사용 배지가 뜬다", async () => {
    mockedRecommend.mockResolvedValue({ jobId: "job-1", historyId: 10, status: "RUNNING" });
    mockedGetJob.mockResolvedValue({
      jobId: "job-1",
      historyId: 10,
      status: "DONE",
      result: {
        overallStatus: "PASS",
        summary: "이상 없음",
        llmStatus: "fallback",
        recommendedPrescriptions: [
          {
            id: 1,
            rank: 1,
            prescription_code: "C1",
            prescription_name: "약1",
            reason: "",
            confidence_score: 0.9,
            dose: 1,
            time: 1,
            days: 1,
          },
        ],
      },
    } as ValidationJobResponse);

    renderDiagnosis();
    fireEvent.click(screen.getByRole("button", { name: "AI 처방 추천" }));

    await waitFor(() => {
      expect(screen.getByText("규칙 기반 결과 — 모델 미사용")).toBeInTheDocument();
    });
  });

  it("결과의 llmStatus 가 real 이면 모델 미사용 배지가 뜨지 않는다", async () => {
    mockedRecommend.mockResolvedValue({ jobId: "job-2", historyId: 10, status: "RUNNING" });
    mockedGetJob.mockResolvedValue({
      jobId: "job-2",
      historyId: 10,
      status: "DONE",
      result: {
        overallStatus: "PASS",
        summary: "이상 없음",
        llmStatus: "real",
        recommendedPrescriptions: [
          {
            id: 1,
            rank: 1,
            prescription_code: "C1",
            prescription_name: "약1",
            reason: "",
            confidence_score: 0.9,
            dose: 1,
            time: 1,
            days: 1,
          },
        ],
      },
    } as ValidationJobResponse);

    renderDiagnosis();
    fireEvent.click(screen.getByRole("button", { name: "AI 처방 추천" }));

    await waitFor(() => {
      expect(screen.getByText("이상 없음")).toBeInTheDocument();
    });
    expect(screen.queryByText(/모델 미사용/)).toBeNull();
  });
});
