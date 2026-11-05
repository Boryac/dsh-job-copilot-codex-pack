/**
 * DSH 工具声明层。
 *
 * 本文件实现的是本包约定的 DSH `defineTool` 表面契约：
 *   - 声明 parameters（含类型/必填/枚举）
 *   - 声明 timeoutMs
 *   - execute 返回 canonical 值
 * docs/ENVIRONMENT.md 第 1 节明确要求"不硬编码 SDK 内部 API"，因此这里只依赖这层语义。
 * 接入真实 SDK 时，只需把 defineTool 换成 SDK 的实现（或加一层适配），工具实现不用改。
 *
 * A1 的验证方式：tsc 类型检查 + tests/tools.test.ts 对参数校验、超时、错误映射做断言。
 */

export type ParamType = "string" | "number" | "boolean" | "object" | "array";

export interface ToolParameter {
  type: ParamType;
  description: string;
  required?: boolean;
  enum?: readonly string[];
  default?: unknown;
}

export interface ToolErrorPayload {
  code: string;
  message: string;
  retryable: boolean;
  fallback: string;
  detail?: Record<string, unknown>;
}

export class ToolInvocationError extends Error {
  readonly payload: ToolErrorPayload;

  constructor(payload: ToolErrorPayload) {
    super(payload.message);
    this.name = "ToolInvocationError";
    this.payload = payload;
  }
}

export interface ToolDefinition<Input, Output> {
  name: string;
  description: string;
  parameters: Record<string, ToolParameter>;
  timeoutMs: number;
  execute: (input: Input, signal?: AbortSignal) => Promise<Output>;
}

export interface DefineToolOptions<Input, Output> {
  name: string;
  description: string;
  parameters: Record<string, ToolParameter>;
  timeoutMs: number;
  execute: (input: Input, signal: AbortSignal) => Promise<Output>;
}

/** 参数校验：缺必填、类型不符、枚举越界都在调用外部服务之前拦下。 */
export function validateParameters(
  parameters: Record<string, ToolParameter>,
  input: unknown,
): string[] {
  const errors: string[] = [];
  if (input === null || typeof input !== "object") {
    return ["参数必须是对象"];
  }
  const record = input as Record<string, unknown>;
  for (const [key, spec] of Object.entries(parameters)) {
    const value = record[key];
    const blankString = typeof value === "string" && value.trim() === "";
    if (value === undefined || value === null || blankString) {
      if (spec.required) errors.push(`缺少必填参数：${key}`);
      continue;
    }
    switch (spec.type) {
      case "string":
        if (typeof value !== "string") errors.push(`${key} 必须是字符串`);
        break;
      case "number":
        if (typeof value !== "number" || Number.isNaN(value)) errors.push(`${key} 必须是数字`);
        break;
      case "boolean":
        if (typeof value !== "boolean") errors.push(`${key} 必须是布尔值`);
        break;
      case "array":
        if (!Array.isArray(value)) errors.push(`${key} 必须是数组`);
        break;
      case "object":
        if (typeof value !== "object" || Array.isArray(value)) errors.push(`${key} 必须是对象`);
        break;
      default:
        errors.push(`${key} 的参数类型声明非法：${String(spec.type)}`);
    }
    if (spec.enum && spec.enum.length > 0 && typeof value === "string" && !spec.enum.includes(value)) {
      errors.push(`${key} 只能取 ${spec.enum.join(" | ")}，实际 ${value}`);
    }
  }
  for (const key of Object.keys(record)) {
    if (!(key in parameters)) errors.push(`未知参数：${key}`);
  }
  return errors;
}

function timeoutError(name: string, timeoutMs: number): ToolInvocationError {
  return new ToolInvocationError({
    code: "TIMEOUT",
    message: `${name} 超过 ${Math.round(timeoutMs / 1000)} 秒预算，已中止本次调用，可重试或改用更小的输入。`,
    retryable: true,
    fallback: "",
  });
}

/**
 * 声明一个工具：校验参数 -> 带超时执行 -> 统一抛 ToolInvocationError。
 * 超时用 AbortController 真正中断下游请求，不是只 Promise.race 假装超时。
 */
export function defineTool<Input extends object, Output>(
  options: DefineToolOptions<Input, Output>,
): ToolDefinition<Input, Output> {
  return {
    name: options.name,
    description: options.description,
    parameters: options.parameters,
    timeoutMs: options.timeoutMs,
    async execute(input: Input, outerSignal?: AbortSignal): Promise<Output> {
      const errors = validateParameters(options.parameters, input);
      if (errors.length > 0) {
        throw new ToolInvocationError({
          code: "INVALID_INPUT",
          message: `参数校验失败：${errors.join("；")}`,
          retryable: false,
          fallback: "",
          detail: { errors },
        });
      }
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), options.timeoutMs);
      const onOuterAbort = () => controller.abort();
      outerSignal?.addEventListener("abort", onOuterAbort);
      // 下游可能不理会 signal（比如第三方 SDK 内部死循环重试）。只 abort 不 race，
      // 超时就会永远挂住，所以这里再压一层：abort 一到就立刻以 TIMEOUT 收尾。
      const aborted = new Promise<never>((_, reject) => {
        controller.signal.addEventListener("abort", () => reject(timeoutError(options.name, options.timeoutMs)));
      });
      aborted.catch(() => undefined);
      try {
        const running = options.execute(input, controller.signal);
        running.catch(() => undefined); // 竞速失败的一方不再冒泡成 unhandledRejection
        return await Promise.race([running, aborted]);
      } catch (error) {
        if (error instanceof ToolInvocationError) throw error;
        if (controller.signal.aborted) throw timeoutError(options.name, options.timeoutMs);
        const message = error instanceof Error ? error.message : String(error);
        throw new ToolInvocationError({
          code: "UPSTREAM_ERROR",
          message: `${options.name} 调用失败：${message}`,
          retryable: true,
          fallback: "",
        });
      } finally {
        clearTimeout(timer);
        outerSignal?.removeEventListener("abort", onOuterAbort);
      }
    },
  };
}
