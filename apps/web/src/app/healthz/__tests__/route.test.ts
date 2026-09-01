import { describe, expect, it } from "vitest";

import { GET, dynamic } from "../route";

// 이 라우트는 쿠버네티스 readinessProbe 가 부를 자리다. 지켜야 할 성질이 셋이고,
// 셋 다 "없어도 겉보기에는 멀쩡한" 종류라 테스트가 아니면 드러나지 않는다.
describe("GET /healthz", () => {
  it("200 과 상태 본문을 돌려준다", async () => {
    const response = GET();

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({ status: "ok" });
  });

  it("정적으로 최적화되지 않는다", () => {
    // force-dynamic 이 없으면 Next 가 빌드 시점에 응답을 굳혀 캐시할 수 있다.
    // 그러면 프로세스가 죽어가는 중에도 캐시된 200 이 나가고, 프로브는 그것을
    // "살아 있다" 로 읽는다.
    expect(dynamic).toBe("force-dynamic");
  });

  it("상류를 확인하지 않는다", () => {
    // 프로브가 Spring·DB 를 확인하면 상류 장애가 이 파드의 재시작으로 번진다.
    // 상류가 돌아와도 이쪽이 재시작 루프에 빠져 있을 수 있다.
    //
    // 함수 본문에 네트워크 호출이 없다는 것으로 고정한다 — 나중에 누가
    // "이왕이면 DB도 확인하자" 로 고치면 여기서 걸린다.
    const source = GET.toString();
    expect(source).not.toMatch(/fetch|axios|http/i);
  });
});
