/**
 * 插件入口：注册三个工具 + 导出 skill 路径。
 * 真实 DSH 环境里，registry 由 SDK 提供；这里只依赖 register(def) 这一层语义。
 */
import { buildSummaryCard, renderCardText } from "./cards/summary-card";
import { runAnalysis, RunAnalysisInput } from "./analysis";
import { companyReconTool, isDeepEstimate } from "./tools/company-recon";
import { jdDecoderTool } from "./tools/jd-decoder";
import { resumeStructurerTool } from "./tools/resume-structurer";
import { ToolDefinition } from "./sdk";

export interface ToolRegistry {
  register: (tool: ToolDefinition<never, unknown> | ToolDefinition<object, unknown>) => void;
}

export const tools = [resumeStructurerTool, companyReconTool, jdDecoderTool];

export function registerTools(registry: ToolRegistry): string[] {
  for (const tool of tools) {
    registry.register(tool as unknown as ToolDefinition<object, unknown>);
  }
  return tools.map((tool) => tool.name);
}

export const SKILL_PATH = "src/skill/job-fit-orchestrator.md";

/** skill 编排层的主入口：一次产出卡片 + 报告，card 用于 DSH 内展示。 */
export async function analyseJobFit(input: RunAnalysisInput) {
  const response = await runAnalysis(input);
  const card = buildSummaryCard(response);
  return { response, card, cardText: renderCardText(card) };
}

export {
  buildSummaryCard,
  renderCardText,
  runAnalysis,
  isDeepEstimate,
  resumeStructurerTool,
  companyReconTool,
  jdDecoderTool,
};
