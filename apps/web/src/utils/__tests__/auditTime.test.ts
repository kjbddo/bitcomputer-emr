import { describe, expect, it } from "vitest";

import {
  formatLocalTimestamp,
  localDayEndToUtcParam,
  localDayStartToUtcParam,
  parseOccurredAtUtc,
} from "../auditTime";

const KST_OFFSET_MINUTES = 540; // UTC+9

// I2 회귀: 서버는 UTC-naive LocalDateTime 을 저장한다. 이 테스트들은 모두
// offsetMinutes 를 명시적으로 넘겨 시간대를 고정한다 - 테스트를 실행하는
// 머신/CI 의 실제 시스템 시간대(ambient TZ)에 기대지 않는다. 그래서 CI 가
// UTC 로 돌든 KST 로 돌든 결과가 달라지지 않는다.
describe("parseOccurredAtUtc", () => {
  it("서버 문자열을 UTC 시각으로 해석한다(Z 를 붙여 파싱)", () => {
    const parsed = parseOccurredAtUtc("2026-08-28T01:11:49");
    expect(parsed.toISOString()).toBe("2026-08-28T01:11:49.000Z");
  });
});

describe("formatLocalTimestamp", () => {
  it("KST(+540)에서는 UTC 보다 9시간 늦은 벽시계로 표시한다", () => {
    // 측정값: occurredAt "2026-08-28T01:11:49" 일 때 KST 로는 10:11:49 여야 한다.
    expect(formatLocalTimestamp("2026-08-28T01:11:49", KST_OFFSET_MINUTES)).toBe(
      "2026-08-28 10:11:49"
    );
  });

  it("UTC(0)에서는 원본 벽시계와 같다", () => {
    expect(formatLocalTimestamp("2026-08-28T01:11:49", 0)).toBe("2026-08-28 01:11:49");
  });

  it("음수 오프셋(UTC-8, 예: PST)에서는 날짜가 전날로 넘어갈 수 있다", () => {
    expect(formatLocalTimestamp("2026-08-28T01:11:49", -480)).toBe("2026-08-27 17:11:49");
  });

  it("KST 자정 근처는 날짜가 다음날로 넘어간다", () => {
    // UTC 2026-08-27T16:00:00 은 KST 로 2026-08-28T01:00:00.
    expect(formatLocalTimestamp("2026-08-27T16:00:00", KST_OFFSET_MINUTES)).toBe(
      "2026-08-28 01:00:00"
    );
  });
});

describe("localDayStartToUtcParam / localDayEndToUtcParam", () => {
  it("KST 오늘 하루(00:00~23:59:59)는 UTC 로 전날 15:00~당일 14:59:59 다", () => {
    // 이게 I2 의 핵심 회귀다: 변환 없이 그냥 "yyyy-MM-ddT00:00:00" 을 보내면
    // KST 00:00~09:00 의 이벤트가 필터에서 빠진다.
    expect(localDayStartToUtcParam("2026-08-28", KST_OFFSET_MINUTES)).toBe(
      "2026-08-27T15:00:00"
    );
    expect(localDayEndToUtcParam("2026-08-28", KST_OFFSET_MINUTES)).toBe(
      "2026-08-28T14:59:59"
    );
  });

  it("UTC(0)에서는 그대로 변환 없이 나온다", () => {
    expect(localDayStartToUtcParam("2026-08-28", 0)).toBe("2026-08-28T00:00:00");
    expect(localDayEndToUtcParam("2026-08-28", 0)).toBe("2026-08-28T23:59:59");
  });

  it("양수 오프셋에서 자정 경계가 전날로 넘어가는 월말/월초도 올바르게 넘어간다", () => {
    // KST 2026-09-01T00:00:00 -> UTC 2026-08-31T15:00:00 (월이 바뀌는 경계).
    expect(localDayStartToUtcParam("2026-09-01", KST_OFFSET_MINUTES)).toBe(
      "2026-08-31T15:00:00"
    );
  });
});
