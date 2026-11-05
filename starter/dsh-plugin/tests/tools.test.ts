/**
 * 三个工具的行为自检。
 * 重点不是"能不能跑通"，而是几条死规矩：
 *   - resume-structurer：30 秒预算，首次超时收紧抽取范围重试一次，两次都超时明确报 TIMEOUT
 *   - jd-decoder：粘贴文本是主路径；什么都没给时提示补文本，且不许打外部服务
 *   - company-recon：deep 未确认只返回预估卡片，且预估路径绝不触发 recon
 */
import assert from "node:assert/strict";
import test, { before } from "node:test";
import { mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { resumeStructurerTool } from "../src/tools/resume-structurer";
import { jdDecoderTool } from "../src/tools/jd-decoder";
import { companyReconTool, isDeepEstimate } from "../src/tools/company-recon";
import { ToolInvocationError } from "../src/sdk";
import {
  companyFixture,
  deepEstimateFixture,
  errorResponse,
  formField,
  installFakeFetch,
  jdFixture,
  jsonResponse,
  resumeFixture,
} from "./helpers";

let resumeFile = "";
const FULL_TYPES = "basic_info,education,work_experience,projects,skills";

before(async () => {
  const dir = await mkdtemp(join(tmpdir(), "dsh-plugin-"));
  resumeFile = join(dir, "resume.txt");
  await writeFile(resumeFile, "林舟 BD 实习生 2025.07-2025.09 酷旅", "utf8");
});

test("resume-structurer 默认按全量字段抽取，返回符合契约的结构化简历", async () => {
  const calls = installFakeFetch(() => jsonResponse(resumeFixture()));
  const result = await resumeStructurerTool.execute({ file_path: resumeFile, resume_id: "v1" });

  assert.equal(calls.length, 1);
  assert.equal(calls[0]?.url, "http://sidecar.test/v1/resume/parse");
  assert.equal(formField(calls[0]?.init, "extract_types"), FULL_TYPES);
  assert.equal(formField(calls[0]?.init, "resume_id"), "v1");
  assert.equal(result.experiences[0]?.id, "exp_01");
  assert.equal(resumeStructurerTool.timeoutMs, 30_000, "02 第 4 节：简历解析预算 30 秒");
});

test("resume-structurer 首次超时会收窄字段重试一次，而不是直接失败", async () => {
  let attempt = 0;
  const calls = installFakeFetch(() => {
    attempt += 1;
    if (attempt === 1) return errorResponse("TIMEOUT", "简历解析超时", 408);
    return jsonResponse(resumeFixture());
  });

  const result = await resumeStructurerTool.execute({ file_path: resumeFile });

  assert.equal(calls.length, 2);
  assert.equal(formField(calls[0]?.init, "extract_types"), FULL_TYPES);
  assert.equal(formField(calls[1]?.init, "extract_types"), "basic_info,work_experience", "第二次必须收窄范围");
  assert.equal(result.experiences.length, 1);
});

test("resume-structurer 两次都超时才报 TIMEOUT，并给出改文本版的建议", async () => {
  const calls = installFakeFetch(() => errorResponse("TIMEOUT", "简历解析超时", 408));
  await assert.rejects(
    () => resumeStructurerTool.execute({ file_path: resumeFile }),
    (error: unknown) => {
      assert.ok(error instanceof ToolInvocationError);
      assert.equal(error.payload.code, "TIMEOUT");
      assert.equal(error.payload.retryable, true);
      assert.equal(error.payload.fallback, "fallback_parser");
      assert.match(error.payload.message, /文本版简历/);
      return true;
    },
  );
  assert.equal(calls.length, 2, "只重试一次，不许死循环重试");
});

test("resume-structurer 参数缺失时不发请求", async () => {
  const calls = installFakeFetch(() => jsonResponse(resumeFixture()));
  await assert.rejects(
    () => resumeStructurerTool.execute({} as never),
    (error: unknown) => error instanceof ToolInvocationError && error.payload.code === "INVALID_INPUT",
  );
  assert.equal(calls.length, 0);
});

test("jd-decoder 优先用粘贴文本，URL 传 null", async () => {
  const calls = installFakeFetch(() => jsonResponse(jdFixture()));
  const result = await jdDecoderTool.execute({ text: "负责区域酒店供应链拓展，要求 1 年以上 BD 经验" });

  assert.equal(calls[0]?.url, "http://sidecar.test/v1/jd/decode");
  const body = JSON.parse(String(calls[0]?.init?.body)) as Record<string, unknown>;
  assert.equal(typeof body.text, "string");
  assert.equal(body.url, null, "有文本时不该顺手也去抓链接");
  assert.equal(result.must_have[0]?.id, "jd_01");
  assert.equal(jdDecoderTool.timeoutMs, 20_000, "02 第 4 节：JD 拆解预算 20 秒");
});

test("jd-decoder 只有链接时走 URL 路径", async () => {
  const calls = installFakeFetch(() => jsonResponse(jdFixture({ source_type: "url" })));
  const result = await jdDecoderTool.execute({ url: "https://example.com/job/1" });

  const body = JSON.parse(String(calls[0]?.init?.body)) as Record<string, unknown>;
  assert.equal(body.text, null);
  assert.equal(body.url, "https://example.com/job/1");
  assert.equal(result.source_type, "url");
});

test("jd-decoder 既没文本也没链接时要求补文本，且零调用", async () => {
  const calls = installFakeFetch(() => jsonResponse(jdFixture()));
  await assert.rejects(
    () => jdDecoderTool.execute({ text: "太短" }),
    (error: unknown) => {
      assert.ok(error instanceof ToolInvocationError);
      assert.equal(error.payload.code, "INVALID_INPUT");
      assert.equal(error.payload.retryable, false);
      assert.equal(error.payload.fallback, "pasted_text_required");
      return true;
    },
  );
  assert.equal(calls.length, 0);
});

test("company-recon basic 走 recon，depth 与 confirmed_deep 如实透传", async () => {
  const calls = installFakeFetch(() => jsonResponse(companyFixture()));
  const result = await companyReconTool.execute({ company_name: "云栖生活", role_keywords: ["BD"] });

  assert.equal(calls[0]?.url, "http://sidecar.test/v1/company/recon");
  const body = JSON.parse(String(calls[0]?.init?.body)) as Record<string, unknown>;
  assert.equal(body.depth, "basic");
  assert.equal(body.confirmed_deep, false);
  assert.deepEqual(body.role_keywords, ["BD"]);
  assert.equal(isDeepEstimate(result), false);
  assert.equal(companyReconTool.timeoutMs, 30_000, "02 第 4 节：公司背调预算 30 秒");
});

test("company-recon deep 未确认只打预估接口，绝不触发付费 recon", async () => {
  const calls = installFakeFetch((url) => {
    if (url.endsWith("/v1/company/deep/estimate")) return jsonResponse(deepEstimateFixture());
    return jsonResponse(companyFixture({ depth_used: "deep", deep_data: { shareholder: [] } }));
  });

  const result = await companyReconTool.execute({ company_name: "云栖生活", depth: "deep" });

  assert.equal(calls.length, 1);
  assert.equal(calls[0]?.url, "http://sidecar.test/v1/company/deep/estimate");
  assert.ok(calls.every((call) => !call.url.endsWith("/v1/company/recon")), "未确认前不许碰 recon");
  assert.equal(isDeepEstimate(result), true);
  if (isDeepEstimate(result)) {
    assert.equal(result.quota_consumed.tianyancha_calls, 0);
    assert.equal(result.estimate.mock, true);
  }
});

test("company-recon deep 已确认才走 recon", async () => {
  const calls = installFakeFetch((url) => {
    if (url.endsWith("/v1/company/deep/estimate")) return jsonResponse(deepEstimateFixture());
    return jsonResponse(companyFixture({ depth_used: "deep", deep_data: { shareholder: [] }, quota_consumed: { tianyancha_calls: 8, tianyancha_detail: [], search_calls: 4 } }));
  });

  const result = await companyReconTool.execute({ company_name: "云栖生活", depth: "deep", confirmed_deep: true });

  assert.equal(calls[0]?.url, "http://sidecar.test/v1/company/recon");
  const body = JSON.parse(String(calls[0]?.init?.body)) as Record<string, unknown>;
  assert.equal(body.confirmed_deep, true);
  assert.equal(isDeepEstimate(result), false);
});

test("company-recon 枚举越界在本地就被拦下", async () => {
  const calls = installFakeFetch(() => jsonResponse(companyFixture()));
  await assert.rejects(
    () => companyReconTool.execute({ company_name: "云栖生活", depth: "full" as never }),
    (error: unknown) => error instanceof ToolInvocationError && error.payload.code === "INVALID_INPUT",
  );
  assert.equal(calls.length, 0);
});

test("sidecar 不可达时给出可操作的提示，而不是裸异常", async () => {
  installFakeFetch(() => {
    throw new Error("ECONNREFUSED");
  });
  await assert.rejects(
    () => companyReconTool.execute({ company_name: "云栖生活" }),
    (error: unknown) => {
      assert.ok(error instanceof ToolInvocationError);
      assert.equal(error.payload.code, "UPSTREAM_ERROR");
      assert.match(error.payload.message, /sidecar 不可达/);
      assert.match(error.payload.message, /uvicorn/);
      return true;
    },
  );
});
