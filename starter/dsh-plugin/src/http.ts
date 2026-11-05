/**
 * Sidecar HTTP 客户端：只做转发与错误映射，不在这里实现业务逻辑。
 * 超时由 AbortController 控制；错误统一映射为 {code, message, retryable, fallback}。
 */
import { ToolInvocationError } from "./sdk";

export interface HttpConfig {
  baseUrl: string;
  fetchImpl: typeof fetch;
  mode: "mock" | "live";
}

const defaultConfig: HttpConfig = {
  baseUrl: process.env.SIDECAR_BASE_URL ?? "http://localhost:8000",
  fetchImpl: ((...args: Parameters<typeof fetch>) => fetch(...args)) as typeof fetch,
  mode: process.env.APP_MODE === "live" ? "live" : "mock",
};

let config: HttpConfig = { ...defaultConfig };

/** 测试用：注入假的 fetch，避免真的起服务。 */
export function configureHttp(next: Partial<HttpConfig>): void {
  config = { ...config, ...next };
}

export function httpConfig(): HttpConfig {
  return { ...config };
}

function parseErrorBody(body: unknown): { code: string; message: string; retryable: boolean; fallback: string } | null {
  if (typeof body !== "object" || body === null) return null;
  const record = body as Record<string, unknown>;
  const error = record.error;
  if (typeof error !== "object" || error === null) return null;
  const e = error as Record<string, unknown>;
  if (typeof e.code !== "string" || typeof e.message !== "string") return null;
  return {
    code: e.code,
    message: e.message,
    retryable: Boolean(e.retryable),
    fallback: typeof e.fallback === "string" ? e.fallback : "",
  };
}

export async function callSidecar<T>(
  path: string,
  payload: unknown,
  signal?: AbortSignal,
  init?: RequestInit,
): Promise<T> {
  let response: Response;
  try {
    response = await config.fetchImpl(`${config.baseUrl.replace(/\/$/, "")}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload ?? {}),
      signal,
      ...init,
    });
  } catch (error) {
    if (signal?.aborted) {
      throw new ToolInvocationError({
        code: "TIMEOUT",
        message: "请求已中止（超时或用户取消）。",
        retryable: true,
        fallback: "",
      });
    }
    throw new ToolInvocationError({
      code: "UPSTREAM_ERROR",
      message: `sidecar 不可达（${config.baseUrl}）。请确认本地服务已启动：docker compose -f starter/docker-compose.yml up，或 uvicorn app.main:app --port 8000。`,
      retryable: true,
      fallback: "",
    });
  }

  const text = await response.text();
  let body: unknown = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = null;
  }

  if (!response.ok) {
    const parsed = parseErrorBody(body);
    if (parsed) throw new ToolInvocationError({ ...parsed, detail: { status: response.status } });
    throw new ToolInvocationError({
      code: "UPSTREAM_ERROR",
      message: `sidecar 返回 ${response.status}，且响应不是标准错误契约。`,
      retryable: response.status >= 500,
      fallback: "",
    });
  }
  return body as T;
}

export async function uploadFile<T>(
  path: string,
  filePath: string,
  fields: Record<string, string>,
  signal?: AbortSignal,
): Promise<T> {
  const { readFile } = await import("node:fs/promises");
  const { basename } = await import("node:path");
  const buffer = await readFile(filePath);
  const form = new FormData();
  form.append("file", new Blob([buffer]), basename(filePath));
  for (const [key, value] of Object.entries(fields)) form.append(key, value);

  const response = await config.fetchImpl(`${config.baseUrl.replace(/\/$/, "")}${path}`, {
    method: "POST",
    body: form,
    signal,
  });
  const text = await response.text();
  const body = text ? JSON.parse(text) : null;
  if (!response.ok) {
    const parsed = parseErrorBody(body);
    throw new ToolInvocationError(
      parsed
        ? { ...parsed, detail: { status: response.status } }
        : { code: "UPSTREAM_ERROR", message: `上传失败：${response.status}`, retryable: true, fallback: "" },
    );
  }
  return body as T;
}
