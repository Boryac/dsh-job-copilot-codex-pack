/**
 * 测试公用件：假 fetch + 契约样例。
 *
 * 为什么不用真的起 sidecar：A1 验的是"插件层自己的行为"——参数校验、超时、错误映射、
 * 契约校验。把这些和 sidecar 实现耦合在一起测，sidecar 一改测试就红，测不出层内缺陷。
 * sidecar 的真实链路另有 Python 侧 tests/ 与 scripts/run_mock_demo.py 覆盖。
 */
import { configureHttp } from "../src/http";
import type { CompanyRecon, DeepEstimate, JdDecoded, ResumeStructured, SummaryCard } from "../src/contracts";

export interface CallRecord {
  url: string;
  init: RequestInit | undefined;
}

export type FakeHandler = (url: string, init?: RequestInit) => Response | Promise<Response>;

/** 注入假 fetch，并把每次调用的 url 记下来供断言。 */
export function installFakeFetch(handler: FakeHandler, mode: "mock" | "live" = "mock"): CallRecord[] {
  const calls: CallRecord[] = [];
  const fake = (async (input: unknown, init?: RequestInit) => {
    const url = String(input);
    calls.push({ url, init });
    return handler(url, init);
  }) as unknown as typeof fetch;
  configureHttp({ fetchImpl: fake, mode, baseUrl: "http://sidecar.test" });
  return calls;
}

export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

/** sidecar 的标准错误契约（main.py 的 ToolError handler）。 */
export function errorResponse(code: string, message: string, status = 500, extra: Record<string, unknown> = {}): Response {
  return jsonResponse({ error: { code, message, retryable: true, fallback: "", ...extra } }, status);
}

export function formField(init: RequestInit | undefined, key: string): string | null {
  const body = init?.body;
  if (!(body instanceof FormData)) return null;
  const value = body.get(key);
  return typeof value === "string" ? value : null;
}

export function resumeFixture(overrides: Partial<ResumeStructured> = {}): unknown {
  return {
    schema_version: "1.0",
    parsing_mode: "fallback",
    basic_info: { name: "林舟", title: "BD", location: "福州", links: [] },
    education: [{ school: "福州外语外贸学院", major: "人工智能", degree: "本科", period: "2023-2027" }],
    experiences: [
      {
        id: "exp_01",
        company: "酷旅",
        role: "BD 实习生",
        period: "2025.07-2025.09",
        bullets: ["负责福建区域酒店供应商拓展，签约 12 家"],
        metrics: [{ value: "12", context: "家酒店签约" }],
      },
    ],
    projects: [{ id: "proj_01", name: "大模型应答系统", bullets: [], metrics: [] }],
    skills: ["SQL", "Excel"],
    parsing_notes: [],
    data_mode: "mock",
    ...overrides,
  };
}

export function jdFixture(overrides: Partial<JdDecoded> = {}): unknown {
  return {
    schema_version: "1.0",
    source_type: "pasted_text",
    must_have: [{ id: "jd_01", text: "1 年以上 BD 经验", type: "hard" }],
    nice_to_have: [{ id: "jd_02", text: "熟悉 OTA 行业", type: "soft" }],
    responsibilities: [{ id: "jd_03", text: "拓展酒店供应商并维护客情" }],
    hidden_priorities: [{ text: "能接受高频出差", evidence_sentence_ids: ["jd_03"], inferred: true }],
    red_flags: [],
    role_summary: "负责区域酒店供应链拓展的 BD 岗",
    sentences: [{ id: "jd_03", text: "拓展酒店供应商并维护客情" }],
    data_mode: "mock",
    ...overrides,
  };
}

export function companyFixture(overrides: Partial<CompanyRecon> = {}): unknown {
  return {
    schema_version: "1.0",
    company_input: "云栖生活",
    company_resolved: {
      name: "云栖生活科技（福州）有限公司",
      unified_credit_code: "91350100MA00000000",
      disambiguation: { candidates: [], chosen_reason: "唯一候选", needs_user_confirm: false },
    },
    hard_data: {
      established_at: { value: "2019-04-11", verified: true, source: "mock://tianyancha/basic" },
    },
    soft_profile: { products: [], news: [], financing: [], hiring_signals: [], inferred: true, source_urls: ["mock://search/1"] },
    deep_data: null,
    depth_used: "basic",
    quota_consumed: { tianyancha_calls: 2, tianyancha_detail: [], search_calls: 4 },
    fetched_at: "2026-01-01T00:00:00+08:00",
    data_mode: "mock",
    cache: { hit: false },
    degradations: [],
    ...overrides,
  };
}

export function deepEstimateFixture(overrides: Partial<DeepEstimate> = {}): unknown {
  return {
    needs_confirmation: true,
    company_input: "云栖生活",
    fields: ["股东穿透", "司法风险"],
    estimate: { calls: 6, cost_yuan: 0, currency: "CNY", mock: true, price_note: "Mock 模式不计费", detail: [] },
    quota_consumed: { tianyancha_calls: 0, tianyancha_detail: [], search_calls: 0 },
    idempotency_key: "deep:云栖生活:1",
    note: "确认后才会发起调用",
    ...overrides,
  };
}

export function cardFixture(overrides: Partial<SummaryCard> = {}): SummaryCard {
  return {
    analysis_id: "an_0001",
    verdict_tier: "discussable",
    headline: "可聊，但住宿供应链经验需要补",
    top_strength: "有 12 家酒店直签记录",
    top_gap: "缺 OTA 渠道侧经验",
    recommended_action: "先补一段渠道侧数据再投",
    company_name: "云栖生活",
    depth: "basic",
    parsing_mode: "fallback",
    generated_at: "2026-01-01T00:00:00+08:00",
    report_filename: "作战包_云栖生活_BD_20260101.md",
    sections: [
      { title: "0 结论先行", anchor: "sec-0" },
      { title: "1 岗位解读", anchor: "sec-1" },
    ],
    degradations: [],
    data_mode: "mock",
    ...overrides,
  };
}
