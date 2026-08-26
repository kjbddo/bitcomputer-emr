/**
 * 인증 토큰은 서버가 HttpOnly 쿠키로 관리한다.
 *
 * JS 에서 토큰 값을 읽거나 저장하지 않는다 — XSS 로 탈취되는 경로를 막기
 * 위해서다. 로그인 여부 판정은 서버 응답(401)으로 한다.
 */

/** 서버 로그아웃 후 클라이언트 상태를 비운다. 쿠키 삭제는 서버가 한다. */
export function clearClientAuthState(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem("access_token");
    window.localStorage.removeItem("refresh_token");
  } catch {
    // storage 접근 실패는 무시한다
  }
}
