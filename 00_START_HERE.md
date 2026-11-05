# 00_START_HERE — Codex 入口（先读这份，再动代码）

## 使命（一句话）

用户只给 3 样东西：**个人简历（PDF/DOCX/图片）+ 岗位 JD（粘贴文本，URL 为辅）+ 公司名称**，
系统自动完成公司背调、岗位拆解、人岗匹配，输出一份**能直接拿去面试的作战包**：
分析报告、应对方案、针对性 HR 面试题、STAR 回答、背靠知识点、自我介绍。

> 这不是一个“给个匹配分”的工具。没有证据引用的结论不许进报告，没有来源标注的公司信息不许写成事实。

## 本包是什么

这是一个**自包含开发包**。Codex / 多 Agent 打开本包后，不需要再问用户要需求细节，
按本包推进即可把项目做到 `09_TESTING_ACCEPTANCE.md` 里的验收标准全部通过。

本包不包含任何真实密钥、真实简历、真实天眼查账号。所有外部调用在开发和测试阶段默认走 Mock。

## 阅读顺序（30 分钟）

1. 本文件 `00_START_HERE.md` — 使命、红线、并行分工、自推进闭环
2. `01_PRD.md` — 需求与非目标、v1.0 完成定义
3. `02_ARCHITECTURE.md` — DSH 插件层 + Python sidecar 架构、超时预算
4. `03_DATA_CONTRACTS.md` — 三个工具的 JSON Schema，改 Schema 先改这里
5. `07_TASK_PLAN.md` — 任务拆分、并行 Lane、文件归属、合并门禁
6. `10_AGENT_WORKFLOW.md` — Orchestrator / Worker / Reviewer 怎么协作、怎么自审核
7. 其余按需查：报告规范、公司背调、证据质量、环境、测试、风险、Fork 地图

## 最终交付形态（v1.0）

- DSH 工具插件 3 个：`resume-structurer`、`company-recon`、`jd-decoder`
- Skill 编排层 1 个：`job-fit-orchestrator`（单 Agent 顺序编排，v1.0 不做多 Agent 路由）
- Python sidecar 1 个：fork 后的 job-copilot services 层 + SmartResume 解析，DSH 插件通过 HTTP 调用它
- 报告：DSH 内先给一页摘要卡片，再展开完整 Markdown 报告（8 节，见 `04_REPORT_SPEC.md`）
- Mock 模式可全流程跑通；真实天眼查 / 搜索 API 只在用户显式配置 key 后启用，且 deep 路径永远要先展示费用预估

## 并行分工（无需人工干预的默认模式）

把工作切成 5 条 Lane，文件归属互不重叠，见 `07_TASK_PLAN.md` 第 3 节。
Orchestrator 只做调度、合并门禁和自审核，不直接写业务代码。

| Lane | 负责 | 核心产出 | 不碰 |
|---|---|---|---|
| A | DSH 插件层 | 3 个工具的 defineTool、参数校验、卡片渲染、超时与降级 | sidecar 内部实现 |
| B | Sidecar 与解析 | FastAPI 骨架、SmartResume 封装、fallback 解析 | DSH 插件代码 |
| C | 公司背调 | company-recon basic/deep、消歧、缓存、额度记账 | 面试题生成 prompt |
| D | 编排与生成 | orchestrator、匹配、四维评分、自我介绍、面试题、知识点 | 插件注册、sidecar 部署 |
| E | 质量与测试 | Schema 校验、证据校验器、golden set、回归、验收报告 | 业务逻辑（只修测试与校验器本身的 bug） |

合并规则：每个 Lane 完成一个里程碑后，必须先跑本 Lane 的自检（`scripts/verify.sh`），
再由 Reviewer 按 `09_TESTING_ACCEPTANCE.md` 做交叉检查，通过才能合并进主线。
冲突只允许 Orchestrator 在 `PROGRESS.md` 里记录裁决，不允许静默覆盖他人文件。

## 自推进闭环（没有人工时就按这个循环）

```
做任务 -> 跑自检 -> 修失败 -> 更新 PROGRESS.md -> 进入下一个任务
   ^                                              |
   |—— 验收不通过：回到失败点，最多修 3 轮 ————|
   |—— 3 轮仍不通过：把问题写进 PROGRESS.md 的 Blockers，
        标记该任务为 blocked，继续其它不依赖它的任务，
        不许为了“看起来完成”而放宽验收标准 ————|
```

**禁止的捷径（红线，见 `11_RISKS_GUARDRAILS.md`）：**

1. 不许编造经历、公司数据、面试题证据引用。证据 ID 不存在 = 失败，不是警告。
2. 不许在开发/测试中调用真实付费接口。deep 路径默认 Mock，真实调用需要显式配置 + 费用确认卡片。
3. 不许把简历全文、电话、邮箱写进日志、测试固件、git 历史或发给搜索接口。搜索只发公司名和 JD 关键词。
4. 不许绕过登录墙爬 Boss/LinkedIn 等站点。JD 主路径是粘贴文本，URL 只是辅助，失败就明确提示粘贴。
5. 不许改验收阈值来让测试变绿。70% / 80% 的阈值只能按 `09_TESTING_ACCEPTANCE.md` 的 rubric 复核，不能口头放宽。
6. 不许把“已发送/已上线/已验证”写进未完成的功能。状态词只写已核实的部分。

## 停止条件（什么时候算“全部完成”）

同时满足以下全部，才算完成，否则继续循环：

- [ ] `07_TASK_PLAN.md` 里 P0 任务全部为 done，且每个任务有对应的测试或校验证据
- [ ] `09_TESTING_ACCEPTANCE.md` 5 条验收标准全部通过，有可复现的运行记录
- [ ] Mock 模式下端到端流程稳定跑通，basic 路径有明确的超时与降级行为
- [ ] `PROGRESS.md` 里没有未解决的 P0 Blocker；P1/P2 缺口全部列在“已知缺口”里，不藏起来
- [ ] 没有真实密钥、真实简历、真实付费调用记录进入仓库

## 遇到本包没写清的地方，怎么办

优先级：`03_DATA_CONTRACTS.md` 的 Schema > `04_REPORT_SPEC.md` 的报告结构 >
`01_PRD.md` 的目标与非目标 > 其它文档。
仍有歧义时，选择**更保守、更可验证**的方案，并在 `PROGRESS.md` 的 Decisions 里记下
“问题、选择的方案、为什么、影响范围”，不要静默自创一个新口径。

## 快速启动（开发机）

```bash
# 1. 复制环境变量模板，不填真实 key 也能跑 Mock
cp starter/.env.example starter/.env
# 2. 只做包内自检，不启动任何外部服务
bash scripts/verify.sh
# 3. 看 starter 骨架，先跑通 Mock 端到端，再按 07_TASK_PLAN.md 分 Lane 推进
python3 scripts/validate_contracts.py
python3 scripts/run_mock_demo.py
```

下一份必读：`01_PRD.md`。
