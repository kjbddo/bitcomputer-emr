import { describe, expect, it, vi, beforeAll, beforeEach } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";

// jsdom 은 <dialog> 의 모달 동작을 구현하지 않는다. open 속성만 흉내 낸다.
// (apps/web/src/components/__tests__/Diagnosis.test.tsx 와 동일한 폴리필)
beforeAll(() => {
  HTMLDialogElement.prototype.showModal = function showModal(this: HTMLDialogElement) {
    this.open = true;
  };
  HTMLDialogElement.prototype.close = function close(this: HTMLDialogElement) {
    this.open = false;
    this.dispatchEvent(new Event("close"));
  };
});

vi.mock("@/services", async () => {
  const actual = await vi.importActual<typeof import("@/services")>("@/services");
  return {
    ...actual,
    generateDocumentCertificateByHistory: vi.fn(),
  };
});

import MedicalCertificate from "../MedicalCertificate";
import { generateDocumentCertificateByHistory } from "@/services";
import type { CertificateItem } from "../CertificateList";

const SELECTED_CERTIFICATE: CertificateItem = {
  id: 1,
  type: "general",
  label: "일반 진단서",
  pdfPath: "",
  patientNumber: "1",
  patientName: "홍길동",
  age: 30,
  department: "내과",
  doctor: "김의사",
  issueDate: "2026-08-28",
};

function renderWithAppliedDiagnosis() {
  return render(
    <MedicalCertificate
      selected={SELECTED_CERTIFICATE}
      patientInfo={null}
      employeeId={1}
      diagnosisApply={{
        key: 1,
        diseaseCode: "J00",
        primaryDiseaseName: "감기",
        additionalDiseaseNames: "",
        historyId: 10,
      }}
    />
  );
}

describe("진단서 AI 미리보기의 llmStatus 배선", () => {
  // M8: 기본값이 fallback 이면 "필드 없음" 과 "fallback" 두 테스트가 같은
  // mock 을 공유해 구분이 안 된다. 배지가 없는 real 을 기본값으로 두어
  // 각 테스트가 자기 설정에만 의존하게 한다.
  beforeEach(() => {
    vi.mocked(generateDocumentCertificateByHistory).mockResolvedValue({
      grantType: "Bearer",
      accessToken: "a",
      refreshToken: "r",
      medicalCertificate: "환자는 통원 치료가 필요합니다.",
      llmStatus: "real",
    });
  });

  it("llmStatus 가 fallback 이면 미리보기에 모델 미사용 배지가 뜬다", async () => {
    vi.mocked(generateDocumentCertificateByHistory).mockResolvedValue({
      grantType: "Bearer",
      accessToken: "a",
      refreshToken: "r",
      medicalCertificate: "환자는 통원 치료가 필요합니다.",
      llmStatus: "fallback",
    });
    renderWithAppliedDiagnosis();

    fireEvent.click(screen.getByRole("button", { name: /AI/ }));

    const dialog = await screen.findByRole("dialog");
    const badge = await within(dialog).findByText("규칙 기반 결과 — 모델 미사용");
    expect(badge).toHaveAttribute("data-tone", "warning");
  });

  // M11: 프로젝트에 Bedrock 키가 없는 지금, 실제로 가장 자주 나오는 값은
  // "stub" 인데도 이 컴포넌트에는 그 경로를 확인하는 테스트가 없었다.
  it("llmStatus 가 stub 이면 미리보기에 스텁 배지가 뜬다", async () => {
    vi.mocked(generateDocumentCertificateByHistory).mockResolvedValue({
      grantType: "Bearer",
      accessToken: "a",
      refreshToken: "r",
      medicalCertificate: "환자는 통원 치료가 필요합니다.",
      llmStatus: "stub",
    });
    renderWithAppliedDiagnosis();

    fireEvent.click(screen.getByRole("button", { name: /AI/ }));

    const dialog = await screen.findByRole("dialog");
    const badge = await within(dialog).findByText("스텁 응답 (모델 미사용)");
    expect(badge).toHaveAttribute("data-tone", "neutral");
  });

  it("llmStatus 가 real 이면 배지가 없다", async () => {
    vi.mocked(generateDocumentCertificateByHistory).mockResolvedValue({
      grantType: "Bearer",
      accessToken: "a",
      refreshToken: "r",
      medicalCertificate: "환자는 통원 치료가 필요합니다.",
      llmStatus: "real",
    });
    renderWithAppliedDiagnosis();

    fireEvent.click(screen.getByRole("button", { name: /AI/ }));

    const dialog = await screen.findByRole("dialog");
    await within(dialog).findByLabelText("AI 생성 소견 미리보기");
    expect(within(dialog).queryByText(/모델 미사용/)).toBeNull();
  });

  // 필드가 없는 응답을 "모델이 돌았다"로 읽으면 이 표시가 존재할 이유가 사라진다.
  it("llmStatus 가 없으면 모델이 돌았다고 가정하지 않는다", async () => {
    vi.mocked(generateDocumentCertificateByHistory).mockResolvedValue({
      grantType: "Bearer",
      accessToken: "a",
      refreshToken: "r",
      medicalCertificate: "환자는 통원 치료가 필요합니다.",
    });
    renderWithAppliedDiagnosis();

    fireEvent.click(screen.getByRole("button", { name: /AI/ }));

    const dialog = await screen.findByRole("dialog");
    await within(dialog).findByText(/모델 미사용/);
  });
});
