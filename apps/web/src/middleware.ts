import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

/**
 * 낙관적 리다이렉트.
 *
 * 쿠키 "존재"만 확인하며 서명을 검증하지 않는다. 이것은 UX 장치이지 방어
 * 계층이 아니다 — 임의의 쿠키를 심으면 통과한다. 실제 권한 판정은 서버
 * (SecurityConfig)에서만 이뤄지며, 권한 없는 요청은 401/403 으로 막힌다.
 */
export function middleware(request: NextRequest) {
  const token = request.cookies.get("access_token")?.value;
  const url = request.nextUrl;

  if (url.pathname === "/") {
    const target = token ? "/dashboard" : "/login";
    return NextResponse.redirect(new URL(target, url));
  }

  if (url.pathname.startsWith("/dashboard")) {
    if (!token) {
      return NextResponse.redirect(new URL("/login", url));
    }
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/", "/dashboard/:path*"],
};


