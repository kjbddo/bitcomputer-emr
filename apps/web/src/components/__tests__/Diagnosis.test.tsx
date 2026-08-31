import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import Diagnosis from "../Diagnosis";
import { llmStatusNotice } from "@/utils/llmStatus";
import type { Verification } from "@/utils/verificationNotice";
import { MedicalSelectionProvider } from "@store/medicalSelection";
import {
  getValidationJob,
  recommendPrescriptions,
  searchPrescriptions,
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
    searchPrescriptions: vi.fn(),
  };
});

const mockedRecommend = vi.mocked(recommendPrescriptions);
const mockedGetJob = vi.mocked(getValidationJob);
const mockedSearch = vi.mocked(searchPrescriptions);

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
    // 위 부등호 비교만으로는 두 문구가 어떤 값으로 바뀌어도(둘이 다르기만
    // 하면) 통과한다. 실제 사용자에게 보이는 문구를 고정한다 — 이 값이
    // 실제로 가장 자주 나오는 값이다(현재 프로젝트에 LLM API 키가 없어
    // "real" 경로가 없으므로).
    expect(stub!.label).toBe("스텁 응답 (모델 미사용)");
  });

  // fallback 의 tone 만 확인하면 stub 분기의 tone 이 조용히 바뀌어도(예: neutral
  // -> warning) 이 describe 블록 전체가 통과해버린다.
  it("스텁의 tone 은 neutral 이다", () => {
    expect(llmStatusNotice("stub")!.tone).toBe("neutral");
  });

  // 필드가 없는 응답을 "모델이 돌았다"로 해석하면 이 태스크의 목적이 무너진다.
  it("필드가 없으면 모델이 돌았다고 가정하지 않는다", () => {
    expect(llmStatusNotice(undefined)).not.toBeNull();
  });

  // GC-2: 값이 없는 것과 "폴백으로 만들었다"는 다른 사실이다. 없는 값을
  // fallback 문구로 렌더하면 확립되지 않은 것을 주장하게 된다. fail-closed 는
  // 지키되(배지는 뜬다) 문구는 "모른다"여야 한다.
  it("필드가 없으면 폴백이라고 단정하지 않고 미확인으로 표시한다", () => {
    const missing = llmStatusNotice(undefined);
    const fallback = llmStatusNotice("fallback");
    expect(missing!.label).toBe("모델 출처 미확인");
    expect(missing!.label).not.toBe(fallback!.label);
    expect(missing!.tone).toBe("warning");
    expect(llmStatusNotice(null)!.label).toBe("모델 출처 미확인");
  });

  // 계약 밖 값도 마찬가지다. "REAL" 은 real 이 아니지만 fallback 이라는 근거도
  // 없다 — 아는 것만 말한다.
  it("계약 밖 값은 폴백이 아니라 미확인이다", () => {
    expect(llmStatusNotice("REAL")!.label).toBe("모델 출처 미확인");
  });

  // "real" 정확 일치만 통과시켜야 한다. 대소문자를 관대하게 받아주면(예:
  // .toLowerCase() === "real") 오늘은 우연히 안전해도 계약을 느슨하게 만드는
  // 변경이 조용히 들어올 수 있다. 대문자 "REAL" 은 계약 밖 값이므로 여전히
  // fail-closed 여야 한다.
  it("real 이 아닌 다른 대소문자 표기는 모델이 돌았다고 인정하지 않는다", () => {
    expect(llmStatusNotice("REAL")).not.toBeNull();
  });
});

// llmStatusNotice 단위 테스트만으로는 실제 모달이 validationModal.result?.llmStatus
// 를 제대로 읽어 배지에 넘기는지 확인할 수 없다 — 이 배선이 끊겨도(예: 엉뚱한 필드를
// 읽거나 하드코딩된 값을 넘겨도) 위 단위 테스트는 전부 통과한다. 그래서 실제 렌더
// 경로(AI 처방 추천 클릭 -> 작업 폴링 -> 모달 오픈)를 통해 배지 문구가 실제로
// 나타나는지 확인한다.
//
// 모달을 열면 같은 llmStatus 배지가 모달과 "AI 추천 처방" 패널 양쪽에 동시에
// 뜬다(패널은 모달을 닫아도 남는다 — 아래 "모달을 닫아도" 테스트 참고). 그래서
// 텍스트 매칭은 모달 안으로 범위를 좁혀 getByRole("dialog") 로 스코프한다.
describe("검증 모달의 llmStatus 배선", () => {
  const clinicVisit = { patientId: 1, deptId: 1 };

  function renderDiagnosis() {
    return render(
      <MedicalSelectionProvider>
        <Diagnosis clinicVisit={clinicVisit} ensureHistory={async () => 10} employeeId={1} />
      </MedicalSelectionProvider>
    );
  }

  // 모달 배지는 validation-agent 자신의 llmStatus 를, 패널 배지는
  // prescription-api 의 prescriptionLlmStatus 를 읽는다(F-H3). 이 헬퍼는 모달
  // 배선을 보는 것이 목적이라 두 값을 같게 두어 패널/모달 문구를 일치시킨다 —
  // 두 축이 실제로 갈라지는 경우는 아래 전용 describe 에서 따로 고정한다.
  function mockJobWithLlmStatus(jobId: string, llmStatus: string) {
    mockedRecommend.mockResolvedValue({ jobId, historyId: 10, status: "RUNNING" });
    mockedGetJob.mockResolvedValue({
      jobId,
      historyId: 10,
      status: "DONE",
      result: {
        overallStatus: "PASS",
        summary: "이상 없음",
        llmStatus,
        prescriptionLlmStatus: llmStatus,
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
  }

  it("결과의 llmStatus 가 fallback 이면 모달에 모델 미사용 배지가 뜬다", async () => {
    mockJobWithLlmStatus("job-1", "fallback");

    renderDiagnosis();
    fireEvent.click(screen.getByRole("button", { name: "AI 처방 추천" }));

    const dialog = await screen.findByRole("dialog");
    const noticeBadge = await within(dialog).findByText("규칙 기반 결과 — 모델 미사용");
    // M5: tone 을 문구가 아니라 배지 자체(class/속성)로도 확인한다. 문구만
    // 확인하면 warning -> neutral 로 tone 이 조용히 바뀌어도 못 잡는다.
    expect(noticeBadge).toHaveAttribute("data-tone", "warning");
    // overallStatus 가 WARNING/NEEDS_REVIEW 면 amber 배지가 둘 나란히 선다.
    // 이 접두어가 둘 중 어느 쪽이 실행 경로 표시인지 구분해준다. 없으면
    // 무라벨 amber 칩 두 개로 조용히 되돌아간다.
    expect(within(dialog).getByText("모델")).toBeInTheDocument();
  });

  it("결과의 llmStatus 가 real 이면 모델 미사용 배지가 뜨지 않는다", async () => {
    mockJobWithLlmStatus("job-2", "real");

    renderDiagnosis();
    fireEvent.click(screen.getByRole("button", { name: "AI 처방 추천" }));

    await waitFor(() => {
      expect(screen.getByText("이상 없음")).toBeInTheDocument();
    });
    expect(screen.queryByText(/모델 미사용/)).toBeNull();
  });

  // IMPORTANT 3: 모달은 확인 클릭으로 사라지지만, aiRecommendations 와 함께
  // 화면에 남는 "AI 추천 처방" 패널에는 llmStatus 를 알려줄 방법이 없었다.
  // 모달을 닫은 뒤에도 배지가 패널에 남아 있는지 실제 렌더 경로로 확인한다.
  it("모달을 닫아도 AI 추천 처방 패널에 모델 미사용 배지가 남는다", async () => {
    mockJobWithLlmStatus("job-3", "fallback");

    renderDiagnosis();
    fireEvent.click(screen.getByRole("button", { name: "AI 처방 추천" }));

    const dialog = await screen.findByRole("dialog");
    await within(dialog).findByText("규칙 기반 결과 — 모델 미사용");

    fireEvent.click(screen.getByRole("button", { name: "확인" }));

    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });

    const panelBadge = screen.getByText("규칙 기반 결과 — 모델 미사용");
    expect(panelBadge).toBeInTheDocument();
    expect(panelBadge).toHaveAttribute("data-tone", "warning");
  });
});

// IMPORTANT 3(최종 리뷰): 최상위 llmStatus 배지는 작업 전체를 하나로 뭉뚱그린다.
// fallback 작업이라도 reasoningTrace 의 개별 스텝은 llm 출처일 수 있고 그
// 반대도 가능하다 — "검증 이유" 목록은 step.source 를 무시하고 action/
// observation 만 이어붙였으므로, 하드코딩된 폴백 thought 문구가 모델 추론처럼
// 읽힐 수 있었다(spec §6.3 완료 조건 6: "사람이 트레이스만 보고 LLM 추론으로
// 오인할 수 없어야 한다"). 스텝별 출처 표시가 실제로 렌더되는지 렌더 경로로
// 확인한다.
describe("검증 이유 목록의 스텝별 출처 표시", () => {
  const clinicVisit = { patientId: 1, deptId: 1 };

  function renderDiagnosis() {
    return render(
      <MedicalSelectionProvider>
        <Diagnosis clinicVisit={clinicVisit} ensureHistory={async () => 10} employeeId={1} />
      </MedicalSelectionProvider>
    );
  }

  function mockJobWithTrace(jobId: string, reasoningTrace: Array<Record<string, unknown>>) {
    mockedRecommend.mockResolvedValue({ jobId, historyId: 10, status: "RUNNING" });
    mockedGetJob.mockResolvedValue({
      jobId,
      historyId: 10,
      status: "DONE",
      result: {
        overallStatus: "PASS",
        summary: "이상 없음",
        llmStatus: "real",
        reasoningTrace,
        recommendedPrescriptions: [],
      },
    } as unknown as ValidationJobResponse);
  }

  it("source 가 rule/fallback 인 스텝에는 (규칙 기반) 표시가 붙는다", async () => {
    mockJobWithTrace("job-trace-1", [
      {
        action: "질병 검증",
        observation: { status: "MATCH", evidence: ["근거 A"] },
        source: "fallback",
      },
    ]);

    renderDiagnosis();
    fireEvent.click(screen.getByRole("button", { name: "AI 처방 추천" }));

    const dialog = await screen.findByRole("dialog");
    expect(
      await within(dialog).findByText("질병 검증 (규칙 기반): MATCH - 근거 A")
    ).toBeInTheDocument();
  });

  it("source 가 stub 인 스텝에는 (스텁) 표시가 붙는다", async () => {
    mockJobWithTrace("job-trace-2", [
      {
        action: "처방 검증",
        observation: { status: "APPROPRIATE", evidence: ["근거 B"] },
        source: "stub",
      },
    ]);

    renderDiagnosis();
    fireEvent.click(screen.getByRole("button", { name: "AI 처방 추천" }));

    const dialog = await screen.findByRole("dialog");
    expect(
      await within(dialog).findByText("처방 검증 (스텁): APPROPRIATE - 근거 B")
    ).toBeInTheDocument();
  });

  it("source 가 llm 인 스텝에는 출처 표시가 붙지 않는다", async () => {
    mockJobWithTrace("job-trace-3", [
      {
        action: "PubMed 요약",
        observation: { status: "LOADED", evidence: ["근거 C"] },
        source: "llm",
      },
    ]);

    renderDiagnosis();
    fireEvent.click(screen.getByRole("button", { name: "AI 처방 추천" }));

    const dialog = await screen.findByRole("dialog");
    expect(
      await within(dialog).findByText("PubMed 요약: LOADED - 근거 C")
    ).toBeInTheDocument();
    expect(within(dialog).queryByText(/PubMed 요약 \(/)).toBeNull();
  });

  // source 가 없거나 계약 밖이면 모델 추론과 구분되지 않는다. 이 브랜치의 다른
  // 모든 경계와 같은 방향으로, "llm" 정확 일치만 무표시여야 한다.
  it("source 가 없는 스텝은 모델 추론으로 보이지 않는다", async () => {
    mockJobWithTrace("job-trace-4", [
      {
        action: "질병 검증",
        observation: { status: "MATCH", evidence: ["근거 D"] },
      },
    ]);

    renderDiagnosis();
    fireEvent.click(screen.getByRole("button", { name: "AI 처방 추천" }));

    const dialog = await screen.findByRole("dialog");
    expect(
      await within(dialog).findByText("질병 검증 (규칙 기반): MATCH - 근거 D")
    ).toBeInTheDocument();
  });

  it("source 가 계약 밖 값이면 모델 추론으로 보이지 않는다", async () => {
    mockJobWithTrace("job-trace-5", [
      {
        action: "처방 검증",
        observation: { status: "OK", evidence: ["근거 E"] },
        source: "RULE",
      },
    ]);

    renderDiagnosis();
    fireEvent.click(screen.getByRole("button", { name: "AI 처방 추천" }));

    const dialog = await screen.findByRole("dialog");
    expect(
      await within(dialog).findByText("처방 검증 (규칙 기반): OK - 근거 E")
    ).toBeInTheDocument();
  });
});

// verification 은 llmStatus 와 다른 축("출력이 조회 결과로 추적되나")이다.
// aiRecommendations 와 같은 생명주기를 가져야 하므로(모달을 닫아도 패널에
// 남아야 한다), 실제 렌더 경로로 확인한다.
describe("처방 표의 항목 단위 검증 표시", () => {
  const clinicVisit = { patientId: 1, deptId: 1 };

  function renderDiagnosis() {
    return render(
      <MedicalSelectionProvider>
        <Diagnosis clinicVisit={clinicVisit} ensureHistory={async () => 10} employeeId={1} />
      </MedicalSelectionProvider>
    );
  }

  // 처방 항목 배지(prescription[N])는 result.prescriptionVerification 을 읽는다
  // (최종 리뷰 C1) — result.verification 은 validation-agent 자기 자신의 검증이고
  // 검사 전부 target="response" 라 이 배지에는 절대 도달하지 않는다. 이 헬퍼는
  // 백엔드가 실제로 만들 수 있는 payload 모양으로 mock 한다.
  function mockJobWithPrescriptionVerification(
    jobId: string,
    prescriptionVerification: Verification | undefined
  ) {
    mockedRecommend.mockResolvedValue({ jobId, historyId: 10, status: "RUNNING" });
    mockedGetJob.mockResolvedValue({
      jobId,
      historyId: 10,
      status: "DONE",
      result: {
        overallStatus: "PASS",
        summary: "이상 없음",
        llmStatus: "real",
        prescriptionVerification,
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
    } as unknown as ValidationJobResponse);
  }

  it("근거 불일치인 처방 행에 표시가 붙는다", async () => {
    mockJobWithPrescriptionVerification("job-v-1", {
      status: "flagged",
      checks: [
        { id: "code_in_candidates", target: "prescription[1]", outcome: "flagged", evidence: "" },
      ],
    });

    renderDiagnosis();
    fireEvent.click(screen.getByRole("button", { name: "AI 처방 추천" }));

    // Task 10부터 검증 모달도 같은 문구("근거 불일치")를 낼 수 있어, 이 테스트가
    // 확인하려는 "처방 행" 표시는 표로 범위를 좁혀야 모달의 표시와 섞이지 않는다.
    const table = await screen.findByRole("table");
    expect(await within(table).findByText("근거 불일치")).toBeInTheDocument();
  });

  it("verification 이 없으면 미검증으로 표시한다", async () => {
    mockJobWithPrescriptionVerification("job-v-2", undefined);

    renderDiagnosis();
    fireEvent.click(screen.getByRole("button", { name: "AI 처방 추천" }));

    const table = await screen.findByRole("table");
    expect(await within(table).findByText("미검증")).toBeInTheDocument();
  });

  it("모달을 닫아도 패널의 검증 표시가 남는다", async () => {
    mockJobWithPrescriptionVerification("job-v-3", {
      status: "flagged",
      checks: [
        { id: "code_in_candidates", target: "prescription[1]", outcome: "flagged", evidence: "" },
      ],
    });

    renderDiagnosis();
    fireEvent.click(screen.getByRole("button", { name: "AI 처방 추천" }));
    await screen.findByRole("dialog");
    fireEvent.click(screen.getByRole("button", { name: "확인" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(screen.getByText("근거 불일치")).toBeInTheDocument();
  });

  it("요약이 근거 불일치와 미검증을 따로 센다", async () => {
    mockedRecommend.mockResolvedValue({ jobId: "job-v-5", historyId: 10, status: "RUNNING" });
    mockedGetJob.mockResolvedValue({
      jobId: "job-v-5",
      historyId: 10,
      status: "DONE",
      result: {
        overallStatus: "PASS",
        summary: "이상 없음",
        llmStatus: "real",
        prescriptionVerification: {
          status: "flagged",
          checks: [
            { id: "code_in_candidates", target: "prescription[1]", outcome: "flagged", evidence: "" },
            { id: "code_in_candidates", target: "prescription[2]", outcome: "skipped", evidence: "" },
            { id: "code_in_candidates", target: "prescription[3]", outcome: "ok", evidence: "" },
          ],
        },
        recommendedPrescriptions: [
          { id: 1, rank: 1, prescription_code: "C1", prescription_name: "약1", reason: "", confidence_score: 0.9, dose: 1, time: 1, days: 1 },
          { id: 2, rank: 2, prescription_code: "C2", prescription_name: "약2", reason: "", confidence_score: 0.9, dose: 1, time: 1, days: 1 },
          { id: 3, rank: 3, prescription_code: "C3", prescription_name: "약3", reason: "", confidence_score: 0.9, dose: 1, time: 1, days: 1 },
        ],
      },
    } as unknown as ValidationJobResponse);

    renderDiagnosis();
    fireEvent.click(screen.getByRole("button", { name: "AI 처방 추천" }));

    expect(await screen.findByText(/근거 불일치 1건/)).toBeInTheDocument();
    expect(screen.getByText(/미검증 1건/)).toBeInTheDocument();
  });

  // --- M1: 응답 단위 검사가 처방 화면에 도달한다 ---------------------------
  //
  // schema_top3 는 target="response" 라 항목별 집계에 들어가지 않는다. 요약
  // 줄이 항목 outcome 만 세면 이 검사는 flagged 여도 처방 표면에 아무 표시가
  // 남지 않는다. 항목 문제와 응답 문제는 의사에게 다른 정보이므로 한 숫자로
  // 합치지 않고 각각 읽을 수 있게 낸다.

  it("항목이 전부 ok 여도 응답 단위 검사가 flagged 면 요약에 나타난다", async () => {
    mockJobWithPrescriptionVerification("job-v-m1-1", {
      status: "flagged",
      checks: [
        { id: "schema_top3", target: "response", outcome: "flagged", evidence: "rank=[1,1,3]" },
        { id: "code_in_candidates", target: "prescription[1]", outcome: "ok", evidence: "" },
        { id: "confidence_in_range", target: "prescription[1]", outcome: "ok", evidence: "" },
      ],
    });

    renderDiagnosis();
    fireEvent.click(screen.getByRole("button", { name: "AI 처방 추천" }));

    expect(await screen.findByText("검증(응답 전체): 근거 불일치")).toBeInTheDocument();
  });

  it("항목 문제와 응답 문제를 한 숫자로 합치지 않고 따로 낸다", async () => {
    mockJobWithPrescriptionVerification("job-v-m1-2", {
      status: "flagged",
      checks: [
        { id: "schema_top3", target: "response", outcome: "flagged", evidence: "" },
        { id: "code_in_candidates", target: "prescription[1]", outcome: "skipped", evidence: "" },
      ],
    });

    renderDiagnosis();
    fireEvent.click(screen.getByRole("button", { name: "AI 처방 추천" }));

    // 항목 줄: 1건 중 미검증 1건 (응답 단위 flagged 가 항목 숫자에 섞이지 않는다)
    expect(await screen.findByText("검증: 1건 중 미검증 1건")).toBeInTheDocument();
    // 응답 줄: 따로
    expect(screen.getByText("검증(응답 전체): 근거 불일치")).toBeInTheDocument();
  });

  // fail-closed(GC-3). 응답 단위 검사가 오지 않은 응답을 "응답 단위는 문제
  // 없음" 으로 읽으면 이 표시가 존재할 이유가 사라진다.
  it("응답 단위 검사가 아예 없으면 응답 줄이 미검증으로 뜬다", async () => {
    mockJobWithPrescriptionVerification("job-v-m1-3", {
      status: "passed",
      checks: [
        { id: "code_in_candidates", target: "prescription[1]", outcome: "ok", evidence: "" },
      ],
    });

    renderDiagnosis();
    fireEvent.click(screen.getByRole("button", { name: "AI 처방 추천" }));

    expect(await screen.findByText("검증(응답 전체): 미검증")).toBeInTheDocument();
  });

  it("항목과 응답 단위가 모두 정상이면 요약 줄이 아예 뜨지 않는다", async () => {
    mockJobWithPrescriptionVerification("job-v-m1-4", {
      status: "passed",
      checks: [
        { id: "schema_top3", target: "response", outcome: "ok", evidence: "" },
        { id: "code_in_candidates", target: "prescription[1]", outcome: "ok", evidence: "" },
      ],
    });

    renderDiagnosis();
    fireEvent.click(screen.getByRole("button", { name: "AI 처방 추천" }));

    await screen.findByRole("table");
    expect(screen.queryByText(/^검증: /)).not.toBeInTheDocument();
    expect(screen.queryByText(/^검증\(응답 전체\): /)).not.toBeInTheDocument();
  });

  // Task 10: modalCardHead 에는 이미 overallStatus 배지와 모델 배지가 있다 —
  // 검증 표시는 그 아래(modalReason 과 검증 이유 목록 사이) 별도 줄에 서야
  // 한다. 세 배지를 한 줄에 쌓으면 셋 다 안 읽힌다(spec §7.1).
  it("검증 모달에 근거 표시가 뜬다", async () => {
    // 모달의 "근거" 표시는 validation-agent 자기 자신의 verification(항상
    // target="response")을 읽는다 — 처방 항목 배지(prescriptionVerification)와는
    // 다른 값이다.
    mockedRecommend.mockResolvedValue({ jobId: "job-v-4", historyId: 10, status: "RUNNING" });
    mockedGetJob.mockResolvedValue({
      jobId: "job-v-4",
      historyId: 10,
      status: "DONE",
      result: {
        overallStatus: "PASS",
        summary: "이상 없음",
        llmStatus: "real",
        verification: { status: "flagged", checks: [] },
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
    } as unknown as ValidationJobResponse);

    renderDiagnosis();
    fireEvent.click(screen.getByRole("button", { name: "AI 처방 추천" }));

    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText("근거")).toBeInTheDocument();
    expect(within(dialog).getByText("근거 불일치")).toBeInTheDocument();
  });

  // M2 — §10.4 의 fail-closed 네 shape(undefined/null/"PASSED"/"bogus")이
  // 순수 함수(verificationNotice.test.ts) 밖에서는 "필드 누락" 하나로만
  // 구동됐다. null/계약 밖 값도 이 모달 렌더 경로를 통과시킨다.
  it("검증 모달의 근거 표시: verification.status 가 null 이면 미검증", async () => {
    mockedRecommend.mockResolvedValue({ jobId: "job-v-8", historyId: 10, status: "RUNNING" });
    mockedGetJob.mockResolvedValue({
      jobId: "job-v-8",
      historyId: 10,
      status: "DONE",
      result: {
        overallStatus: "PASS",
        summary: "이상 없음",
        llmStatus: "real",
        verification: { status: null, checks: [] },
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
    } as unknown as ValidationJobResponse);

    renderDiagnosis();
    fireEvent.click(screen.getByRole("button", { name: "AI 처방 추천" }));

    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText("미검증")).toBeInTheDocument();
  });

  it("검증 모달의 근거 표시: 계약 밖 status 값도 미검증으로 본다", async () => {
    mockedRecommend.mockResolvedValue({ jobId: "job-v-9", historyId: 10, status: "RUNNING" });
    mockedGetJob.mockResolvedValue({
      jobId: "job-v-9",
      historyId: 10,
      status: "DONE",
      result: {
        overallStatus: "PASS",
        summary: "이상 없음",
        llmStatus: "real",
        verification: { status: "bogus", checks: [] },
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
    } as unknown as ValidationJobResponse);

    renderDiagnosis();
    fireEvent.click(screen.getByRole("button", { name: "AI 처방 추천" }));

    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText("미검증")).toBeInTheDocument();
  });

  // 리뷰에서 지적된 갭: 근거 표시 텍스트가 어딘가에 있다는 것만으로는 그게
  // modalCardHead 안(overallStatus 배지, 모델 배지와 한 줄)으로 옮겨져도 안
  // 잡힌다 — 이 저장소가 이미 겪은 "세 배지가 한 줄"(spec §7.1 위반) 실패를
  // 그대로 재현해도 통과해버린다. 텍스트 존재가 아니라 컨테이너 소속을 검사한다.
  it("근거 표시는 modalCardHead 배지 줄에 속하지 않는다", async () => {
    // 모델 배지도 함께 떠야 modalCardHead 를 "모델" 라벨로 특정할 수 있다
    // (mockJobWithVerification 은 llmStatus 를 "real" 로 고정해 모델 배지가
    // 안 뜬다).
    mockedRecommend.mockResolvedValue({ jobId: "job-v-7", historyId: 10, status: "RUNNING" });
    mockedGetJob.mockResolvedValue({
      jobId: "job-v-7",
      historyId: 10,
      status: "DONE",
      result: {
        overallStatus: "PASS",
        summary: "이상 없음",
        llmStatus: "fallback",
        verification: { status: "flagged", checks: [] },
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
    } as unknown as ValidationJobResponse);

    renderDiagnosis();
    fireEvent.click(screen.getByRole("button", { name: "AI 처방 추천" }));

    const dialog = await screen.findByRole("dialog");
    const modelLabel = await within(dialog).findByText("모델");
    // modelLabel 은 <span class=llmStatusGroupLabel> 이고 그 부모가
    // <span class=llmStatusGroup>, 그 부모가 modalCardHead div 다. 클래스
    // 이름에 의존하지 않고 가장 가까운 div 조상을 찾으면 modalCardHead 다.
    const badgeRow = modelLabel.closest("div");
    expect(badgeRow).not.toBeNull();

    const evidenceLabel = within(dialog).getByText("근거");
    expect(badgeRow!.contains(evidenceLabel)).toBe(false);

    // modalCardHead 밖이라는 것만으로는 부족하다. 배지 줄 바로 아래이면서
    // 요약 문단보다 위여도 이 단언은 통과한다. 브리프가 지정한 자리는
    // "요약 문단 아래, 검증 이유 목록 위" 다.
    const summary = within(dialog).getByText("이상 없음");
    // DOCUMENT_POSITION_FOLLOWING = 4. 근거 표시가 요약보다 뒤에 와야 한다.
    expect(
      summary.compareDocumentPosition(evidenceLabel) &
        Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy();
  });
});

// CRITICAL: 배지는 rank 로 조회하지만(`prescription[${rank}]`), 의사는 "처방
// 상세 선택" 피커로 그 rank 에 앉은 처방 자체를 바꿀 수 있다. rank 는 그대로라
// 바뀐 뒤에도 옛 처방을 검사한 결과가 계속 표시된다 — 한 번도 검사 안 된
// 처방이 "검증됨"(무배지)으로 보이는, 이 기능이 막으려던 정확히 그 반전이다.
// 스왑된 rank 만 미검증으로 무효화되고 손대지 않은 다른 rank 는 원래 검증을
// 유지해야 한다(전체를 지우면 유효한 신호까지 파괴한다).
describe("처방 상세 선택으로 처방을 바꾸면 그 rank 의 검증이 무효화된다", () => {
  const clinicVisit = { patientId: 1, deptId: 1 };

  function renderDiagnosis() {
    return render(
      <MedicalSelectionProvider>
        <Diagnosis clinicVisit={clinicVisit} ensureHistory={async () => 10} employeeId={1} />
      </MedicalSelectionProvider>
    );
  }

  function mockJobWithTwoItems(jobId: string) {
    mockedRecommend.mockResolvedValue({ jobId, historyId: 10, status: "RUNNING" });
    mockedGetJob.mockResolvedValue({
      jobId,
      historyId: 10,
      status: "DONE",
      result: {
        overallStatus: "PASS",
        summary: "이상 없음",
        llmStatus: "real",
        prescriptionVerification: {
          status: "flagged",
          checks: [
            { id: "code_in_candidates", target: "prescription[1]", outcome: "ok", evidence: "" },
            { id: "code_in_candidates", target: "prescription[2]", outcome: "flagged", evidence: "" },
          ],
        },
        recommendedPrescriptions: [
          { id: 1, rank: 1, prescription_code: "C1", prescription_name: "약1", reason: "", confidence_score: 0.9, dose: 1, time: 1, days: 1 },
          { id: 2, rank: 2, prescription_code: "C2", prescription_name: "약2", reason: "", confidence_score: 0.9, dose: 1, time: 1, days: 1 },
        ],
      },
    } as unknown as ValidationJobResponse);
  }

  it("검증이 ok 였던 rank 를 스왑하면 그 행은 미검증으로 바뀌고 다른 rank 는 유지된다", async () => {
    mockJobWithTwoItems("job-swap-1");
    mockedSearch.mockResolvedValue({
      items: [{ id: 99, code: "C9", name: "약9", dose: 2, time: 2, days: 2 }],
      total: 1,
      page: 0,
      pageSize: 20,
    });

    renderDiagnosis();
    fireEvent.click(screen.getByRole("button", { name: "AI 처방 추천" }));

    const dialog = await screen.findByRole("dialog", { name: "검증 완료" });
    fireEvent.click(within(dialog).getByRole("button", { name: "확인" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "검증 완료" })).not.toBeInTheDocument());

    // 스왑 전: rank1(ok) 는 무배지, rank2(flagged) 만 "근거 불일치"
    expect(screen.queryByText("미검증")).not.toBeInTheDocument();
    expect(screen.getByText("근거 불일치")).toBeInTheDocument();
    expect(screen.getByText(/검증: 2건 중 근거 불일치 1건/)).toBeInTheDocument();

    // rank1("약1") 행의 "처방 상세 선택" 버튼으로 스왑
    const detailButtons = screen.getAllByRole("button", { name: "처방 상세 선택" });
    fireEvent.click(detailButtons[0]);

    const pickerDialog = await screen.findByRole("dialog", { name: "처방 상세 선택" });
    fireEvent.click(await within(pickerDialog).findByRole("button", { name: "선택" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "처방 상세 선택" })).not.toBeInTheDocument());

    // 스왑 후: 새 처방이 앉은 rank1 은 미검증, 손대지 않은 rank2 는 여전히 근거 불일치
    expect(screen.getByText(/약9/)).toBeInTheDocument();
    expect(await screen.findByText("미검증")).toBeInTheDocument();
    expect(screen.getByText("근거 불일치")).toBeInTheDocument();
    // flagged 와 skipped 를 따로 세는 요약도 스왑을 반영해 이동한다
    expect(screen.getByText(/검증: 2건 중 근거 불일치 1건, 미검증 1건/)).toBeInTheDocument();
  });

  // 응답 단위 검사(schema_top3)는 "rank 집합이 {1,2,3} 인가" 와 "코드 중복이
  // 없는가" 를 그때 화면에 있던 처방코드 집합에 대해 판정한 결과다. 스왑은 그
  // 집합을 바꾼다 — 스왑으로 들어온 코드가 다른 행과 겹쳐도 옛 판정은 여전히
  // ok 이므로, 그대로 두면 검사된 적 없는 조합이 "응답 단위 이상 없음" 으로
  // 보인다. 항목 배지와 같은 이유로 스왑이 있으면 응답 줄도 미검증이다.
  it("스왑이 있으면 응답 단위 판정도 미검증으로 무효화된다", async () => {
    mockedRecommend.mockResolvedValue({ jobId: "job-swap-3", historyId: 10, status: "RUNNING" });
    mockedGetJob.mockResolvedValue({
      jobId: "job-swap-3",
      historyId: 10,
      status: "DONE",
      result: {
        overallStatus: "PASS",
        summary: "이상 없음",
        llmStatus: "real",
        prescriptionVerification: {
          status: "passed",
          checks: [
            { id: "schema_top3", target: "response", outcome: "ok", evidence: "" },
            { id: "code_in_candidates", target: "prescription[1]", outcome: "ok", evidence: "" },
            { id: "code_in_candidates", target: "prescription[2]", outcome: "ok", evidence: "" },
          ],
        },
        recommendedPrescriptions: [
          { id: 1, rank: 1, prescription_code: "C1", prescription_name: "약1", reason: "", confidence_score: 0.9, dose: 1, time: 1, days: 1 },
          { id: 2, rank: 2, prescription_code: "C2", prescription_name: "약2", reason: "", confidence_score: 0.9, dose: 1, time: 1, days: 1 },
        ],
      },
    } as unknown as ValidationJobResponse);
    mockedSearch.mockResolvedValue({
      items: [{ id: 99, code: "C2", name: "약2", dose: 2, time: 2, days: 2 }],
      total: 1,
      page: 0,
      pageSize: 20,
    });

    renderDiagnosis();
    fireEvent.click(screen.getByRole("button", { name: "AI 처방 추천" }));

    const dialog = await screen.findByRole("dialog", { name: "검증 완료" });
    fireEvent.click(within(dialog).getByRole("button", { name: "확인" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "검증 완료" })).not.toBeInTheDocument());

    // 스왑 전: 응답 단위도 항목도 전부 ok 라 요약 줄이 없다
    expect(screen.queryByText("검증(응답 전체): 미검증")).not.toBeInTheDocument();

    // rank1 을 rank2 와 같은 코드("C2")로 스왑한다 — schema_top3 의 코드중복
    // 조건이 다시 판정돼야 할 상황이지만 옛 판정은 여전히 ok 다.
    const detailButtons = screen.getAllByRole("button", { name: "처방 상세 선택" });
    fireEvent.click(detailButtons[0]);
    const pickerDialog = await screen.findByRole("dialog", { name: "처방 상세 선택" });
    fireEvent.click(await within(pickerDialog).findByRole("button", { name: "선택" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "처방 상세 선택" })).not.toBeInTheDocument());

    expect(await screen.findByText("검증(응답 전체): 미검증")).toBeInTheDocument();
  });

  // 스왑 집합은 그것이 무효화하는 aiVerification 과 정확히 같은 생명주기를 가져야
  // 한다. 새 세대(재생성)가 시작되면 이전 세대에서 쌓인 스왑 기록은 더 이상
  // 의미가 없다 — 지우지 않으면 새로 생성된, 실제로는 한 번도 스왑되지 않은
  // rank 가 옛 스왑 이력 때문에 미검증으로 잘못 표시된다.
  it("재생성하면 이전 세대의 스왑 이력이 초기화되어 새 검증 결과를 그대로 보여준다", async () => {
    mockJobWithTwoItems("job-swap-2");
    mockedSearch.mockResolvedValue({
      items: [{ id: 99, code: "C9", name: "약9", dose: 2, time: 2, days: 2 }],
      total: 1,
      page: 0,
      pageSize: 20,
    });

    renderDiagnosis();
    fireEvent.click(screen.getByRole("button", { name: "AI 처방 추천" }));

    const dialog = await screen.findByRole("dialog", { name: "검증 완료" });
    fireEvent.click(within(dialog).getByRole("button", { name: "확인" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "검증 완료" })).not.toBeInTheDocument());

    const detailButtons = screen.getAllByRole("button", { name: "처방 상세 선택" });
    fireEvent.click(detailButtons[0]);
    const pickerDialog = await screen.findByRole("dialog", { name: "처방 상세 선택" });
    fireEvent.click(await within(pickerDialog).findByRole("button", { name: "선택" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "처방 상세 선택" })).not.toBeInTheDocument());

    expect(await screen.findByText("미검증")).toBeInTheDocument();

    // 재생성: 새 세대는 rank1 이 ok 로 검증됐다고 알려준다(이번엔 스왑한 적 없다)
    mockedRecommend.mockResolvedValue({ jobId: "job-swap-2b", historyId: 10, status: "RUNNING" });
    mockedGetJob.mockResolvedValue({
      jobId: "job-swap-2b",
      historyId: 10,
      status: "DONE",
      result: {
        overallStatus: "PASS",
        summary: "이상 없음",
        llmStatus: "real",
        prescriptionVerification: {
          status: "passed",
          checks: [
            { id: "code_in_candidates", target: "prescription[1]", outcome: "ok", evidence: "" },
          ],
        },
        recommendedPrescriptions: [
          { id: 1, rank: 1, prescription_code: "C1", prescription_name: "약1", reason: "", confidence_score: 0.9, dose: 1, time: 1, days: 1 },
        ],
      },
    } as unknown as ValidationJobResponse);

    fireEvent.click(screen.getByRole("button", { name: "AI 처방 추천" }));
    const dialog2 = await screen.findByRole("dialog", { name: "검증 완료" });
    fireEvent.click(within(dialog2).getByRole("button", { name: "확인" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "검증 완료" })).not.toBeInTheDocument());

    // 이전 세대의 스왑 이력이 새 세대까지 이어지면 안 된다 — rank1 은 ok 이므로 무배지
    expect(screen.queryByText("미검증")).not.toBeInTheDocument();
    expect(screen.queryByText("근거 불일치")).not.toBeInTheDocument();
  });
});

// IMPORTANT: aiRecommendations 가 clear 되는 두 리셋 지점(환자 전환, 진료/이력
// 전환)에서 aiLlmStatus·aiVerification 도 함께 clear 된다. 셋 다 이 패널
// 안에서만(aiRecommendations.length > 0 게이트 안에서만) 보이므로, 패널이
// 사라지는지를 렌더 경로로 확인하는 것이 이 세 state 가 실제로 초기화됐는지
// 확인하는 유일한 방법이다 — 게이트 자체가 사라지면(예: setAiRecommendations([])
// 호출이 지워지면) 이전 환자/진료의 배지가 새 화면에 그대로 남는다.
describe("환자·진료 전환 시 AI 추천/검증 상태가 초기화된다", () => {
  function mockJobWithBadges(jobId: string, historyId: number) {
    mockedRecommend.mockResolvedValue({ jobId, historyId, status: "RUNNING" });
    mockedGetJob.mockResolvedValue({
      jobId,
      historyId,
      status: "DONE",
      result: {
        overallStatus: "PASS",
        summary: "이상 없음",
        llmStatus: "fallback",
        // 패널 배지는 prescription-api 의 값을 읽는다(F-H3). 이 describe 는
        // 배지의 출처가 아니라 "전환 시 초기화되는가"를 보므로 두 축을 같게 둔다.
        prescriptionLlmStatus: "fallback",
        prescriptionVerification: {
          status: "flagged",
          checks: [
            { id: "code_in_candidates", target: "prescription[1]", outcome: "flagged", evidence: "" },
          ],
        },
        recommendedPrescriptions: [
          { id: 1, rank: 1, prescription_code: "C1", prescription_name: "약1", reason: "", confidence_score: 0.9, dose: 1, time: 1, days: 1 },
        ],
      },
    } as unknown as ValidationJobResponse);
  }

  it("환자가 바뀌면 이전 환자의 AI 추천 패널·배지가 사라진다", async () => {
    mockJobWithBadges("job-reset-patient", 10);

    const { rerender } = render(
      <MedicalSelectionProvider>
        <Diagnosis
          clinicVisit={{ patientId: 1, deptId: 1 }}
          ensureHistory={async () => 10}
          employeeId={1}
        />
      </MedicalSelectionProvider>
    );
    fireEvent.click(screen.getByRole("button", { name: "AI 처방 추천" }));

    await screen.findByRole("dialog");
    fireEvent.click(screen.getByRole("button", { name: "확인" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

    expect(screen.getByText("근거 불일치")).toBeInTheDocument();
    expect(screen.getByText("규칙 기반 결과 — 모델 미사용")).toBeInTheDocument();
    expect(screen.getByText("AI 추천 처방")).toBeInTheDocument();

    rerender(
      <MedicalSelectionProvider>
        <Diagnosis
          clinicVisit={{ patientId: 2, deptId: 1 }}
          ensureHistory={async () => 10}
          employeeId={1}
        />
      </MedicalSelectionProvider>
    );

    // aiRecommendations 가 clear 되어 패널 전체가 사라져야 한다. 패널이 남아있으면
    // aiLlmStatus/aiVerification 도 이전 환자 값을 그대로 들고 있다는 뜻이다.
    expect(screen.queryByText("AI 추천 처방")).not.toBeInTheDocument();
    expect(screen.queryByText("근거 불일치")).not.toBeInTheDocument();
    expect(screen.queryByText("규칙 기반 결과 — 모델 미사용")).not.toBeInTheDocument();
  });

  it("진료(이력)가 바뀌면 이전 진료의 AI 추천 패널·배지가 사라진다", async () => {
    mockJobWithBadges("job-reset-history", 10);

    const { rerender } = render(
      <MedicalSelectionProvider>
        <Diagnosis
          clinicVisit={{ patientId: 1, deptId: 1, historyId: 10 }}
          ensureHistory={async () => 10}
          employeeId={1}
        />
      </MedicalSelectionProvider>
    );
    fireEvent.click(screen.getByRole("button", { name: "AI 처방 추천" }));

    await screen.findByRole("dialog");
    fireEvent.click(screen.getByRole("button", { name: "확인" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

    expect(screen.getByText("근거 불일치")).toBeInTheDocument();
    expect(screen.getByText("규칙 기반 결과 — 모델 미사용")).toBeInTheDocument();
    expect(screen.getByText("AI 추천 처방")).toBeInTheDocument();

    rerender(
      <MedicalSelectionProvider>
        <Diagnosis
          clinicVisit={{ patientId: 1, deptId: 1, historyId: 20 }}
          ensureHistory={async () => 10}
          employeeId={1}
        />
      </MedicalSelectionProvider>
    );

    expect(screen.queryByText("AI 추천 처방")).not.toBeInTheDocument();
    expect(screen.queryByText("근거 불일치")).not.toBeInTheDocument();
    expect(screen.queryByText("규칙 기반 결과 — 모델 미사용")).not.toBeInTheDocument();
  });
});

// F-H3: "AI 추천 처방" 패널의 모델 출처 배지는 그 표 안의 처방을 실제로 만든
// 서비스(prescription-api)의 llmStatus 를 읽어야 한다. 응답 최상위 llmStatus 는
// validation-agent 가 자기 검증 결정을 어떻게 냈는지이지, 표에 있는 처방이
// 어디서 나왔는지가 아니다 — 그 둘을 섞으면 prescription-api 가 스텁인데도
// validation-agent 가 real 이라는 이유로 배지가 사라진다(라이브 재현됨).
//
// 바로 아래 검증 축(prescriptionVerification)은 이미 이 구분을 지키고 있었다.
// 같은 블록에서 모델 출처 축만 구분되지 않았다.
describe("처방 패널 모델 배지는 prescription-api 의 llmStatus 를 읽는다", () => {
  const clinicVisit = { patientId: 1, deptId: 1 };

  function renderDiagnosis() {
    return render(
      <MedicalSelectionProvider>
        <Diagnosis clinicVisit={clinicVisit} ensureHistory={async () => 10} employeeId={1} />
      </MedicalSelectionProvider>
    );
  }

  function mockJob(
    jobId: string,
    llmStatus: string,
    prescriptionLlmStatus: string | null | undefined
  ) {
    mockedRecommend.mockResolvedValue({ jobId, historyId: 10, status: "RUNNING" });
    mockedGetJob.mockResolvedValue({
      jobId,
      historyId: 10,
      status: "DONE",
      result: {
        overallStatus: "PASS",
        summary: "이상 없음",
        llmStatus,
        prescriptionLlmStatus,
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
    } as unknown as ValidationJobResponse);
  }

  // 모달을 닫아야 패널만 남는다 — 같은 문구가 모달에도 뜰 수 있어 스코프를 분리한다.
  async function openThenClosePanel() {
    fireEvent.click(screen.getByRole("button", { name: "AI 처방 추천" }));
    await screen.findByRole("dialog");
    fireEvent.click(screen.getByRole("button", { name: "확인" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  }

  it("validation-agent 가 real 이어도 처방 RAG 가 stub 이면 패널에 스텁 배지가 뜬다", async () => {
    // F-H3 의 라이브 재현 상태 그대로다: 최상위 real, 처방 RAG stub.
    mockJob("job-fh3-1", "real", "stub");

    renderDiagnosis();
    await openThenClosePanel();

    const badge = screen.getByText("스텁 응답 (모델 미사용)");
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveAttribute("data-tone", "neutral");
  });

  it("처방 RAG 가 real 이면 최상위가 stub 이어도 패널에는 배지가 없다", async () => {
    // 반대 방향도 고정한다. 이 단언이 없으면 "항상 배지를 띄운다"는 구현으로도
    // 위 테스트가 통과해버린다.
    mockJob("job-fh3-2", "stub", "real");

    renderDiagnosis();
    await openThenClosePanel();

    expect(screen.getByText("AI 추천 처방")).toBeInTheDocument();
    expect(screen.queryByText("스텁 응답 (모델 미사용)")).toBeNull();
    expect(screen.queryByText(/모델 미사용/)).toBeNull();
    expect(screen.queryByText("모델 출처 미확인")).toBeNull();
  });

  it("처방 RAG 의 llmStatus 가 없으면 미확인 배지가 뜬다", async () => {
    // GC-3: 필드가 없다는 것은 "모델이 돌았다"도 "규칙으로 만들었다"도 아니다.
    // 둘 중 아무거나로 말하면 확립되지 않은 것을 주장하게 된다(GC-2).
    mockJob("job-fh3-3", "real", undefined);

    renderDiagnosis();
    await openThenClosePanel();

    const badge = screen.getByText("모델 출처 미확인");
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveAttribute("data-tone", "warning");
  });
});

describe("신기능 금기 관문 표시", () => {
  const clinicVisit = { patientId: 1, deptId: 1 };

  function renderDiagnosis() {
    return render(
      <MedicalSelectionProvider>
        <Diagnosis clinicVisit={clinicVisit} ensureHistory={async () => 10} employeeId={1} />
      </MedicalSelectionProvider>
    );
  }

  function mockJobWithRenalGate(jobId: string, prescriptionRenalGate: unknown) {
    mockedRecommend.mockResolvedValue({ jobId, historyId: 10, status: "RUNNING" });
    mockedGetJob.mockResolvedValue({
      jobId,
      historyId: 10,
      status: "DONE",
      result: {
        overallStatus: "PASS",
        summary: "이상 없음",
        llmStatus: "real",
        prescriptionLlmStatus: "real",
        prescriptionVerification: {
          status: "passed",
          checks: [
            { id: "code_in_candidates", target: "prescription[1]", outcome: "ok", evidence: "" },
            { id: "name_matches_code", target: "prescription[1]", outcome: "ok", evidence: "" },
          ],
        },
        prescriptionRenalGate,
        recommendedPrescriptions: [
          {
            id: 1,
            rank: 1,
            prescription_code: "641600390",
            prescription_name: "다이아벡스정500mg",
            reason: "",
            confidence_score: 0.9,
            dose: 1,
            time: 1,
            days: 1,
          },
        ],
      },
    } as unknown as ValidationJobResponse);
  }

  const WARN_GATE = {
    status: "warn",
    renalStatus: "impaired",
    renalEvidence: "GFR 13",
    undeterminedReason: null,
    items: [
      {
        rank: 1,
        name: "다이아벡스정500mg",
        prescriptionCode: "641600390",
        outcome: "warn",
        ingredient: "메트포르민",
        evidence: "메트포르민: 젖산산증 위험. 특이사항에서 확인된 신기능 지표: GFR 13",
      },
    ],
  };

  it("warn 이면 배너와 행 배지가 함께 뜬다", async () => {
    mockJobWithRenalGate("job-r-1", WARN_GATE);

    renderDiagnosis();
    fireEvent.click(screen.getByRole("button", { name: "AI 처방 추천" }));

    expect(await screen.findByText("신배설 금기 경고")).toBeInTheDocument();
    // 환자 축이 판정과 별도로 보여야 한다.
    expect(screen.getByText(/신기능 저하 확인/)).toBeInTheDocument();
    // 항목 evidence 가 표의 범위를 들고 다닌다 — 요약해서 버리면 안 된다.
    expect(screen.getByText(/젖산산증/)).toBeInTheDocument();

    const table = await screen.findByRole("table");
    expect(within(table).getByText("신배설 금기")).toBeInTheDocument();
  });

  it("clear 라도 신기능 미확정이면 배너가 사라지지 않는다", async () => {
    mockJobWithRenalGate("job-r-2", {
      status: "clear",
      renalStatus: "undetermined",
      renalEvidence: "",
      undeterminedReason: "노트에 신기능 지표가 없습니다",
      items: [
        {
          rank: 1,
          name: "다이아벡스정500mg",
          prescriptionCode: "641600390",
          outcome: "clear",
          ingredient: null,
          evidence: "신배설 금기 표(11개 성분)에 없는 성분입니다 — 이 표의 범위 안에서 해당 없음.",
        },
      ],
    });

    renderDiagnosis();
    fireEvent.click(screen.getByRole("button", { name: "AI 처방 추천" }));

    expect(await screen.findByText("신배설 금기 표 범위 밖")).toBeInTheDocument();
    expect(screen.getByText(/신기능 미확정/)).toBeInTheDocument();
    expect(screen.getByText(/노트에 신기능 지표가 없습니다/)).toBeInTheDocument();
    // clear 항목에는 행 배지를 붙이지 않는다 — 범위 한정은 배너가 들고 있다.
    const table = await screen.findByRole("table");
    expect(within(table).queryByText("신배설 금기")).not.toBeInTheDocument();
  });

  it("관문 결과가 없으면 '해당 없음'이 아니라 미확인으로 표시한다", async () => {
    mockJobWithRenalGate("job-r-3", undefined);

    renderDiagnosis();
    fireEvent.click(screen.getByRole("button", { name: "AI 처방 추천" }));

    expect(await screen.findByText("신기능 관문 미확인")).toBeInTheDocument();
    const table = await screen.findByRole("table");
    expect(within(table).getByText("신기능 미확인")).toBeInTheDocument();
  });

  it("처방을 스왑하면 그 행의 관문 판정이 무효가 된다", async () => {
    // 관문은 스왑되기 전 약을 대조했다. 스왑 후에도 옛 warn/clear 가 남으면
    // 금기 약으로 바꿔 넣어도 화면이 옛 판정을 그대로 보여준다.
    mockJobWithRenalGate("job-r-4", {
      ...WARN_GATE,
      status: "clear",
      items: [{ ...WARN_GATE.items[0], outcome: "clear", evidence: "표 밖 성분입니다." }],
    });
    mockedSearch.mockResolvedValue({
      items: [{ id: 99, code: "999999999", name: "다른약", dose: 1, time: 1, days: 1 }],
      total: 1,
      page: 0,
      pageSize: 20,
    });

    renderDiagnosis();
    fireEvent.click(screen.getByRole("button", { name: "AI 처방 추천" }));

    const dialog = await screen.findByRole("dialog", { name: "검증 완료" });
    fireEvent.click(within(dialog).getByRole("button", { name: "확인" }));
    await waitFor(() =>
      expect(screen.queryByRole("dialog", { name: "검증 완료" })).not.toBeInTheDocument()
    );

    // 스왑 전: clear 라 행 배지가 없다.
    expect(screen.queryByText("신기능 미확인")).not.toBeInTheDocument();

    fireEvent.click(screen.getAllByRole("button", { name: "처방 상세 선택" })[0]);
    const picker = await screen.findByRole("dialog", { name: "처방 상세 선택" });
    fireEvent.click(await within(picker).findByRole("button", { name: "선택" }));
    await waitFor(() =>
      expect(screen.queryByRole("dialog", { name: "처방 상세 선택" })).not.toBeInTheDocument()
    );

    // 스왑 후: 그 행의 관문 판정은 무효다.
    expect(screen.getByText(/다른약/)).toBeInTheDocument();
    expect(await screen.findByText("신기능 미확인")).toBeInTheDocument();
  });
});
