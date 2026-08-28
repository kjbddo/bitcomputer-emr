import { describe, expect, it } from "vitest";

import { DOCUMENT_API_TIMEOUT_MS } from "../agent";

// apps/api/src/main/resources/application.properties 의
// http.client.rest-template.read-timeout-ms 값. 두 값을 나란히 두어 관계가
// 깨지면(어느 쪽을 바꾸든) 이 테스트가 즉시 실패하게 한다.
const JAVA_REST_TEMPLATE_READ_TIMEOUT_MS = 180000;

describe("DOCUMENT_API_TIMEOUT_MS", () => {
  // 최종 리뷰 IMPORTANT: 브라우저가 Java 보다 먼저 포기하면 안 된다 — 그러면
  // Java/게이트웨이가 아직 정상 처리 중인 요청도 사용자에게는 실패로 보인다.
  it("Java RestTemplate read-timeout-ms 보다 커야 한다", () => {
    expect(DOCUMENT_API_TIMEOUT_MS).toBeGreaterThan(JAVA_REST_TEMPLATE_READ_TIMEOUT_MS);
  });
});
