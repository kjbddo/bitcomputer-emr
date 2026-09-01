import axios, { type AxiosInstance, type AxiosRequestConfig } from "axios";
import { attachInterceptors } from "./interceptors";
import type { HttpClientOptions } from "./types";

let sharedInstance: AxiosInstance | null = null;
let interceptorsAttached = false;

function createInstance(options?: HttpClientOptions): AxiosInstance {
  // 상대 경로다. 절대 주소를 쓰지 않는다.
  //
  // 예전에는 `NEXT_PUBLIC_API_BASE_URL` 로 API 주소를 받았다. 그 값은
  // **빌드 시점에 번들에 박히므로** 도메인마다 프론트 이미지를 따로 구워야 했다 —
  // AWS 용, DR 용, 로컬용이 각각 다른 이미지가 된다.
  //
  // 빈 baseURL 은 요청을 현재 오리진으로 보낸다. 프론트와 API 를 같은 호스트명
  // 아래 두는 것이 그 전제이고, 배포에서는 CloudFront 가(`/*` 프론트, `/api/*`
  // Spring), 로컬에서는 next.config 의 rewrite 가 그 조건을 만든다.
  //
  // **GCP DR 도 같은 조건을 지켜야 한다.** 프론트와 API 를 다른 호스트에 두면
  // 이 한 줄 때문에 프론트 이미지가 다시 갈라진다.
  const baseURL = options?.baseURL ?? "";
  const timeout = options?.timeoutMs ?? 15000;

  const instance = axios.create({
    baseURL,
    timeout,
    withCredentials: true,
    withXSRFToken: true,
    xsrfCookieName: "XSRF-TOKEN",
    xsrfHeaderName: "X-XSRF-TOKEN",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
  });

  // 인터셉터는 한 번만 추가한다
  if (!interceptorsAttached) {
    attachInterceptors(instance);
    interceptorsAttached = true;
  }
  return instance;
}

export function http(options?: HttpClientOptions): AxiosInstance {
  if (!sharedInstance) {
    sharedInstance = createInstance(options);
  }
  return sharedInstance;
}

// Convenience helpers with typed responses
export async function get<T = unknown>(url: string, config?: AxiosRequestConfig): Promise<T> {
  const res = await http().get<T>(url, config);
  return res.data;
}

export async function post<T = unknown, B = unknown>(
  url: string,
  body?: B,
  config?: AxiosRequestConfig
): Promise<T> {
  const res = await http().post<T>(url, body, config);
  return res.data;
}

export async function put<T = unknown, B = unknown>(
  url: string,
  body?: B,
  config?: AxiosRequestConfig
): Promise<T> {
  const res = await http().put<T>(url, body, config);
  return res.data;
}

export async function del<T = unknown>(url: string, config?: AxiosRequestConfig): Promise<T> {
  const res = await http().delete<T>(url, config);
  return res.data;
}


