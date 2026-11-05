/**
 * DSH 宿主层入口（Cordis 插件）。
 *
 * 这一层只做适配，不改业务：
 *   - 把 src/ 里已经声明好的 3 个工具挂到 DSH 的 tools registry；
 *   - 把 src/skill/job-fit-orchestrator.md 注册成 DSH 原生 skill；
 *   - 注册 /job-fit 命令，让"简历 + JD + 公司 -> 卡片 + Markdown 报告"整条链
 *     在 DSH 里能被一条命令触发（否则模型只能看到 3 个工具，拿不到第 4 步的编排结果）。
 *
 * 工具签名（名称、参数、超时、返回结构）全部来自 dist/src/index.js，本文件不复制也不改写。
 * 运行环境：DSH desktop 0.2.1-rc.5，Node 24，ESM。
 */
import { createRequire } from "node:module";
import { appendFileSync, mkdirSync, readFileSync, writeFileSync, existsSync } from "node:fs";
import { dirname, isAbsolute, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const HERE = dirname(fileURLToPath(import.meta.url));
const pkg = require("./package.json");
const core = require("./dist/src/index.js");

const PLUGIN_ID = pkg?.dsh?.id ?? "dsh-job-skill-plugin";
const SKILL_FILE = join(HERE, "src", "skill", "job-fit-orchestrator.md");

/** 加载/注册自证：装没装上不靠猜，只写本插件目录下的 load.log；只读安装目录时静默跳过。 */
function logLine(text) {
  try {
    appendFileSync(join(HERE, "load.log"), `${new Date().toISOString()}\t${text}\n`, "utf8");
  } catch {
    /* 只读安装目录时不自证也不阻塞加载 */
  }
}

export const name = PLUGIN_ID;
export const inject = ["tools"];

/** 本地抽象层的参数声明 -> DSH/JSON Schema。字段名与语义原样保留。 */
function toJsonSchema(parameters, description) {
  const properties = {};
  const required = [];
  for (const [key, spec] of Object.entries(parameters ?? {})) {
    const property = { type: spec.type, description: spec.description };
    if (Array.isArray(spec.enum) && spec.enum.length > 0) property.enum = [...spec.enum];
    if (spec.default !== undefined) property.default = spec.default;
    if (spec.type === "array") property.items = { type: "string" };
    properties[key] = property;
    if (spec.required) required.push(key);
  }
  return {
    schema: {
      type: "object",
      properties,
      ...(required.length > 0 ? { required } : {}),
      additionalProperties: false,
    },
    description,
  };
}

/** 工具输出渲染：DSH 需要 [{type:'text'}] 形态，内容保持 canonical JSON。 */
function renderToolText(_args, value) {
  return [{ type: "text", text: JSON.stringify(value, null, 1) }];
}

/** 把 ToolInvocationError 的 code/fallback 带进错误信息，便于在 DSH 里看清失败原因。 */
function toDshError(error) {
  if (error && typeof error === "object" && "payload" in error) {
    const payload = error.payload ?? {};
    const suffix = payload.fallback ? `（建议：${payload.fallback}）` : "";
    return Object.assign(new Error(`[${payload.code ?? "TOOL_ERROR"}] ${payload.message ?? ""}${suffix}`), {
      code: payload.code,
    });
  }
  return error instanceof Error ? error : new Error(String(error));
}

function toDshTool(definition) {
  const { schema, description } = toJsonSchema(definition.parameters, definition.description);
  return {
    name: definition.name,
    description,
    parameters: schema,
    output: { schema: { type: "object", additionalProperties: true }, render: renderToolText },
    async execute(args = {}, execution) {
      try {
        // 第 2 个入参是 AbortSignal：DSH 取消/超时时会真的中断下游请求。
        return await definition.execute(args, execution?.signal);
      } catch (error) {
        throw toDshError(error);
      }
    },
  };
}

function parseSkillFile() {
  const text = readFileSync(SKILL_FILE, "utf8");
  const match = /^---\r?\n([\s\S]*?)\r?\n---\r?\n([\s\S]+)$/.exec(text);
  if (!match) throw new Error("job-fit-orchestrator.md 缺少 frontmatter");
  const meta = {};
  for (const line of match[1].split(/\r?\n/)) {
    const field = /^([a-zA-Z_]+):\s*(.+)$/.exec(line);
    if (field) meta[field[1]] = field[2].trim().replace(/^"(.*)"$/, "$1");
  }
  if (!meta.name || !meta.description) throw new Error("job-fit-orchestrator.md 的 name/description 不能为空");
  return {
    name: meta.name,
    description: meta.description,
    source: "bundled",
    path: SKILL_FILE,
    resourceBase: { kind: "directory", path: dirname(SKILL_FILE) },
    invocation: { modelInvocable: true, userInvocable: true },
    content: match[2].trim(),
  };
}

/** 极简 flag 解析：--resume、--jd、--company、--out 四个参数，支持带引号的路径。 */
function parseFlags(rawInput) {
  const flags = {};
  const pattern = /--(resume|jd|company|out)\s+("([^"]*)"|'([^']*)'|(\S+))/g;
  let match;
  while ((match = pattern.exec(rawInput ?? "")) !== null) {
    flags[match[1]] = match[3] ?? match[4] ?? match[5] ?? "";
  }
  return flags;
}

function resolveMaybePath(value) {
  if (!value) return "";
  return isAbsolute(value) ? value : resolve(process.cwd(), value);
}

function buildCommand(reportDir) {
  return {
    // definitionId 是 DSH 用来配对「定义 / 执行」的稳定身份，按官方插件的写法给插件命名空间前缀。
    definitionId: "dsh-job-skill-plugin/command-job-fit",
    name: "job-fit",
    description:
      "求职作战包：简历 + JD + 公司 -> 摘要卡片 + 8 节 Markdown 报告（默认 Mock 数据）",
    // 形状必须与 @deepseek-ai/dsh-command-goal 完全一致：dsh-commands 的
    // normalizeDefinition 校验 name / description / handler，input.hint 用于斜杠菜单提示。
    // 早先写成 execute 而不是 handler，注册时抛 TypeError 被 ctx.inject 回调吞掉，
    // 于是命令从未进注册表、菜单里自然看不到 /job-fit。
    input: {
      hint: "--resume <简历路径> --jd <JD 文件路径或正文> --company <公司名> [--out <导出目录>]",
    },
    async handler(invocation) {
      const flags = parseFlags(invocation?.rawInput);
      try {
        if (!flags.resume) throw new Error("缺少 --resume <简历文件绝对路径>");
        if (!flags.jd) throw new Error("缺少 --jd <JD 文件路径或 JD 正文>");
        if (!flags.company) throw new Error("缺少 --company <公司名>");

        const resumePath = resolveMaybePath(flags.resume);
        if (!existsSync(resumePath)) throw new Error(`简历文件不存在：${resumePath}`);

        let jdText = flags.jd;
        const asPath = resolveMaybePath(flags.jd);
        if (existsSync(asPath)) jdText = readFileSync(asPath, "utf8");
        if (jdText.trim().length < 20) throw new Error("JD 内容太短（至少 20 字），请给完整 JD 文本");

        const { response, cardText } = await core.analyseJobFit({
          resume_path: resumePath,
          jd_text: jdText,
          company_name: flags.company,
          depth: "basic",
        });

        const outDir = resolveMaybePath(flags.out) || reportDir;
        mkdirSync(outDir, { recursive: true });
        const outFile = join(outDir, response.filename);
        writeFileSync(outFile, response.markdown, "utf8");

        const mode = response.card?.data_mode === "live" ? "live" : "mock";
        const lines = [
          cardText,
          "",
          `导出文件：${outFile}`,
          `分析 ID：${response.analysis_id}`,
          mode === "mock" ? "数据模式：Mock —— 公司数据为虚构样本，不是真实工商记录。" : "数据模式：live",
          "本报告由 AI 生成，需人工核实证据；匹配结论不是通过率预测。",
        ];
        return { kind: "success", text: lines.join("\n") };
      } catch (error) {
        const shaped = toDshError(error);
        return { kind: "error", text: `job-fit 失败：${shaped.message}` };
      }
    },
  };
}

export function apply(ctx, config = {}) {
  const reportDir = resolveMaybePath(
    config.reportDir || process.env.JOB_FIT_REPORT_DIR || join(HERE, "reports"),
  );

  // 1) 三个工具
  const disposers = [];
  for (const definition of core.tools) {
    const dispose = ctx.tools.register(toDshTool(definition));
    if (typeof dispose === "function") disposers.push(dispose);
  }
  ctx.effect(() => () => {
    for (const dispose of disposers.reverse()) dispose();
  });

  // 加载自证：装没装上不靠猜，宿主真的挂载了才写这一行（安装文档里的自查依据）。
  logLine(
    `plugin=${PLUGIN_ID}\ttools=${core.tools.map((t) => t.name).join(",")}\tsidecar=${process.env.SIDECAR_BASE_URL ?? "http://localhost:8000"}`,
  );

  // 2) 一个 skill
  ctx.inject(["skills"], (scope) => {
    const service = scope.get("skills");
    if (!service || typeof service.register !== "function") return;
    const dispose = service.register(parseSkillFile());
    return () => {
      if (typeof dispose === "function") dispose();
    };
  });

  // 3) 一条命令（触发编排，避免只装到 3 个工具就断链）
  ctx.inject(["commands"], (scope) => {
    const service = scope.get("commands");
    if (!service || typeof service.register !== "function") return;
    let dispose;
    try {
      dispose = service.register(buildCommand(reportDir));
    } catch (error) {
      // 注册失败必须留痕，否则"命令没出现"永远查不到原因。
      logLine(`cmdfail\tname=job-fit\terror=${error?.message ?? error}`);
      return;
    }
    // 注册自证：直接把注册表里的命令名读回来，证明它真的进了 commands 表。
    let listed = "unavailable";
    try {
      const descriptors = service.list(undefined);
      listed = descriptors.map((d) => `/${d.name}`).join(",");
    } catch (error) {
      listed = `list-failed:${error?.message ?? error}`;
    }
    logLine(`cmdcheck\tname=job-fit\tregistered=${listed}`);
    return () => {
      if (typeof dispose === "function") dispose();
    };
  });
}

export const internals = { parseFlags, toJsonSchema, parseSkillFile, buildCommand };
