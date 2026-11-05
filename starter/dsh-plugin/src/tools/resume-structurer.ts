/**
 * resume-structurer：简历文件 -> 结构化 JSON（03 第 3.1 节）。
 *
 * 超时策略（02 第 4 节）：30 秒预算；第一次超时后用更小的 extract_types 重试一次，
 * 仍失败才向用户报 TIMEOUT，并说明"可改用文本版简历"——不静默返回半成品。
 */
import { assertResume, ResumeStructured } from "../contracts";
import { uploadFile } from "../http";
import { defineTool, ToolInvocationError } from "../sdk";

export interface ResumeStructurerInput {
  file_path: string;
  resume_id?: string;
  extract_types?: string[];
}

const FULL_TYPES = ["basic_info", "education", "work_experience", "projects", "skills"];
const TRIMMED_TYPES = ["basic_info", "work_experience"];

export const resumeStructurerTool = defineTool<ResumeStructurerInput, ResumeStructured>({
  name: "resume-structurer",
  description:
    "把简历文件（PDF/DOCX/图片/TXT）解析成结构化 JSON：教育、经历（exp_01…）、项目、技能与量化成果。输出必须符合 03 数据契约。",
  timeoutMs: 30_000,
  parameters: {
    file_path: {
      type: "string",
      required: true,
      description: "简历文件的本地绝对路径，支持 .pdf / .docx / .txt / .md（图片需 OCR，当前会标注 fallback）",
    },
    resume_id: { type: "string", description: "简历版本标识，用于日志与幂等（只记哈希，不记内容）" },
    extract_types: {
      type: "array",
      description: "按需抽取的字段类型，默认全量。超时重试时会自动收窄为 basic_info + work_experience",
    },
  },
  async execute(input, signal) {
    const first = await tryParse(input, input.extract_types ?? FULL_TYPES, signal);
    if (first) return first;
    // 第一次超时：收窄抽取范围重试一次（减少 LLM 分段，不降低校验标准）
    const retry = await tryParse(input, TRIMMED_TYPES, signal);
    if (retry) return retry;
    throw new ToolInvocationError({
      code: "TIMEOUT",
      message:
        "简历解析两次都超过 30 秒预算。建议：改用文本版简历（或先另存为 DOCX）后重试；图片简历需要 OCR，当前环境默认不启用。",
      retryable: true,
      fallback: "fallback_parser",
    });
  },
});

async function tryParse(
  input: ResumeStructurerInput,
  extractTypes: string[],
  signal?: AbortSignal,
): Promise<ResumeStructured | null> {
  try {
    const raw = await uploadFile<unknown>(
      "/v1/resume/parse",
      input.file_path,
      { resume_id: input.resume_id ?? "", extract_types: extractTypes.join(",") },
      signal,
    );
    return assertResume(raw);
  } catch (error) {
    if (error instanceof ToolInvocationError && error.payload.code === "TIMEOUT") return null;
    throw error;
  }
}
