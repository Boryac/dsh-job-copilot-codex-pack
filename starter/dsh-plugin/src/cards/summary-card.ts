/**
 * DSH 摘要卡片（04 第 2 节）：只放第 0 节 + 各节锚点 + 导出文件名。
 * 完整报告是 Markdown 文件，卡片不做全文渲染。
 */
import { AnalysisResponse, SummaryCard, Tier } from "../contracts";

const TIER_LABEL: Record<Tier, string> = {
  strong: "强匹配",
  discussable: "可聊，有缺口",
  gap: "缺口明显",
};

export interface CardViewModel {
  title: string;
  badge: string;
  badgeTone: "positive" | "neutral" | "warning";
  headline: string;
  strength: string;
  gap: string;
  action: string;
  meta: string[];
  sections: Array<{ title: string; anchor: string }>;
  exportFile: string;
  footnotes: string[];
}

export function buildSummaryCard(response: AnalysisResponse): CardViewModel {
  const card: SummaryCard = response.card;
  const tone = card.verdict_tier === "strong" ? "positive" : card.verdict_tier === "gap" ? "warning" : "neutral";
  const footnotes: string[] = [];
  if (card.data_mode === "mock") {
    footnotes.push("当前是 Mock 模式：公司数据为虚构样本，不可用于真实投递决策。");
  }
  for (const item of card.degradations ?? []) footnotes.push(item);
  if (card.parsing_mode === "fallback") {
    footnotes.push("简历使用 fallback 解析（未启用 SmartResume），字段准确性需人工复核。");
  }
  const meta = [
    card.company_name ? `公司：${card.company_name}` : "公司：待确认",
    `depth：${card.depth}`,
    `解析方式：${card.parsing_mode ?? "未知"}`,
    `生成时间：${card.generated_at}`,
  ];
  return {
    title: `作战包｜${card.company_name ?? "待确认公司"}`,
    badge: TIER_LABEL[card.verdict_tier],
    badgeTone: tone,
    headline: card.headline,
    strength: card.top_strength,
    gap: card.top_gap,
    action: card.recommended_action,
    meta,
    sections: card.sections,
    exportFile: card.report_filename,
    footnotes,
  };
}

/** 卡片文本化：给不支持富文本的宿主用，保持同样的信息层次。 */
export function renderCardText(card: CardViewModel): string {
  const lines = [
    `${card.title}（${card.badge}）`,
    card.headline,
    `最大亮点：${card.strength}`,
    `最大缺口：${card.gap}`,
    `建议动作：${card.action}`,
    card.meta.join("｜"),
    `完整报告：${card.exportFile}`,
  ];
  if (card.footnotes.length > 0) {
    lines.push("注意：");
    for (const note of card.footnotes) lines.push(`- ${note}`);
  }
  return lines.join("\n");
}
