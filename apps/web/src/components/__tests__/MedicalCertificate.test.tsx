import { describe, expect, it, vi, beforeAll, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";

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

  // M11: 프로젝트에 LLM API 키가 없는 지금, 실제로 가장 자주 나오는 값은
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

  // 근거 배지가 추가되면서 llmStatus 배지도 나란히 설 수 있다. 접두어가 없으면
  // Diagnosis.tsx 모달과 같은 문제(라벨 없는 amber 배지 두 개)가 재현된다.
  it("모델 접두어가 배지 옆에 표시된다", async () => {
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
    expect(await within(dialog).findByText("모델")).toBeInTheDocument();
  });
});

describe("진단서 AI 미리보기의 근거 검증 표시", () => {
  it("진단서 검증이 flagged 면 미리보기에 근거 불일치가 뜬다", async () => {
    vi.mocked(generateDocumentCertificateByHistory).mockResolvedValue({
      grantType: "Bearer", accessToken: "a", refreshToken: "r",
      medicalCertificate: "소견",
      llmStatus: "real",
      verification: {
        status: "flagged",
        checks: [{ id: "cited_code_known", target: "certificate", outcome: "flagged", evidence: "K52.9" }],
      },
    });
    renderWithAppliedDiagnosis();
    fireEvent.click(screen.getByRole("button", { name: /AI/ }));

    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText("근거 불일치")).toBeInTheDocument();
  });

  it("verification 이 없으면 미검증으로 표시한다", async () => {
    vi.mocked(generateDocumentCertificateByHistory).mockResolvedValue({
      grantType: "Bearer", accessToken: "a", refreshToken: "r",
      medicalCertificate: "소견", llmStatus: "real",
    });
    renderWithAppliedDiagnosis();
    fireEvent.click(screen.getByRole("button", { name: /AI/ }));

    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText("미검증")).toBeInTheDocument();
  });

  it("passed 면 검증 표시가 없다", async () => {
    vi.mocked(generateDocumentCertificateByHistory).mockResolvedValue({
      grantType: "Bearer", accessToken: "a", refreshToken: "r",
      medicalCertificate: "소견", llmStatus: "real",
      verification: { status: "passed", checks: [] },
    });
    renderWithAppliedDiagnosis();
    fireEvent.click(screen.getByRole("button", { name: /AI/ }));

    const dialog = await screen.findByRole("dialog");
    await within(dialog).findByLabelText("AI 생성 소견 미리보기");
    expect(within(dialog).queryByText("미검증")).toBeNull();
    expect(within(dialog).queryByText("근거 불일치")).toBeNull();
  });

  // 근거 접두어가 지워지면(라벨 없는 배지로 되돌아가면) 이 테스트가 잡는다 —
  // 모델(llmStatus)과 근거(verification) 두 배지가 나란히 설 때 어느 쪽인지
  // 구분할 유일한 단서가 이 접두어다.
  it("근거 접두어가 배지 옆에 표시된다", async () => {
    vi.mocked(generateDocumentCertificateByHistory).mockResolvedValue({
      grantType: "Bearer", accessToken: "a", refreshToken: "r",
      medicalCertificate: "소견",
      llmStatus: "real",
      verification: { status: "flagged", checks: [] },
    });
    renderWithAppliedDiagnosis();
    fireEvent.click(screen.getByRole("button", { name: /AI/ }));

    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText("근거")).toBeInTheDocument();
  });

  // 리뷰에서 지적된 갭: 모델 배지와 근거 배지가 하나의 컨테이너로 합쳐져도
  // 텍스트("모델", "근거")는 둘 다 여전히 존재하므로 문구 검사만으로는 못
  // 잡는다. 두 표시가 서로 다른 블록 컨테이너(div)에 있는지 구조로 확인한다.
  it("모델 표시와 근거 표시는 서로 다른 블록에 따로 선다", async () => {
    vi.mocked(generateDocumentCertificateByHistory).mockResolvedValue({
      grantType: "Bearer", accessToken: "a", refreshToken: "r",
      medicalCertificate: "소견",
      llmStatus: "fallback",
      verification: { status: "flagged", checks: [] },
    });
    renderWithAppliedDiagnosis();
    fireEvent.click(screen.getByRole("button", { name: /AI/ }));

    const dialog = await screen.findByRole("dialog");
    const modelLabel = await within(dialog).findByText("모델");
    const evidenceLabel = within(dialog).getByText("근거");

    const modelContainer = modelLabel.closest("div");
    const evidenceContainer = evidenceLabel.closest("div");

    expect(modelContainer).not.toBeNull();
    expect(evidenceContainer).not.toBeNull();
    expect(modelContainer).not.toBe(evidenceContainer);
    // 노드가 다르다는 것만으로는 부족하다. 한쪽을 다른 쪽 안에 중첩시켜도
    // closest("div") 가 서로 다른 노드를 돌려줘서 위 단언은 통과한다.
    // 두 표시는 나란히 선 형제여야 한다.
    expect(modelContainer!.parentElement).toBe(evidenceContainer!.parentElement);
    expect(modelContainer!.contains(evidenceContainer)).toBe(false);
    expect(evidenceContainer!.contains(modelContainer)).toBe(false);
  });

  // 생명주기: 미리보기 모달의 근거 표시는 그 미리보기가 담은 정확히 그 텍스트를
  // 설명한다. 수락하면 모달은 사라지고 텍스트는 편집 가능한 opinion 필드로
  // 옮겨간다 — 그 시점부터 의사가 자유롭게 고칠 수 있는 텍스트이므로, 검증
  // 당시의 근거 표시가 화면 어디에도 남아있으면 안 된다(더 이상 설명하는
  // 대상과 일치한다고 보장할 수 없다).
  it("수락 후에는 근거 표시가 화면에 남지 않는다", async () => {
    vi.mocked(generateDocumentCertificateByHistory).mockResolvedValue({
      grantType: "Bearer", accessToken: "a", refreshToken: "r",
      medicalCertificate: "소견",
      llmStatus: "real",
      verification: { status: "flagged", checks: [] },
    });
    renderWithAppliedDiagnosis();
    fireEvent.click(screen.getByRole("button", { name: /AI/ }));

    await screen.findByRole("dialog");
    expect(screen.getByText("근거 불일치")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "수락" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(screen.queryByText("근거 불일치")).toBeNull();
  });
});
