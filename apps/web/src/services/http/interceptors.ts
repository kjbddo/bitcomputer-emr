import type { AxiosInstance, AxiosError } from "axios";
import { HttpError } from "./types";

/**
 * 인증은 HttpOnly 쿠키(withCredentials)로 전달되므로 Authorization 헤더를
 * 붙이지 않는다. CSRF 토큰은 axios 의 xsrfCookieName/xsrfHeaderName 설정이
 * 자동으로 처리한다.
 */
export function attachInterceptors(instance: AxiosInstance): void {
  instance.interceptors.response.use(
    (response) => response,
    (error: AxiosError) => {
      const status = error.response?.status ?? 0;
      const data = error.response?.data as unknown;
      const body = typeof data === "object" && data !== null ? (data as Record<string, unknown>) : null;
      const detail = body?.detail;
      const detailStr =
        typeof detail === "string"
          ? detail
          : Array.isArray(detail)
            ? detail
                .map((x) =>
                  typeof x === "object" && x && "msg" in x ? String((x as { msg: unknown }).msg) : String(x)
                )
                .join("; ")
            : "";
      // I3: GlobalExceptionHandler 의 모든 핸들러가 ResponseEntity<String> 을
      // 반환해, 에러 응답 본문이 text/plain 문자열이다("이미 존재하는
      // 부서명입니다: 내과" 등). data 가 object 가 아니면 이 문자열이
      // 그대로 온다 - 위의 object 전용 처리만으로는 항상 body 가 null 이
      // 되어 서버가 고른 구체적인 한글 메시지가 버려지고 axios 의 영어
      // 일반 메시지("Request failed with status code 409")로 대체됐다.
      const stringBody = typeof data === "string" ? data.trim() : "";
      const message =
        detailStr ||
        (body?.message != null ? String(body.message) : "") ||
        stringBody ||
        error.message ||
        "HTTP Error";

      if (status === 401 && typeof window !== "undefined") {
        window.location.href = "/login";
      }

      throw new HttpError(message, status, data);
    }
  );
}
