/**
 * /job-fit 命令形状回归。
 *
 * 上一轮的真实缺陷：命令对象写成 `execute` 而不是 `handler`，DSH 的
 * `@deepseek-ai/dsh-commands` 在 normalizeDefinition 里直接抛
 * `command "job-fit" handler must be a function`，异常被 `ctx.inject` 回调吞掉，
 * 于是命令从未进注册表、斜杠菜单里看不到 /job-fit，而工具和 Skill 一切正常。
 *
 * 这里把 dsh-commands 的三条硬校验照抄成断言，让这个坑不会再回来：
 *   1) name 必须匹配 /^[a-z][a-z0-9_-]*$/
 *   2) description 必须是非空字符串
 *   3) handler 必须是函数（不是 execute、不是 run、不是 invoke）
 *   4) input.hint 给了就必须是非空字符串
 */
import assert from "node:assert/strict";
import test from "node:test";

import { join } from "node:path";
import { pathToFileURL } from "node:url";

// 插件入口是 ESM（host.mjs），本测试编译成 CJS，用 Function 包一层拿真正的动态 import。
const dynamicImport = new Function("specifier", "return import(specifier)") as (
  specifier: string,
) => Promise<Record<string, unknown>>;

const COMMAND_NAME = /^[a-z][a-z0-9_-]*$/u;

async function loadCommand() {
  const host = await dynamicImport(pathToFileURL(join(__dirname, "..", "..", "host.mjs")).href);
  const internals = host.internals as { buildCommand: (dir: string) => Record<string, unknown> };
  return internals.buildCommand(join(__dirname, "reports-out"));
}

test("/job-fit 命令满足 dsh-commands 的全部注册校验", async () => {
  const command = await loadCommand();

  assert.equal(command.name, "job-fit");
  assert.match(String(command.name), COMMAND_NAME, "命令名不匹配 dsh-commands 的 COMMAND_NAME 正则");

  assert.equal(typeof command.description, "string");
  assert.ok(String(command.description).trim().length > 0, "description 不能为空");

  // 核心回归点：dsh-commands 只认 handler。
  assert.equal(typeof command.handler, "function", "命令必须用 handler，否则注册直接抛 TypeError");
  assert.ok(!("execute" in command), "不能残留 execute 字段（dsh-commands 不认，会静默失败）");

  const input = command.input as { hint?: unknown } | undefined;
  assert.ok(input !== undefined, "缺少 input，斜杠菜单没有参数提示");
  assert.equal(typeof input?.hint, "string");
  assert.ok(String(input?.hint).trim().length > 0, "input.hint 不能为空");

  assert.equal(typeof command.definitionId, "string", "definitionId 用于定义/执行配对");
});

test("/job-fit 在缺参时返回结构化 error，而不是抛异常", async () => {
  const command = await loadCommand();
  const handler = command.handler as (invocation: unknown) => Promise<{ kind: string; text?: string }>;

  const result = await handler({ rawInput: "--company 某公司", attachments: [] });
  assert.equal(result.kind, "error");
  assert.match(String(result.text), /缺少 --resume/);
});
