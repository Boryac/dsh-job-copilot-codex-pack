/**
 * A1 的层内自检：defineTool 的三条硬约束。
 *   1) 参数不合法时，execute 一次都不许被调用（不能带着坏参数去打外部服务）
 *   2) 超时必须真的中止，并在预算附近返回 TIMEOUT（不是无限挂住）
 *   3) 下游异常必须映射成带 code/retryable/fallback 的结构化错误
 */
import assert from "node:assert/strict";
import test from "node:test";

import { defineTool, ToolInvocationError, validateParameters, type ToolParameter } from "../src/sdk";

const PARAMS: Record<string, ToolParameter> = {
  file_path: { type: "string", required: true, description: "路径" },
  depth: { type: "string", description: "深度", enum: ["basic", "deep"] },
  confirmed_deep: { type: "boolean", description: "是否确认" },
  role_keywords: { type: "array", description: "关键词" },
  payload: { type: "object", description: "对象" },
};

test("validateParameters 拦下缺必填、类型不符、枚举越界与未知参数", () => {
  assert.deepEqual(validateParameters(PARAMS, { file_path: "a.pdf" }), []);

  const missing = validateParameters(PARAMS, {});
  assert.ok(missing.some((item) => item.includes("缺少必填参数：file_path")), missing.join("|"));

  const emptyString = validateParameters(PARAMS, { file_path: "   " });
  assert.ok(emptyString.some((item) => item.includes("缺少必填参数：file_path")), "空白字符串不能算填了");

  const wrongType = validateParameters(PARAMS, { file_path: 1, confirmed_deep: "yes", role_keywords: "a", payload: [] });
  assert.ok(wrongType.some((item) => item.includes("file_path 必须是字符串")), wrongType.join("|"));
  assert.ok(wrongType.some((item) => item.includes("confirmed_deep 必须是布尔值")));
  assert.ok(wrongType.some((item) => item.includes("role_keywords 必须是数组")));
  assert.ok(wrongType.some((item) => item.includes("payload 必须是对象")));

  const badEnum = validateParameters(PARAMS, { file_path: "a.pdf", depth: "superdeep" });
  assert.ok(badEnum.some((item) => item.includes("depth 只能取 basic | deep")), badEnum.join("|"));

  const unknown = validateParameters(PARAMS, { file_path: "a.pdf", resume_text: "整份简历" });
  assert.ok(unknown.some((item) => item.includes("未知参数：resume_text")), "未知参数要拦，避免把简历内容塞进来");

  assert.deepEqual(validateParameters(PARAMS, null), ["参数必须是对象"]);
});

test("参数不合法时 execute 不会被调用", async () => {
  let called = 0;
  const tool = defineTool<{ file_path: string }, string>({
    name: "spy-tool",
    description: "只用来数调用次数",
    parameters: { file_path: { type: "string", required: true, description: "路径" } },
    timeoutMs: 1000,
    async execute() {
      called += 1;
      return "ok";
    },
  });

  await assert.rejects(
    () => tool.execute({} as { file_path: string }),
    (error: unknown) => {
      assert.ok(error instanceof ToolInvocationError);
      assert.equal(error.payload.code, "INVALID_INPUT");
      assert.equal(error.payload.retryable, false);
      return true;
    },
  );
  assert.equal(called, 0);
  assert.equal(tool.timeoutMs, 1000);
});

test("超时会中止下游并返回 TIMEOUT，即使下游不理会 signal", async () => {
  let sawAbort = false;
  const tool = defineTool<{ name: string }, string>({
    name: "hang-tool",
    description: "永不返回",
    parameters: { name: { type: "string", required: true, description: "名字" } },
    timeoutMs: 40,
    execute(_input, signal) {
      signal.addEventListener("abort", () => {
        sawAbort = true;
      });
      return new Promise<string>(() => undefined); // 故意不响应 signal
    },
  });

  const startedAt = Date.now();
  await assert.rejects(
    () => tool.execute({ name: "x" }),
    (error: unknown) => {
      assert.ok(error instanceof ToolInvocationError);
      assert.equal(error.payload.code, "TIMEOUT");
      assert.equal(error.payload.retryable, true);
      assert.match(error.payload.message, /超过/);
      return true;
    },
  );
  const elapsed = Date.now() - startedAt;
  assert.ok(elapsed < 2000, `应在预算附近返回，实际 ${elapsed}ms`);
  assert.equal(sawAbort, true, "必须真的 abort 下游，不能只 Promise.race 假装超时");
});

test("下游普通异常映射为 UPSTREAM_ERROR；ToolInvocationError 原样透传", async () => {
  const broken = defineTool<{ name: string }, string>({
    name: "broken-tool",
    description: "抛异常",
    parameters: { name: { type: "string", required: true, description: "名字" } },
    timeoutMs: 1000,
    async execute() {
      throw new Error("connection reset");
    },
  });
  await assert.rejects(
    () => broken.execute({ name: "x" }),
    (error: unknown) => {
      assert.ok(error instanceof ToolInvocationError);
      assert.equal(error.payload.code, "UPSTREAM_ERROR");
      assert.equal(error.payload.retryable, true);
      assert.match(error.payload.message, /connection reset/);
      return true;
    },
  );

  const configured = defineTool<{ name: string }, string>({
    name: "not-configured-tool",
    description: "未配置密钥",
    parameters: { name: { type: "string", required: true, description: "名字" } },
    timeoutMs: 1000,
    async execute() {
      throw new ToolInvocationError({
        code: "NOT_CONFIGURED",
        message: "未配置 TIANYANCHA_TOKEN",
        retryable: false,
        fallback: "manual_input",
      });
    },
  });
  await assert.rejects(
    () => configured.execute({ name: "x" }),
    (error: unknown) => {
      assert.ok(error instanceof ToolInvocationError);
      assert.equal(error.payload.code, "NOT_CONFIGURED");
      assert.equal(error.payload.fallback, "manual_input");
      return true;
    },
  );
});

test("外部取消也会中止本次调用", async () => {
  const tool = defineTool<{ name: string }, string>({
    name: "cancellable-tool",
    description: "等待外部取消",
    parameters: { name: { type: "string", required: true, description: "名字" } },
    timeoutMs: 5000,
    execute(_input, signal) {
      return new Promise<string>((_resolve, reject) => {
        signal.addEventListener("abort", () => reject(new Error("aborted")));
      });
    },
  });
  const controller = new AbortController();
  setTimeout(() => controller.abort(), 20);
  await assert.rejects(
    () => tool.execute({ name: "x" }, controller.signal),
    (error: unknown) => {
      assert.ok(error instanceof ToolInvocationError);
      assert.equal(error.payload.code, "TIMEOUT");
      return true;
    },
  );
});
