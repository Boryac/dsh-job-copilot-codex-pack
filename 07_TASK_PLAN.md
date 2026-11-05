# 07_TASK_PLAN — 任务拆分、并行 Lane、4 周计划

> 形态已定（2026-11-05 用户确认）：DSH 插件优先，报告可导出 Markdown。
> DSH 内摘要卡片 + 完整 Markdown 文件；sidecar API 与前端解耦，未来加网页壳不重写引擎。

## 1. 任务状态词

- `todo` 未开始 / `doing` 进行中 / `done` 已通过本 Lane 自检 + Reviewer 交叉检查 / `blocked` 有 Blocker 且已记录
- 一个任务只有同时满足“实现 + 测试 + PROGRESS.md 更新”才能标 done。只写完代码不算 done。

## 2. 4 周计划（P0 必须做，P1 有时间做，P2 v2 再做）

### 第 1 周：底座搭建与简历 / JD 工具（Lane A + B + E 先行）

- [ ] T1.1 [P0, Lane E] 锁定 fork 仓库：按 `12_FORK_MAP.md` 逐项核对仓库地址、提交、许可证，输出锁定表（见 12 第 4 节）
- [ ] T1.2 [P0, Lane B] sidecar 骨架跑通：FastAPI + `/health` + Mock 解析端点，Docker 一键启动
- [ ] T1.3 [P0, Lane B] SmartResume 封装：`ResumeAnalyzer.pipeline` 调用 + `extract_types` 按需抽取 + fallback 路径
- [ ] T1.4 [P0, Lane A] resume-structurer 插件：defineTool、参数校验、超时 30 秒、卡片渲染
- [ ] T1.5 [P0, Lane A] jd-decoder 插件：粘贴文本主路径、URL 辅助路径、失败提示粘贴
- [ ] T1.6 [P0, Lane E] 契约测试：03 的三个 Schema 全部有正例 + 反例测试
- 里程碑 M1：DSH 中可上传 PDF 并拿到结构化简历 JSON；JD 粘贴可出结构化拆解

### 第 2 周：公司背调（basic）+ 编排层（Lane C + D）

- [ ] T2.1 [P0, Lane C] company-recon basic：消歧 + 基础工商（Mock）+ 搜索软信息 + 缓存 + 额度记账字段
- [ ] T2.2 [P0, Lane D] job-fit-orchestrator：固定顺序编排（并行三工具 → 匹配 → 自我介绍 → 面试题 → 报告）
- [ ] T2.3 [P0, Lane D] 报告生成器：按 `04_REPORT_SPEC.md` 模板输出 8 节 + Markdown 导出文件命名规则
- [ ] T2.4 [P0, Lane A] DSH 摘要卡片：执行摘要 + 各节锚点 + 导出文件链接
- [ ] T2.5 [P0, Lane E] 端到端 Mock 演示：`scripts/run_mock_demo.py` 全流程跑通并产出样例报告
- 里程碑 M2：输入简历 + JD + 公司名，产出一份可读报告，公司信息分区正确（hard vs soft）

### 第 3 周：证据锁定与面试题质量（Lane D + E）

- [ ] T3.1 [P0, Lane E] 证据校验器完整版：按 `06_EVIDENCE_QUALITY.md` 第 2 节全部规则实现
- [ ] T3.2 [P0, Lane D] 面试题生成重构：生成时只给已生成 ID 列表，生成后走校验器，重生成与降级逻辑
- [ ] T3.3 [P0, Lane D] 匹配基线：关键词重合度 + 语义匹配 + 四维档位 rubric 落实
- [ ] T3.4 [P0, Lane E] 人工评审：5 组真实“简历-JD”对，按 06 第 4 节三项打分，输出评审表
- [ ] T3.5 [P1, Lane D] 知识点分级：must / bonus / frequent 落实，通用知识点标注规则
- 里程碑 M3：评审通过率 ≥ 70%（“问题与经历相关”判定，三项全通过才算通过）

### 第 4 周：deep 背调按需付费（Mock 先行）+ 回归测试（Lane C + E）

- [ ] T4.1 [P0, Lane C] deep 预估卡片：预估次数、费用、字段清单、取消零调用、幂等缓存
- [ ] T4.2 [P0, Lane E] golden set：5 组输入-期望输出（见 09），接入回归检查
- [ ] T4.3 [P0, Lane E] 回归与修复：回归通过率 ≥ 80%，修复第 3 周评审暴露的 top 问题
- [ ] T4.4 [P1, Lane A/B] 超时与降级实测：按 02 第 4 节预算实测 P50/P90，更新架构文档
- [ ] T4.5 [P0, Lane E] 验收报告：按 09 第 4 节逐项打勾，附运行记录
- 里程碑 M4：端到端流程稳定，回归通过率 ≥ 80%，basic 路径有可复现的耗时与降级记录

### v2.0（P2，不在本包验收内，只记录方向）

- 多轮对话式模拟面试；多 Agent 路由（job-copilot Supervisor 架构参考）
- 核心模块 TypeScript 移植评估；薄网页壳（复用同一套 sidecar API）
- 真实天眼查 deep 上线（需用户显式配置 key + 费用确认，仍不默认触发）

## 3. 并行 Lane 与文件归属（冲突预防的核心）

| Lane | 负责人角色 | 拥有目录/文件 | 绝不碰 |
|---|---|---|---|
| A | DSH 插件开发 | `starter/dsh-plugin/`、插件注册、卡片渲染 | sidecar 内部、校验器、测试固件 |
| B | Sidecar 与解析 | `starter/sidecar/app/main.py`、解析封装、Docker | 插件代码、报告模板 |
| C | 公司背调 | company-recon 采集、消歧、缓存、记账模块 | 面试题 prompt、匹配评分 |
| D | 编排与生成 | orchestrator、匹配、生成 prompt、报告组装 | 插件注册、sidecar 部署 |
| E | 质量与测试 | `starter/sidecar/app/validator.py`、`scripts/`、golden set、验收报告 | 业务逻辑（只修校验器与测试本身的 bug） |

- 公共文件（`03_DATA_CONTRACTS.md`、`04_REPORT_SPEC.md`）变更：先在 PROGRESS.md 发起变更记录，
  Orchestrator 批准后各 Lane 同步改，旧字段保留一个版本兼容期或明确标注 breaking。
- 每天（或每个里程碑）合并一次：各 Lane 先自检，再 Reviewer 交叉检查，通过才进主线。

## 4. 依赖关系（不要并行踩到依赖）

```
T1.1 锁定仓库 ──> T1.2/T1.3 sidecar ──> T1.4/T1.5 插件
T1.6 契约测试 ──> T2.1/T2.2 ──> T2.3 报告 ──> T2.5 演示
T2.2 ──> T3.1 校验器 ──> T3.2 面试题重构 ──> T3.4 评审
T2.1 ──> T4.1 deep 卡片（Mock） ──> T4.2 golden ──> T4.5 验收
```

无依赖的任务可以并行；有依赖的任务，前置任务未 done 时后置任务只能做设计与 Mock 接口，不许假装已集成。
