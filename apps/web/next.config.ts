import type { NextConfig } from "next";

/**
 * `/api/*` 의 목적지. 어느 환경에서나 같은 값이다.
 *
 * **환경변수로 받지 않는다.** `rewrites()` 는 `next build` 때 한 번 평가돼
 * `.next/routes-manifest.json` 에 구워진다 — `next start` 는 그 파일을 읽을 뿐
 * 다시 평가하지 않는다. 그래서 기동 환경변수로는 바뀌지 않고, 빌드 인자로 받으면
 * 값이 다른 만큼 이미지가 갈라진다. 그걸 없애려고 이 구조를 만들었으므로 여기에
 * 환경 의존을 다시 들이지 않는다.
 *
 * 값을 고정할 수 있는 이유는 이름을 우리가 정하기 때문이다. compose 서비스
 * 이름과 쿠버네티스 Service 이름을 양쪽 다 `spring-boot` 으로 둔다.
 *
 * **쿠버네티스 Service 이름을 바꾸면 이 값도 함께 바꿔야 한다.** 다만 배포에서
 * `/api/*` 는 ALB 가 Spring 으로 보내므로 프론트 파드에 닿지 않는다 — 어긋나도
 * 평소에는 드러나지 않고, ALB 라우팅이 빠진 날에만 드러난다.
 */
const API_UPSTREAM = "http://spring-boot:8080";

const nextConfig: NextConfig = {
  /**
   * 브라우저가 API 를 **상대 경로**로 부르게 하기 위한 장치다.
   *
   * 절대 주소를 쓰면 도메인마다 프론트를 다시 빌드해야 한다 — `NEXT_PUBLIC_` 값은
   * 번들에 박혀 기동 환경변수로 못 바꾸기 때문이다. 상대 경로는 프론트와 API 가
   * 같은 오리진일 때만 성립하고, 배포에서는 CloudFront 가 `/*` 를 프론트로
   * `/api/*` 를 Spring 으로 보내 그 조건을 만든다. 로컬 compose 에는 그 앞단이
   * 없어 3000 과 8080 이 다른 오리진이므로, 이 rewrite 가 대신한다.
   *
   * **`beforeFiles` 다.** 배포에서 ALB 는 `/api/*` 를 조건 없이 Spring 으로 보낸다.
   * `afterFiles` 로 두면 `src/app/api/` 아래 라우트가 로컬에서만 프록시를 가로채,
   * 로컬에서는 동작하는데 배포에서는 닿지 않는 코드가 생긴다. 여기서도 무조건
   * 넘겨 로컬이 배포와 같은 규칙을 따르게 한다.
   *
   * 그래서 **`src/app/api/` 아래에는 라우트를 만들지 않는다.** 프론트 자신의
   * 엔드포인트는 `/api` 밖에 둔다(헬스는 `/healthz`).
   */
  async rewrites() {
    return {
      beforeFiles: [
        { source: "/api/:path*", destination: `${API_UPSTREAM}/api/:path*` },
      ],
      afterFiles: [],
      fallback: [],
    };
  },
};

export default nextConfig;
