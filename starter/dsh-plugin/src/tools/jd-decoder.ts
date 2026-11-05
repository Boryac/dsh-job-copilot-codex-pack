/**
 * jd-decoder：JD 文本 / URL -> 结构化拆解（03 第 3.3 节）。
 *
 * 主路径是粘贴文本；URL 只是辅助。抓取失败必须明确提示粘贴，
 * 不许用残缺内容静默继续（11 第 1 节）。
 */
import { assertJd, JdDecoded } from "../contracts";
import { callSidecar } from "../http";
import { defineTool, ToolInvocationError } from "../sdk";

export interface JdDecoderInput {
  text?: string;
  url?: string;
}

export const jdDecoderTool = defineTool<JdDecoderInput, JdDecoded>({
  name: "jd-decoder",
  description:
    "把岗位 JD 拆成 must_have / nice_to_have / responsibilities / hidden_priorities / red_flags，每条要求带稳定 ID（jd_01…）。优先使用粘贴文本。",
  timeoutMs: 20_000,
  parameters: {
    text: { type: "string", description: "粘贴的 JD 原文（推荐，主路径）" },
    url: { type: "string", description: "JD 链接（辅助，遇到登录墙/反爬会失败并要求改粘贴）" },
  },
  async execute(input, signal) {
    const hasText = typeof input.text === "string" && input.text.trim().length >= 20;
    const hasUrl = typeof input.url === "string" && input.url.trim().length > 0;
    if (!hasText && !hasUrl) {
      throw new ToolInvocationError({
        code: "INVALID_INPUT",
        message: "需要提供 JD 文本（至少 20 字）或 JD 链接。推荐直接粘贴 JD 正文。",
        retryable: false,
        fallback: "pasted_text_required",
      });
    }
    const raw = await callSidecar<unknown>("/v1/jd/decode", { text: hasText ? input.text : null, url: hasUrl ? input.url : null }, signal);
    return assertJd(raw);
  },
});
