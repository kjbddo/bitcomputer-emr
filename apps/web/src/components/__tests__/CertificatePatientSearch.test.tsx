import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import CertificatePatientSearch from "../CertificatePatientSearch";

// @services 별칭이 vitest.config.ts 에 등록되지 않으면 이 컴포넌트를 import 하는
// 시점에 "Failed to resolve import '@services/certificate'" 로 테스트 파일 자체가
// 로드되지 못한다(리뷰어가 CertificatePatientSearch.tsx 에서 재현한 사례).
// 그래서 이 테스트는 별도 단언 없이도 "렌더가 된다"는 사실 자체로 별칭 배선을 검증한다.
vi.mock("@services/certificate", async () => {
  const actual = await vi.importActual<typeof import("@services/certificate")>(
    "@services/certificate"
  );
  return {
    ...actual,
    getAllPatients: vi.fn(),
    getPatientById: vi.fn(),
  };
});

describe("CertificatePatientSearch", () => {
  it("@services 별칭을 통해 정상적으로 렌더된다", () => {
    render(<CertificatePatientSearch onPatientFound={() => {}} />);
    expect(screen.getByText("환자 조회")).toBeInTheDocument();
  });
});
