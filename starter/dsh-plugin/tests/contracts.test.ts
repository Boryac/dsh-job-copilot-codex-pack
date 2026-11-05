/**
 * B1/B2 的层内自检：03 数据契约在插件侧必须"挡住坏数据"。
 * 插件不修数据、不猜数据，契约不符一律抛 ContractError，让上层显示错误而不是渲染错误结论。
 */
import assert from "node:assert/strict";
import test from "node:test";

import {
  assertCompany,
  assertDeepEstimate,
  assertJd,
  assertResume,
  ContractError,
} from "../src/contracts";
import { assertAnalysis } from "../src/analysis";
import { cardFixture, companyFixture, deepEstimateFixture, jdFixture, resumeFixture } from "./helpers";

test("正常简历契约通过，且经历 ID 连续", () => {
  const parsed = assertResume(resumeFixture());
  assert.equal(parsed.experiences.length, 1);
  assert.equal(parsed.experiences[0]?.id, "exp_01");
});

test("经历 ID 断号、格式非法、schema_version 不符都要报错", () => {
  assert.throws(
    () =>
      assertResume(
        resumeFixture({
          experiences: [
            { id: "exp_01", bullets: [], metrics: [] },
            { id: "exp_03", bullets: [], metrics: [] },
          ],
        }),
      ),
    (error: unknown) => error instanceof ContractError && /连续编号/.test(error.message),
  );

  assert.throws(
    () => assertResume(resumeFixture({ experiences: [{ id: "exp1", bullets: [], metrics: [] }] })),
    (error: unknown) => error instanceof ContractError && /形如 exp_01/.test(error.message),
  );

  assert.throws(
    () => assertResume({ ...(resumeFixture() as object), schema_version: "2.0" }),
    (error: unknown) => error instanceof ContractError && /schema_version/.test(error.message),
  );

  assert.throws(
    () => assertResume({ ...(resumeFixture() as object), data_mode: "demo" }),
    (error: unknown) => error instanceof ContractError && /data_mode/.test(error.message),
  );
});

test("JD 的 ID 重复、缺 inferred 标记要报错", () => {
  assert.ok(assertJd(jdFixture()));

  assert.throws(
    () =>
      assertJd(
        jdFixture({
          must_have: [{ id: "jd_01", text: "a", type: "hard" }],
          nice_to_have: [{ id: "jd_01", text: "b", type: "soft" }],
        }),
      ),
    (error: unknown) => error instanceof ContractError && /ID 重复/.test(error.message),
  );

  assert.throws(
    () =>
      assertJd(
        jdFixture({
          hidden_priorities: [{ text: "能出差", evidence_sentence_ids: ["jd_03"] } as never],
        }),
      ),
    (error: unknown) => error instanceof ContractError && /inferred: true/.test(error.message),
  );

  assert.throws(
    () => assertJd({ ...(jdFixture() as object), source_type: "screenshot" }),
    (error: unknown) => error instanceof ContractError && /source_type/.test(error.message),
  );
});

test("硬数据不许出现 inferred；软信息必须 inferred:true；deep 数据不许空", () => {
  assert.ok(assertCompany(companyFixture()));

  assert.throws(
    () =>
      assertCompany(
        companyFixture({
          hard_data: { established_at: { value: "2019", verified: true, source: "x" } as never, headcount: { value: 30, verified: true, source: "x", inferred: true } as never },
        }),
      ),
    (error: unknown) => error instanceof ContractError && /不许出现 inferred/.test(error.message),
  );

  assert.throws(
    () => assertCompany(companyFixture({ soft_profile: { ...(companyFixture() as never as { soft_profile: object }).soft_profile, inferred: false } as never })),
    (error: unknown) => error instanceof ContractError && /soft_profile.inferred/.test(error.message),
  );

  assert.throws(
    () => assertCompany(companyFixture({ depth_used: "deep", deep_data: null })),
    (error: unknown) => error instanceof ContractError && /deep_data 不许为空/.test(error.message),
  );

  assert.throws(
    () => assertCompany(companyFixture({ quota_consumed: { tianyancha_calls: 2, tianyancha_detail: [], search_calls: "many" } as never })),
    (error: unknown) => error instanceof ContractError && /quota_consumed/.test(error.message),
  );
});

test("deep 预估卡片必须 needs_confirmation 且零调用", () => {
  assert.ok(assertDeepEstimate(deepEstimateFixture()));

  assert.throws(
    () => assertDeepEstimate(deepEstimateFixture({ needs_confirmation: false as never })),
    (error: unknown) => error instanceof ContractError && /needs_confirmation/.test(error.message),
  );

  assert.throws(
    () =>
      assertDeepEstimate(
        deepEstimateFixture({ quota_consumed: { tianyancha_calls: 3, tianyancha_detail: [], search_calls: 0 } }),
      ),
    (error: unknown) => error instanceof ContractError && /零调用/.test(error.message),
  );
});

test("分析结果缺 markdown、档位非法、缺锚点都要报错", () => {
  const ok = assertAnalysis({
    analysis_id: "an_0001",
    markdown: "# 报告",
    filename: "a.md",
    card: cardFixture(),
  });
  assert.equal(ok.card.verdict_tier, "discussable");

  assert.throws(
    () => assertAnalysis({ analysis_id: "an_0001", filename: "a.md", card: cardFixture() }),
    (error: unknown) => error instanceof ContractError && /markdown/.test(error.message),
  );

  assert.throws(
    () =>
      assertAnalysis({
        analysis_id: "an_0001",
        markdown: "#",
        filename: "a.md",
        card: { ...cardFixture(), verdict_tier: "perfect" },
      }),
    (error: unknown) => error instanceof ContractError && /verdict_tier/.test(error.message),
  );

  assert.throws(
    () =>
      assertAnalysis({
        analysis_id: "an_0001",
        markdown: "#",
        filename: "a.md",
        card: { ...cardFixture(), sections: [] },
      }),
    (error: unknown) => error instanceof ContractError && /锚点/.test(error.message),
  );
});
