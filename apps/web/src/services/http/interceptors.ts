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
      const message =
        detailStr ||
        (body?.message != null ? String(body.message) : "") ||
        error.message ||
        "HTTP Error";

      if (status === 401 && typeof window !== "undefined") {
        window.location.href = "/login";
      }

      throw new HttpError(message, status, data);
    }
  );
}
