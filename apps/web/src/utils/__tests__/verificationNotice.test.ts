import { describe, expect, it } from "vitest";
import {
  itemVerificationOutcome,
  responseVerificationOutcome,
  verificationNotice,
} from "../verificationNotice";

describe("verificationNotice", () => {
  it("passed 면 아무것도 표시하지 않는다", () => {
    expect(verificationNotice("passed")).toBeNull();
  });

  it("flagged 와 skipped 는 다른 문구를 쓴다", () => {
    const flagged = verificationNotice("flagged");
    const skipped = verificationNotice("skipped");
    expect(flagged!.label).toContain("근거 불일치");
    expect(skipped!.label).toContain("미검증");
    expect(flagged!.label).not.toBe(skipped!.label);
  });

  it("flagged 가 skipped 보다 강한 tone 을 쓴다", () => {
    expect(verificationNotice("flagged")!.tone).toBe("danger");
    expect(verificationNotice("skipped")!.tone).toBe("warning");
  });

  // fail-closed. 필드가 없는 응답을 "검증됨"으로 읽으면 이 표시가 존재할 이유가 사라진다.
  it("값이 없거나 계약 밖이면 미검증으로 본다", () => {
    expect(verificationNotice(undefined)).not.toBeNull();
    expect(verificationNotice(null)).not.toBeNull();
    expect(verificationNotice("PASSED")).not.toBeNull();
    expect(verificationNotice("bogus")).not.toBeNull();
  });
});

describe("itemVerificationOutcome", () => {
  const verification = {
    status: "flagged",
    checks: [
      { id: "code_in_candidates", target: "prescription[1]", outcome: "ok", evidence: "" },
      { id: "name_matches_code", target: "prescription[2]", outcome: "flagged", evidence: "" },
      { id: "code_in_candidates", target: "prescription[3]", outcome: "skipped", evidence: "" },
    ],
  };

  it("항목에 flagged 가 있으면 flagged", () => {
    expect(itemVerificationOutcome(verification, "prescription[2]")).toBe("flagged");
  });

  it("항목이 전부 ok 면 ok", () => {
    expect(itemVerificationOutcome(verification, "prescription[1]")).toBe("ok");
  });

  it("항목이 skipped 만 있으면 skipped", () => {
    expect(itemVerificationOutcome(verification, "prescription[3]")).toBe("skipped");
  });

  it("해당 항목의 검사가 없으면 skipped", () => {
    expect(itemVerificationOutcome(verification, "prescription[9]")).toBe("skipped");
  });

  it("verification 자체가 없으면 skipped", () => {
    expect(itemVerificationOutcome(undefined, "prescription[1]")).toBe("skipped");
  });

  // IMP-2 — confidence_in_range 는 구조 검사(STRUCTURAL_CHECK_IDS)라 조회 데이터와
  // 대조하지 않는다. code_in_candidates·name_matches_code 가 실제 후보와 대조해
  // 둘 다 ok 인데, confidence_score 가 주입되지 않아 confidence_in_range 만
  // skipped 인 경우 — 구조 검사 하나가 이미 성립한 grounding 을 혼자 뒤집으면
  // 안 된다. 상병코드를 고르기 전에 "AI 처방 추천"을 누르는 흔한 조작
  // 순서에서 실제로 발생한다(prescription_api.py:474 의 `if dx_codes:` 가드).
  it("구조 검사만 skipped 이고 근거 검사가 전부 ok 면 ok(구조 검사가 grounding 을 혼자 뒤집지 못한다)", () => {
    const verification = {
      status: "passed",
      checks: [
        { id: "code_in_candidates", target: "prescription[1]", outcome: "ok", evidence: "" },
        { id: "name_matches_code", target: "prescription[1]", outcome: "ok", evidence: "" },
        { id: "confidence_in_range", target: "prescription[1]", outcome: "skipped", evidence: "confidence_score 없음" },
      ],
    };
    expect(itemVerificationOutcome(verification, "prescription[1]")).toBe("ok");
  });

  // GC-3 는 그대로 지킨다 — 그 항목에 구조 검사만 있고 근거 검사가 하나도
  // 없으면 여전히 skipped(미검증)다. 구조 검사는 grounding 을 확립하지
  // 못한다(GC-2) — 거부권만 없앴을 뿐 발언권을 준 것이 아니다.
  it("근거 검사 없이 구조 검사만 있으면 여전히 skipped", () => {
    const verification = {
      status: "skipped",
      checks: [
        { id: "confidence_in_range", target: "prescription[1]", outcome: "ok", evidence: "confidence_score=0.5" },
      ],
    };
    expect(itemVerificationOutcome(verification, "prescription[1]")).toBe("skipped");
  });

  // 구조 검사가 진짜로 flagged(예: 범위 밖 confidence_score)면 근거 검사가
  // 전부 ok 여도 여전히 눈에 띄어야 한다 — 거부권만 없앴을 뿐 진짜 결함까지
  // 숨기면 안 된다(M1 이 응답 단위에서 지킨 것과 같은 원칙).
  it("구조 검사가 실제로 flagged 면 근거 검사가 전부 ok 여도 flagged", () => {
    const verification = {
      status: "flagged",
      checks: [
        { id: "code_in_candidates", target: "prescription[1]", outcome: "ok", evidence: "" },
        { id: "name_matches_code", target: "prescription[1]", outcome: "ok", evidence: "" },
        { id: "confidence_in_range", target: "prescription[1]", outcome: "flagged", evidence: "confidence_score=1.5 가 범위 밖" },
      ],
    };
    expect(itemVerificationOutcome(verification, "prescription[1]")).toBe("flagged");
  });

  // F-H1 — code_is_medication 은 구조 검사지만 flagged 는 반드시 화면까지 가야
  // 한다. 이 검사가 잡는 것은 "폐렴 환자에게 재진진찰료를 추천했다" 이고, 그
  // 코드는 실제로 조회된 후보에서 왔으므로 근거 검사(code_in_candidates·
  // name_matches_code)는 전부 정직하게 ok 다 — IMP-2 의 구조 검사 예외가
  // flagged 까지 삼키면 그 항목이 초록 배지로 나간다.
  it("code_is_medication 이 flagged 면 근거 검사가 전부 ok 여도 flagged", () => {
    const verification = {
      status: "flagged",
      checks: [
        { id: "code_in_candidates", target: "prescription[1]", outcome: "ok", evidence: "" },
        { id: "name_matches_code", target: "prescription[1]", outcome: "ok", evidence: "" },
        {
          id: "code_is_medication",
          target: "prescription[1]",
          outcome: "flagged",
          evidence: "코드 'AA254' 는 약제 코드 형태가 아님",
        },
      ],
    };
    expect(itemVerificationOutcome(verification, "prescription[1]")).toBe("flagged");
  });

  // 반대 방향: code_is_medication 의 ok 하나로는 grounding 이 서지 않는다.
  // 조회 데이터와 대조하지 않는 검사이기 때문이다(GC-2) — 파이썬
  // aggregate_status 와 같은 규칙이다.
  it("code_is_medication 만 ok 이고 근거 검사가 없으면 skipped", () => {
    const verification = {
      status: "skipped",
      checks: [
        { id: "code_is_medication", target: "prescription[1]", outcome: "ok", evidence: "" },
        { id: "code_in_candidates", target: "prescription[1]", outcome: "skipped", evidence: "" },
        { id: "name_matches_code", target: "prescription[1]", outcome: "skipped", evidence: "" },
      ],
    };
    expect(itemVerificationOutcome(verification, "prescription[1]")).toBe("skipped");
  });

  // M2 — fail-closed 는 verificationNotice.ts:43 에서 이미 맞게 동작하지만
  // 계약 밖 outcome 값(대소문자 오탈자 등)에 대한 고정 테스트가 없었다.
  // "ok"/"flagged" 정확 일치가 아니면 통과로 새지 않아야 한다(GC-3).
  it("계약 밖 outcome 값(대소문자 오탈자)이 섞이면 ok 로 새지 않고 skipped", () => {
    const withBogusOutcome = {
      status: "flagged",
      checks: [
        { id: "code_in_candidates", target: "prescription[5]", outcome: "OK", evidence: "" },
      ],
    };
    expect(itemVerificationOutcome(withBogusOutcome, "prescription[5]")).toBe("skipped");
  });
});

// M1 — 응답 단위 검사(target="response", 예: schema_top3)는 항목 단위 집계에
// 들어가지 않는다. 처방 화면 요약이 항목 outcome 만 세면 이 검사는 무엇을
// 보고하든 화면에 나타나지 않는다. 응답 단위 판정을 별도로 뽑아낸다.
describe("responseVerificationOutcome", () => {
  it("응답 단위 검사가 flagged 면 flagged", () => {
    expect(
      responseVerificationOutcome({
        status: "flagged",
        checks: [
          { id: "schema_top3", target: "response", outcome: "flagged", evidence: "" },
          { id: "code_in_candidates", target: "prescription[1]", outcome: "ok", evidence: "" },
        ],
      })
    ).toBe("flagged");
  });

  it("응답 단위 검사가 전부 ok 면 ok", () => {
    expect(
      responseVerificationOutcome({
        status: "passed",
        checks: [
          { id: "schema_top3", target: "response", outcome: "ok", evidence: "" },
          { id: "code_in_candidates", target: "prescription[1]", outcome: "flagged", evidence: "" },
        ],
      })
    ).toBe("ok");
  });

  // 항목 단위 판정과 뒤섞이면 안 된다. 항목이 flagged 라고 응답 단위까지
  // flagged 로 물들면 의사가 "표의 어느 행 문제인지" 와 "응답 전체 형태
  // 문제인지" 를 구분할 수 없다.
  it("항목 단위 검사만 flagged 여도 응답 단위 판정은 물들지 않는다", () => {
    expect(
      responseVerificationOutcome({
        status: "flagged",
        checks: [
          { id: "schema_top3", target: "response", outcome: "ok", evidence: "" },
          { id: "code_in_candidates", target: "prescription[1]", outcome: "flagged", evidence: "" },
        ],
      })
    ).toBe("ok");
  });

  // fail-closed(GC-3). 응답 단위 검사가 아예 없으면 "응답 단위로는 검증된 적
  // 없음" 이지 "통과" 가 아니다.
  it("응답 단위 검사가 없으면 skipped", () => {
    expect(
      responseVerificationOutcome({
        status: "passed",
        checks: [
          { id: "code_in_candidates", target: "prescription[1]", outcome: "ok", evidence: "" },
        ],
      })
    ).toBe("skipped");
  });

  it("verification 자체가 없거나 null 이면 skipped", () => {
    expect(responseVerificationOutcome(undefined)).toBe("skipped");
    expect(responseVerificationOutcome(null)).toBe("skipped");
  });

  it("checks 가 배열이 아니면 skipped", () => {
    expect(
      responseVerificationOutcome({ status: "passed", checks: null })
    ).toBe("skipped");
  });

  it("계약 밖 outcome 값은 ok 로 새지 않고 skipped", () => {
    expect(
      responseVerificationOutcome({
        status: "passed",
        checks: [{ id: "schema_top3", target: "response", outcome: "OK", evidence: "" }],
      })
    ).toBe("skipped");
  });
});
