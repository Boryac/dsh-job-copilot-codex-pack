/**
 * 端到端分析客户端（供 skill 编排层调用）：一次请求产出摘要卡片 + Markdown 报告。
 * 插件层不在这里做匹配或生成，只做参数整理与结果校验。
 */
import { AnalysisResponse, ContractError, SummaryCard, Tier } from "./contracts";
import { callSidecar } from "./http";
import { ToolInvocationError } from "./sdk";

export interface RunAnalysisInput {
  resume_path: string;
  jd_text?: string;
  jd_url?: string;
  company_name: string;
  depth?: "basic" | "deep";
  confirmed_deep?: boolean;
}

const VALID_TIERS: Tier[] = ["strong", "discussable", "gap"];

export function assertAnalysis(value: unknown): AnalysisResponse {
  if (typeof value !== "object" || value === null) throw new ContractError("分析结果必须是对象");
  const data = value as Record<string, unknown>;
  for (const key of ["analysis_id", "markdown", "filename"]) {
    if (typeof data[key] !== "string" || (data[key] as string).length === 0) {
      throw new ContractError(`分析结果缺少 ${key}`);
    }
  }
  const card = data.card as SummaryCard | undefined;
  if (!card || !VALID_TIERS.includes(card.verdict_tier)) {
    throw new ContractError("摘要卡片的 verdict_tier 非法");
  }
  if (!Array.isArray(card.sections) || card.sections.length === 0) {
    throw new ContractError("摘要卡片缺少各节锚点");
  }
  return data as unknown as AnalysisResponse;
}

export async function runAnalysis(input: RunAnalysisInput, signal?: AbortSignal): Promise<AnalysisResponse> {
  if (!input.resume_path) {
    throw new ToolInvocationError({
      code: "INVALID_INPUT",
      message: "缺少 resume_path：请先上传简历并拿到本地路径。",
      retryable: false,
      fallback: "",
    });
  }
  const hasText = typeof input.jd_text === "string" && input.jd_text.trim().length >= 20;
  const hasUrl = typeof input.jd_url === "string" && input.jd_url.trim().length > 0;
  if (!hasText && !hasUrl) {
    throw new ToolInvocationError({
      code: "INVALID_INPUT",
      message: "缺少 JD：请粘贴 JD 文本（推荐）或提供可公开访问的链接。",
      retryable: false,
      fallback: "pasted_text_required",
    });
  }
  const raw = await callSidecar<unknown>(
    "/v1/analysis",
    {
      resume_path: input.resume_path,
      jd_text: hasText ? input.jd_text : null,
      jd_url: hasUrl ? input.jd_url : null,
      company_name: input.company_name,
      depth: input.depth ?? "basic",
      confirmed_deep: input.confirmed_deep === true,
    },
    signal,
  );
  return assertAnalysis(raw);
}
