# 10_AGENT_WORKFLOW — Orchestrator / Worker / Reviewer 协作流程

## 1. 角色与权限

- Orchestrator：唯一能改 `PROGRESS.md` 的“进度与决策”区、唯一能批准合并与契约变更的人（角色，不是某个人名）。
  不直接写业务代码，不绕过 Reviewer 合并。
- Worker：一次只领一个任务，只改自己 Lane 的文件。需要改公共契约时先提变更记录，等批准。
- Reviewer：按 `09_TESTING_ACCEPTANCE.md` 第 5 节检查表逐项打勾。发现证据造假、付费调用、
  隐私泄露时一票否决，不许“先合并后修”。

## 2. 自推进主循环（无需人工干预时的默认循环）

```
1. Orchestrator 从 07_TASK_PLAN.md 选下一个可做的 P0 任务（依赖已 done）
2. 派给对应 Lane 的 Worker，Worker 在分支/目录里实现 + 写测试
3. Worker 自检：bash scripts/verify.sh + 本 Lane 测试 + 边界与降级自查
4. Worker 更新 PROGRESS.md：任务状态、改了什么、测试结果、遗留问题
5. Reviewer 交叉检查：契约、证据、隐私、成本四项 + 09 检查表
6. 通过 → 合并进主线，选下一个任务；不通过 → 回到第 2 步（最多 3 轮）
7. 3 轮不过 → 写 Blocker，转做其它任务，不改阈值、不删测试
8. 所有 P0 done + 验收全部通过 → 输出验收报告，循环结束
```

## 3. 并行规则

- 5 条 Lane 可以同时跑，但同一文件同一时间只允许一个 Lane 改。
- 公共契约变更期间：其它 Lane 暂停对该契约的依赖改动，等 Orchestrator 宣布同步完成。
- 每天（或每个里程碑）做一次合并检查：各 Lane 的自检结果、冲突、Blocker 全部汇总进 PROGRESS.md。

## 4. 提交与记录规范

- 提交信息：`[Lane-A] feat: resume-structurer 参数校验` / `[Lane-E] test: 证据校验器反例`
- 每个任务的记录必须包含：需求对应点、实现摘要、测试命令与结果、边界与降级处理、遗留问题
- 决策记录格式（PROGRESS.md 的 Decisions 区）：
  `日期 | 问题 | 选择的方案 | 为什么 | 影响范围 | 是否需要后续复核`

## 5. Codex 接入时的第一批指令（复制给 Codex 即可开始）

```
你是一组并行 Agent 的 Orchestrator。先读本包的 00_START_HERE.md 和 AGENTS.md，
再读 01_PRD.md、02_ARCHITECTURE.md、03_DATA_CONTRACTS.md、07_TASK_PLAN.md。
形态已定：DSH 插件优先，报告可导出 Markdown；sidecar API 与前端解耦。
按 10_AGENT_WORKFLOW.md 第 2 节的自推进主循环工作，不需要人工干预时不要停下来问问题：
遇到歧义选更保守、更可验证的方案，并记进 PROGRESS.md 的 Decisions。
开发默认 Mock 模式，绝不调用真实付费接口，绝不把真实密钥或简历写进仓库。
完成标准是 09_TESTING_ACCEPTANCE.md 的 A1-A7 全部通过，不是代码写完了。
```

## 6. 人工介入点（本包默认“无需人工”，但以下情况必须停下来记 Blocker，而不是擅自决定）

- 真实天眼查 key、搜索 key、LLM key 的开通与付费决策（开发阶段一律 Mock，不许擅自开通）
- 许可证冲突：某个 fork 目标的许可证不允许当前用法时，停下来记 Blocker，换备选方案，不许忽略许可证
- DSH SDK 的 API 与本包假设严重不一致，且影响插件注册时，记 Blocker 并给出最小改动方案
- 以上 Blocker 不阻塞其它 Lane，Orchestrator 继续调度不依赖它的任务
