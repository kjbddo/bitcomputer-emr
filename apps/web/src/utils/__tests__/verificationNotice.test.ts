import { describe, expect, it } from "vitest";
import { itemVerificationOutcome, verificationNotice } from "../verificationNotice";

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
      { id: "dosage_verbatim", target: "prescription[2]", outcome: "flagged", evidence: "" },
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
});
