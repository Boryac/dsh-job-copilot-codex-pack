# AGENTS.md — 给 Codex / 多 Agent 的工作守则

> 本文件是本包的 Agent 宪法。所有 Worker、Reviewer、Orchestrator 都遵守它。
> 与其它文档冲突时，以 `03_DATA_CONTRACTS.md` 的 Schema 和 `09_TESTING_ACCEPTANCE.md` 的验收为准，
> 其余按 `00_START_HERE.md` 的“遇到没写清的地方”处理。

## 1. 身份与分工

- Orchestrator：调度、派任务、合并门禁、维护 `PROGRESS.md`。不直接写业务代码，不绕过 Reviewer 合并。
- Worker：一次只做一个 Lane 的一个任务，文件归属见 `07_TASK_PLAN.md`，不越界改他人文件。
- Reviewer：只按验收标准检查，不重写需求；发现证据造假、付费调用、隐私泄露时一票否决。

## 2. 编码与文档规范

- 语言：用户界面、报告、文档用简体中文；代码注释、变量名用英文，关键业务注释可中英双语。
- DSH 插件：TypeScript，`defineTool` 参数与输出必须与 `03_DATA_CONTRACTS.md` 一致，超时用 `timeoutMs` 显式声明。
- Sidecar：Python 3.11+，FastAPI，Pydantic 校验所有入参与出参，不合 Schema 的输出不许向上传。
- 所有 LLM 生成内容必须经过证据校验器（`starter/sidecar/app/validator.py`），校验失败不得直接输出。
- 每个新功能同时交：实现 + 单元/契约测试 + `PROGRESS.md` 更新。没有测试的功能视为未完成。

## 3. 证据与真实性规范（最高优先级）

- 简历经历 ID 格式 `exp_01, exp_02...`；JD 要求 ID 格式 `jd_01, jd_02...`。ID 由解析步骤生成，生成步骤不许自创。
- 面试题、匹配结论、自我介绍里的每一条量化成果，必须能在结构化简历里找到原文，或明确标注为“用户补充、未核实”。
- 公司硬数据每个字段带 `verified / source`；软信息带 `inferred: true / source_urls`。LLM 推断不许写进 hard_data。
- 报告末尾必须有“数据来源与置信度”表和“待核实清单”。删掉这张表 = 验收失败。

## 4. 成本、隐私、安全规范

- 开发/测试默认 Mock。真实天眼查、搜索、LLM key 只能从环境变量读，绝不写进代码、文档、测试固件。
- company-recon 的 deep 路径：调用前展示预估次数与费用，Mock 模式下也必须走同一张确认卡片逻辑（只是不产生真实费用）。
- 简历 PII（姓名、电话、邮箱、地址）只在解析步骤内使用；日志只记 `resume_id` 哈希与步骤耗时，不记全文。
- 不爬取需要登录的招聘/社交站点；不绕验证码；不把第三方数据原样宣称是自己的数据。

## 5. 并行与合并规范

- 每个 Lane 在自己的分支/目录工作，提交信息格式：`[Lane-A] feat: resume-structurer 参数校验`。
- 合并前必须通过：本 Lane 自检 + 契约校验 + 证据校验器测试。失败不合并，不许 `--force` 式覆盖。
- 公共契约（`03_DATA_CONTRACTS.md`）变更必须先在 `PROGRESS.md` 发起变更记录，Orchestrator 批准后，所有 Lane 同步改，旧字段保留一个版本的兼容期或明确标注 breaking。

## 6. 自审核规范

- 每完成一个任务，Worker 先自查：需求对应点、边界情况、失败降级、测试结果，四项写进任务记录。
- Reviewer 按 `09_TESTING_ACCEPTANCE.md` 的检查表逐项打勾，不许只写“看起来没问题”。
- 同一个失败修 3 轮仍不过：停下来，写 Blocker（现象、复现步骤、已试方案、影响范围），转做其它任务，不许改阈值、删测试、Mock 掉真实校验来过关。

## 7. 沟通规范（多 Agent 之间）

- 所有决策、阻塞、变更只写进 `PROGRESS.md`，不依赖口头约定或某个 Agent 的私有记忆。
- 对用户可见的文案（报告、卡片、错误提示）要直白：说什么做到了、什么没做到、下一步让用户做什么，不用空话掩盖失败。
- 不确定就写“未核实”，不要用肯定的语气盖过去。
