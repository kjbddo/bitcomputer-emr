export interface HttpClientOptions {
  baseURL?: string;
  timeoutMs?: number;
}

export interface ErrorResponseBody {
  message?: string;
  [key: string]: unknown;
}

export class HttpError extends Error {
  public readonly status: number;
  public readonly data?: unknown;

  constructor(message: string, status: number, data?: unknown) {
    super(message);
    this.name = "HttpError";
    this.status = status;
    this.data = data;
  }
}


