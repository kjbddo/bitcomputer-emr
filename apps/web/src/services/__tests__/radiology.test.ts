import { describe, expect, it } from "vitest";

import { RADIOLOGY_ANALYZE_TIMEOUT_MS } from "../radiology";

// http/client.ts 의 기본 타임아웃. X-ray 업로드가 이 값을 그대로 쓰고 있었고,
// 추론 시간이 그 바로 아래라 같은 영상이라도 어떤 요청은 통과하고 어떤 요청은
// 타임아웃났다.
const HTTP_CLIENT_DEFAULT_TIMEOUT_MS = 15000;

// apps/api/src/main/resources/application.properties 의
// http.client.rest-template.read-timeout-ms. 값을 나란히 두어 어느 쪽을 바꾸든
// 관계가 깨지면 이 테스트가 즉시 실패하게 한다.
const JAVA_REST_TEMPLATE_READ_TIMEOUT_MS = 180000;

// 컨테이너 안에서 실측한 추론 시간(2026-08-31, CPU 14코어):
//   SQUID 이상탐지 ~4초 + DenseNet 임베딩 ~8초 + 나머지 ~0.3초 = 10~15초
const MEASURED_INFERENCE_MS = 15000;

describe("RADIOLOGY_ANALYZE_TIMEOUT_MS", () => {
  it("실측 추론 시간보다 충분히 커야 한다", () => {
    // 실측 상한과 같거나 작으면, 서버가 정상 처리 중인데도 브라우저가 먼저
    // 포기해 사용자에게는 분석 실패로 보인다. 여유를 두지 않으면 CPU 부하가
    // 조금만 늘어도 다시 경계에 걸린다.
    expect(RADIOLOGY_ANALYZE_TIMEOUT_MS).toBeGreaterThanOrEqual(MEASURED_INFERENCE_MS * 2);
  });

  it("http 클라이언트 기본값을 그대로 쓰지 않는다", () => {
    // 이 단언이 깨진다는 것은 명시 타임아웃이 지워져 기본값으로 돌아갔다는
    // 뜻이다 — 원래 결함의 정확한 형태다.
    expect(RADIOLOGY_ANALYZE_TIMEOUT_MS).not.toBe(HTTP_CLIENT_DEFAULT_TIMEOUT_MS);
  });

  it("Java RestTemplate read-timeout-ms 보다 작아야 한다", () => {
    // 이쪽이 더 크면 Java 가 이미 포기한 요청을 브라우저가 계속 기다린다.
    // 문서 생성 경로(DOCUMENT_API_TIMEOUT_MS)와 방향이 반대인데, 그쪽은 Java 를
    // 거쳐 게이트웨이까지 가는 긴 경로라 브라우저가 더 오래 기다려야 하고,
    // 이쪽은 Java 안에서 끝나는 호출이라 Java 가 상한을 쥔다.
    expect(RADIOLOGY_ANALYZE_TIMEOUT_MS).toBeLessThan(JAVA_REST_TEMPLATE_READ_TIMEOUT_MS);
  });
});
