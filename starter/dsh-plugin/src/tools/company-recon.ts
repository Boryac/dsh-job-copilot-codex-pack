/**
 * company-recon：公司名称 -> 硬数据 + 软信息（03 第 3.2 节 / 05）。
 *
 * deep 路径的死规矩：未确认时只返回预估卡片，且预估必须零调用；
 * 用户取消 = 不产生任何付费调用。Mock 模式走同一套逻辑，只是费用为 0。
 */
import { assertCompany, assertDeepEstimate, CompanyRecon, DeepEstimate } from "../contracts";
import { callSidecar } from "../http";
import { defineTool } from "../sdk";

export interface CompanyReconInput {
  company_name: string;
  depth?: "basic" | "deep";
  confirmed_deep?: boolean;
  role_keywords?: string[];
}

export type CompanyReconOutput = CompanyRecon | DeepEstimate;

export const companyReconTool = defineTool<CompanyReconInput, CompanyReconOutput>({
  name: "company-recon",
  description:
    "公司背调：返回可验证的工商硬数据（verified/source）与公开渠道软信息（inferred/source_urls），两层严格分区。默认 basic；deep 需要用户显式确认预估费用。",
  timeoutMs: 30_000,
  parameters: {
    company_name: { type: "string", required: true, description: "公司名称，可以是简称或品牌名（会先做工商主体消歧）" },
    depth: {
      type: "string",
      description: "basic = 基础工商字段 + 搜索软信息；deep = 股东穿透/司法风险等按需付费字段",
      enum: ["basic", "deep"],
      default: "basic",
    },
    confirmed_deep: {
      type: "boolean",
      description: "仅在 depth=deep 时有意义：true 表示用户已确认预估费用；false 时只返回预估卡片，不产生调用",
      default: false,
    },
    role_keywords: { type: "array", description: "岗位关键词（来自 jd-decoder），只用于消歧打分，不含任何简历内容" },
  },
  async execute(input, signal) {
    const depth = input.depth ?? "basic";
    const roleKeywords = input.role_keywords ?? [];

    // deep 且未确认：先拿预估，绝不直接发起付费调用
    if (depth === "deep" && input.confirmed_deep !== true) {
      const estimate = await callSidecar<unknown>(
        "/v1/company/deep/estimate",
        { company_name: input.company_name, depth: "deep", role_keywords: roleKeywords },
        signal,
      );
      return assertDeepEstimate(estimate);
    }

    const raw = await callSidecar<unknown>(
      "/v1/company/recon",
      {
        company_name: input.company_name,
        depth,
        confirmed_deep: input.confirmed_deep === true,
        role_keywords: roleKeywords,
      },
      signal,
    );
    return assertCompany(raw);
  },
});

export function isDeepEstimate(output: CompanyReconOutput): output is DeepEstimate {
  return (output as DeepEstimate).needs_confirmation === true;
}
