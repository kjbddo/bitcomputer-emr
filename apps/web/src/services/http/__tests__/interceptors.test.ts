import axios, { type AxiosError, type AxiosInstance } from "axios";
import { describe, expect, it } from "vitest";

import { attachInterceptors } from "../interceptors";
import { HttpError } from "../types";

// axios 는 등록된 인터셉터를 공식 타입으로 노출하지 않는다. interceptors.response
// 내부의 handlers 배열({fulfilled, rejected})에 직접 접근해 rejected 핸들러만
// 떼어내 호출한다 - 실제 axios 요청/네트워크 없이 인터셉터 로직만 단위 테스트한다.
function getRejectedHandler(instance: AxiosInstance): (error: AxiosError) => never {
  const handlers = (instance.interceptors.response as unknown as {
    handlers: Array<{ rejected: (error: AxiosError) => never }>;
  }).handlers;
  return handlers[0].rejected;
}

function makeInstance(): AxiosInstance {
  const instance = axios.create();
  attachInterceptors(instance);
  return instance;
}

function makeError(status: number, data: unknown, message = "Request failed"): AxiosError {
  return {
    response: { status, data, statusText: "", headers: {}, config: {} as never },
    message,
    isAxiosError: true,
    toJSON: () => ({}),
    name: "AxiosError",
  } as unknown as AxiosError;
}

describe("attachInterceptors - 에러 메시지 추출", () => {
  // I3: GlobalExceptionHandler 의 모든 핸들러가 ResponseEntity<String> 을 반환해
  // 에러 본문이 text/plain 문자열로 온다. 이 분기가 없으면 서버가 고른 구체적인
  // 한글 메시지 대신 axios 의 영어 일반 메시지로 대체된다.
  it("문자열(text/plain) 에러 본문을 메시지로 사용한다", () => {
    const rejected = getRejectedHandler(makeInstance());
    const error = makeError(409, "이미 존재하는 부서명입니다: 내과");

    expect(() => rejected(error)).toThrow(HttpError);
    try {
      rejected(error);
    } catch (err) {
      expect(err).toBeInstanceOf(HttpError);
      expect((err as HttpError).message).toBe("이미 존재하는 부서명입니다: 내과");
      expect((err as HttpError).status).toBe(409);
    }
  });

  it("앞뒤 공백만 있는 문자열 본문은 무시하고 axios 기본 메시지로 폴백한다", () => {
    const rejected = getRejectedHandler(makeInstance());
    const error = makeError(500, "   ", "Request failed with status code 500");

    try {
      rejected(error);
      expect.unreachable();
    } catch (err) {
      expect((err as HttpError).message).toBe("Request failed with status code 500");
    }
  });

  it("object 본문의 message 필드는 기존대로 우선 사용한다(회귀 방지)", () => {
    const rejected = getRejectedHandler(makeInstance());
    const error = makeError(400, { message: "잘못된 요청입니다" });

    try {
      rejected(error);
      expect.unreachable();
    } catch (err) {
      expect((err as HttpError).message).toBe("잘못된 요청입니다");
    }
  });

  it("object 본문의 detail 필드는 message 보다 우선한다(회귀 방지)", () => {
    const rejected = getRejectedHandler(makeInstance());
    const error = makeError(422, { detail: "세부 사유", message: "무시되어야 함" });

    try {
      rejected(error);
      expect.unreachable();
    } catch (err) {
      expect((err as HttpError).message).toBe("세부 사유");
    }
  });
});
