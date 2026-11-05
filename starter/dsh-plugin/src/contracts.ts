/**
 * 03_DATA_CONTRACTS 的 TypeScript 侧类型与运行时校验（Lane A）。
 *
 * 为什么还要运行时校验：插件层是"转发 + 渲染"，如果 sidecar 升级后字段漂移，
 * 不做校验就会把坏数据渲染成卡片，用户看到的是错误结论而不是错误提示。
 * 契约不符一律抛 ContractError，由 execute 映射成 UPSTREAM_ERROR。
 */

export class ContractError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ContractError";
  }
}

export type Tier = "strong" | "discussable" | "gap";
export type Depth = "basic" | "deep";
export type DataMode = "mock" | "live";

export interface Metric {
  value: string;
  context: string;
}

export interface Experience {
  id: string;
  company?: string | null;
  role?: string | null;
  period?: string | null;
  bullets: string[];
  metrics: Metric[];
}

export interface ResumeStructured {
  schema_version: "1.0";
  parsing_mode: "smartresume" | "fallback";
  basic_info: { name?: string | null; title?: string | null; location?: string | null; links: string[] };
  education: Array<{ school?: string | null; major?: string | null; degree?: string | null; period?: string | null }>;
  experiences: Experience[];
  projects: Array<{ id: string; name?: string | null; bullets: string[]; metrics: Metric[] }>;
  skills: string[];
  parsing_notes: string[];
  data_mode: DataMode;
}

export interface HardField {
  value: string | number | null;
  verified: boolean;
  source: string;
}

export interface CompanyRecon {
  schema_version: "1.0";
  company_input: string;
  company_resolved: {
    name: string | null;
    unified_credit_code: string | null;
    disambiguation: {
      candidates: Array<{ name: string; match_reason: string; score?: number | null }>;
      chosen_reason: string;
      needs_user_confirm: boolean;
    };
  };
  hard_data: Record<string, HardField>;
  soft_profile: {
    products: Array<Record<string, unknown>>;
    news: Array<Record<string, unknown>>;
    financing: Array<Record<string, unknown>>;
    hiring_signals: string[];
    inferred: true;
    source_urls: string[];
  };
  deep_data: Record<string, unknown> | null;
  depth_used: Depth;
  quota_consumed: { tianyancha_calls: number; tianyancha_detail: Array<Record<string, unknown>>; search_calls: number };
  fetched_at: string;
  data_mode: DataMode;
  cache: { hit: boolean; fetched_at?: string | null };
  degradations: string[];
}

export interface JdDecoded {
  schema_version: "1.0";
  source_type: "pasted_text" | "url";
  must_have: Array<{ id: string; text: string; type: "hard" }>;
  nice_to_have: Array<{ id: string; text: string; type: "soft" }>;
  responsibilities: Array<{ id: string; text: string }>;
  hidden_priorities: Array<{ text: string; evidence_sentence_ids: string[]; inferred: true }>;
  red_flags: Array<{ text: string; evidence_sentence_ids: string[]; inferred: true }>;
  role_summary: string;
  sentences: Array<{ id: string; text: string }>;
  data_mode: DataMode;
}

export interface DeepEstimate {
  needs_confirmation: true;
  company_input: string;
  fields: string[];
  estimate: { calls: number; cost_yuan: number; currency: string; mock: boolean; price_note: string; detail: Array<Record<string, unknown>> };
  quota_consumed: { tianyancha_calls: number; tianyancha_detail: Array<Record<string, unknown>>; search_calls: number };
  idempotency_key: string;
  note: string;
}

export interface AnalysisResponse {
  analysis_id: string;
  card: SummaryCard;
  structured: Record<string, unknown>;
  markdown: string;
  filename: string;
  timings: Record<string, number>;
  degradations: string[];
  validation_warnings: string[];
}

export interface SummaryCard {
  analysis_id: string;
  verdict_tier: Tier;
  headline: string;
  top_strength: string;
  top_gap: string;
  recommended_action: string;
  company_name: string | null;
  depth: Depth;
  parsing_mode: string | null;
  generated_at: string;
  report_filename: string;
  sections: Array<{ title: string; anchor: string }>;
  degradations: string[];
  data_mode: DataMode;
}

const EXP_ID = /^exp_\d{2,3}$/;
const PROJ_ID = /^proj_\d{2,3}$/;
const JD_ID = /^jd_\d{2,3}$/;

function requireObject(value: unknown, label: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new ContractError(`${label} 必须是对象`);
  }
  return value as Record<string, unknown>;
}

function requireArray(value: unknown, label: string): unknown[] {
  if (!Array.isArray(value)) throw new ContractError(`${label} 必须是数组`);
  return value;
}

function requireString(value: unknown, label: string): string {
  if (typeof value !== "string") throw new ContractError(`${label} 必须是字符串`);
  return value;
}

export function assertResume(value: unknown): ResumeStructured {
  const data = requireObject(value, "简历结构化结果");
  if (data.schema_version !== "1.0") throw new ContractError(`schema_version 必须为 1.0，实际 ${String(data.schema_version)}`);
  if (data.parsing_mode !== "smartresume" && data.parsing_mode !== "fallback") {
    throw new ContractError(`parsing_mode 非法：${String(data.parsing_mode)}`);
  }
  const experiences = requireArray(data.experiences, "experiences");
  const ids: string[] = [];
  experiences.forEach((item, index) => {
    const exp = requireObject(item, `experiences[${index}]`);
    const id = requireString(exp.id, `experiences[${index}].id`);
    if (!EXP_ID.test(id)) throw new ContractError(`经历 ID 必须形如 exp_01，实际 ${id}`);
    ids.push(id);
    requireArray(exp.bullets, `experiences[${index}].bullets`);
    requireArray(exp.metrics, `experiences[${index}].metrics`);
  });
  const expected = ids.map((_, i) => `exp_${String(i + 1).padStart(2, "0")}`);
  if (ids.join(",") !== expected.join(",")) {
    throw new ContractError(`经历 ID 必须从 exp_01 连续编号，实际 ${ids.join(",")}`);
  }
  requireArray(data.projects, "projects").forEach((item, index) => {
    const proj = requireObject(item, `projects[${index}]`);
    const id = requireString(proj.id, `projects[${index}].id`);
    if (!PROJ_ID.test(id)) throw new ContractError(`项目 ID 必须形如 proj_01，实际 ${id}`);
  });
  if (data.data_mode !== "mock" && data.data_mode !== "live") {
    throw new ContractError(`data_mode 非法：${String(data.data_mode)}`);
  }
  return value as ResumeStructured;
}

export function assertJd(value: unknown): JdDecoded {
  const data = requireObject(value, "JD 结构化结果");
  if (data.schema_version !== "1.0") throw new ContractError("JD schema_version 必须为 1.0");
  if (data.source_type !== "pasted_text" && data.source_type !== "url") {
    throw new ContractError(`source_type 非法：${String(data.source_type)}`);
  }
  const seen = new Set<string>();
  const checkIds = (list: unknown, label: string) => {
    requireArray(list, label).forEach((item, index) => {
      const row = requireObject(item, `${label}[${index}]`);
      const id = requireString(row.id, `${label}[${index}].id`);
      if (!JD_ID.test(id)) throw new ContractError(`${label} ID 必须形如 jd_01，实际 ${id}`);
      if (seen.has(id)) throw new ContractError(`JD ID 重复：${id}`);
      seen.add(id);
      requireString(row.text, `${label}[${index}].text`);
    });
  };
  checkIds(data.must_have, "must_have");
  checkIds(data.nice_to_have, "nice_to_have");
  checkIds(data.responsibilities, "responsibilities");
  for (const key of ["hidden_priorities", "red_flags"] as const) {
    requireArray(data[key], key).forEach((item, index) => {
      const row = requireObject(item, `${key}[${index}]`);
      if (row.inferred !== true) throw new ContractError(`${key}[${index}] 必须标注 inferred: true`);
    });
  }
  return value as JdDecoded;
}

export function assertCompany(value: unknown): CompanyRecon {
  const data = requireObject(value, "公司背调结果");
  if (data.schema_version !== "1.0") throw new ContractError("公司背调 schema_version 必须为 1.0");
  const hard = requireObject(data.hard_data, "hard_data");
  for (const [key, field] of Object.entries(hard)) {
    const f = requireObject(field, `hard_data.${key}`);
    if ("inferred" in f) throw new ContractError(`hard_data.${key} 不许出现 inferred 字段（硬数据不许是推断）`);
    if (typeof f.verified !== "boolean") throw new ContractError(`hard_data.${key}.verified 必须是布尔值`);
  }
  const soft = requireObject(data.soft_profile, "soft_profile");
  if (soft.inferred !== true) throw new ContractError("soft_profile.inferred 必须为 true");
  if (data.depth_used !== "basic" && data.depth_used !== "deep") {
    throw new ContractError(`depth_used 非法：${String(data.depth_used)}`);
  }
  if (data.depth_used === "deep" && (data.deep_data === null || data.deep_data === undefined)) {
    throw new ContractError("depth_used=deep 时 deep_data 不许为空");
  }
  const quota = requireObject(data.quota_consumed, "quota_consumed");
  if (typeof quota.tianyancha_calls !== "number" || typeof quota.search_calls !== "number") {
    throw new ContractError("quota_consumed 必须包含 tianyancha_calls 与 search_calls");
  }
  return value as CompanyRecon;
}

export function assertDeepEstimate(value: unknown): DeepEstimate {
  const data = requireObject(value, "deep 预估");
  if (data.needs_confirmation !== true) throw new ContractError("deep 预估必须返回 needs_confirmation: true");
  const quota = requireObject(data.quota_consumed, "quota_consumed");
  if (quota.tianyancha_calls !== 0 || quota.search_calls !== 0) {
    throw new ContractError("预估卡片必须是零调用（quota_consumed 全为 0）");
  }
  const estimate = requireObject(data.estimate, "estimate");
  if (typeof estimate.calls !== "number") throw new ContractError("estimate.calls 必须是数字");
  return value as DeepEstimate;
}
