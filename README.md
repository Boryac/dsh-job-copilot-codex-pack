# DSH 求职背调与面试准备 Skill 套件 — Codex 开发包 v1.0

用户输入简历 + JD + 公司名称，自动输出一份能直接拿去面试的作战包：
公司背调、岗位拆解、人岗匹配、应对方案、针对性 HR 面试题与 STAR 回答、背靠知识点、自我介绍。

## 包内结构

```
00_START_HERE.md              Codex 入口：使命、红线、并行分工、自推进闭环
AGENTS.md                     Agent 工作守则
01_PRD.md                     需求、目标与非目标、v1.0 完成定义
02_ARCHITECTURE.md            架构、超时预算、部署形态
03_DATA_CONTRACTS.md          三个工具的 JSON Schema（改 Schema 先改这里）
04_REPORT_SPEC.md             8 节报告规范与模板
05_COMPANY_RECON_SPEC.md      公司背调三层、消歧、缓存、额度记账
06_EVIDENCE_QUALITY.md        证据锁定、评分 rubric、反幻觉校验
07_TASK_PLAN.md               任务拆分、并行 Lane、文件归属、4 周计划
08_ENVIRONMENT.md             环境、依赖、Mock 模式、启动步骤
09_TESTING_ACCEPTANCE.md      测试、golden set、验收标准、自审核表
10_AGENT_WORKFLOW.md          Orchestrator / Worker / Reviewer 协作流程
11_RISKS_GUARDRAILS.md        风险、隐私、成本、合规护栏
12_FORK_MAP.md                开源借鉴与 fork 锁定清单
PROGRESS.md                   进度、决策、Blocker 追踪表（Agent 持续更新）
templates/                    报告模板、golden 用例模板、消歧模板
starter/                      DSH 插件骨架 + Python sidecar 骨架 + Docker + .env 模板
scripts/                      包自检、契约校验、Mock 演示脚本
```

## 给 Codex 的接入方式

1. 把本压缩包解压到一个空工作目录（不要直接解压进已有项目，避免覆盖）。
2. 让 Codex 先读 `00_START_HERE.md` 和 `AGENTS.md`，再按 `07_TASK_PLAN.md` 分 Lane 推进。
3. 开发中默认 Mock 模式：`bash scripts/verify.sh` 应始终通过；真实 key 只通过环境变量配置。
4. 完成标准见 `09_TESTING_ACCEPTANCE.md`，不要以“代码写完了”代替“验收通过了”。

## 核心设计判断（不要在开发中悄悄推翻）

- 不从零做求职应用：fork / 借鉴成熟开源项目的 services 层，DSH 插件只做声明与调用。
- 不把完整应用塞进插件：DSH 插件层（TypeScript + defineTool）通过 HTTP 调用本地 sidecar。
- 公司信息分层：硬数据可验证、软信息标推断、低置信信息只作参考，三者绝不混写。
- 面试题证据锁定：每个问题必须带 `evidence_ref`，指向真实存在的简历经历 ID 或 JD 句子 ID。
- 深度背调按需付费：默认 basic，deep 必须先展示预估费用并走确认逻辑，开发阶段一律 Mock。
