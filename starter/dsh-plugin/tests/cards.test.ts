/**
 * 层内自检：DSH 内只放摘要卡片，完整报告是 Markdown 文件。
 * 卡片必须做到：档位可读、缺口与亮点不混淆、Mock/降级有明示、导出文件名可见。
 */
import assert from "node:assert/strict";
import test from "node:test";

import { buildSummaryCard, renderCardText } from "../src/cards/summary-card";
import type { AnalysisResponse } from "../src/contracts";
import { cardFixture } from "./helpers";

function analysis(overrides: Partial<AnalysisResponse> = {}): AnalysisResponse {
  return {
    analysis_id: "an_0001",
    card: cardFixture(),
    structured: {},
    markdown: "# 作战包\n",
    filename: "作战包_云栖生活_BD_20260101.md",
    timings: {},
    degradations: [],
    validation_warnings: [],
    ...overrides,
  };
}

test("卡片字段与档位文案对齐，且带导出文件名", () => {
  const view = buildSummaryCard(analysis());
  assert.equal(view.title, "作战包｜云栖生活");
  assert.equal(view.badge, "可聊，有缺口");
  assert.equal(view.badgeTone, "neutral");
  assert.equal(view.exportFile, "作战包_云栖生活_BD_20260101.md");
  assert.equal(view.sections.length, 2);
  assert.ok(view.meta.some((line) => line.includes("公司：云栖生活")));
  assert.ok(view.meta.some((line) => line.includes("depth：basic")));
});

test("三档对应三种语气", () => {
  assert.equal(buildSummaryCard(analysis({ card: cardFixture({ verdict_tier: "strong" }) })).badgeTone, "positive");
  assert.equal(buildSummaryCard(analysis({ card: cardFixture({ verdict_tier: "discussable" }) })).badgeTone, "neutral");
  assert.equal(buildSummaryCard(analysis({ card: cardFixture({ verdict_tier: "gap" }) })).badgeTone, "warning");
  assert.equal(buildSummaryCard(analysis({ card: cardFixture({ verdict_tier: "strong" }) })).badge, "强匹配");
  assert.equal(buildSummaryCard(analysis({ card: cardFixture({ verdict_tier: "gap" }) })).badge, "缺口明显");
});

test("Mock 模式、fallback 解析、降级都要在卡片上写明", () => {
  const view = buildSummaryCard(
    analysis({
      card: cardFixture({ data_mode: "mock", parsing_mode: "fallback", degradations: ["公司软信息抓取失败，仅用工商硬数据"] }),
    }),
  );
  assert.ok(view.footnotes.some((note) => note.includes("Mock 模式")), "Mock 数据不能当成真实结论");
  assert.ok(view.footnotes.some((note) => note.includes("fallback 解析")));
  assert.ok(view.footnotes.some((note) => note.includes("软信息抓取失败")));

  const live = buildSummaryCard(analysis({ card: cardFixture({ data_mode: "live", parsing_mode: "smartresume" }) }));
  assert.equal(live.footnotes.length, 0, "live + smartresume 不该有多余免责说明");
});

test("公司未解析时卡片不编造公司名", () => {
  const view = buildSummaryCard(analysis({ card: cardFixture({ company_name: null }) }));
  assert.equal(view.title, "作战包｜待确认公司");
  assert.ok(view.meta.some((line) => line.includes("公司：待确认")));
});

test("卡片文本化包含全部信息层次", () => {
  const text = renderCardText(buildSummaryCard(analysis()));
  for (const piece of ["作战包｜云栖生活", "可聊，有缺口", "最大亮点", "最大缺口", "建议动作", "完整报告：", "注意："]) {
    assert.ok(text.includes(piece), `卡片文本缺少：${piece}`);
  }
  assert.ok(text.includes("云栖生活"));
});
