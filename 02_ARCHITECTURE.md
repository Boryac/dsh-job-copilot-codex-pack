# 02_ARCHITECTURE — 技术架构（DSH 视角）

## 1. 总体架构

```
用户上传 / 输入（简历文件、JD 文本、公司名称）
      │
      ▼
┌──────────────────────────────────────────────────┐
│  DSH 插件层（TypeScript + defineTool）             │
│  resume-structurer  company-recon  jd-decoder    │
│  job-fit-orchestrator（Skill 编排层，非工具）      │
└──────────────┬───────────────────────────────────┘
               │ HTTP 调用（本地或容器内服务）
               ▼
┌──────────────────────────────────────────────────┐
│  fork 后的 job-copilot services/ 层（sidecar）     │
│  简历编排 / JD 编排 / 匹配引擎 / 企业研究 / 面试陪练编排 │
└──────┬──────────────────┬────────────────────────┘
       │                  │
       ▼                  ▼
 SmartResume API      天眼查 MCP / 搜索 API（Tavily 或内置搜索）
 (Python, fork)       （按需、分层调用，默认 Mock）
```

## 2. 为什么是 sidecar，而不是把 Python 塞进插件

- DSH 插件包不适合内置 Python 运行时、OCR 模型和 vLLM；sidecar 让重型依赖留在容器里。
- DSH 插件只做三件事：声明参数、校验输入、把请求转发给 sidecar 并渲染结果卡片。
- v2.0 再评估把核心模块直接移植为 TypeScript；v1.0 不做这个重构，避免同时啃两个大重构。

## 3. 部署形态

- v1.0：fork 后的后端作为本地 sidecar 服务运行，DSH 插件通过 http-client 模式调用。
  提供 `starter/docker-compose.yml`，一键起 sidecar + 健康检查端点 `/health`。
- 配置只走环境变量（见 `08_ENVIRONMENT.md`），key 缺失时自动进入 Mock 模式并在卡片上明示。
- 不要求用户本地装 GPU：SmartResume 本地模型为可选项，默认走“文本提取 + LLM 结构化”或远程解析，
  输出标注 `parsing_mode`，不把 GPU 作为 MVP 硬依赖。

## 4. 超时与降级预算（v1.0 必须先定，再写代码）

PRD 里“单工具 30 秒、端到端 60 秒”在真实搜索 + 多轮 LLM 下几乎一定超时。
v1.0 按以下预算实现，超出即降级，不许静默等到整体失败：

| 步骤 | 目标预算 | 超时后行为 |
|---|---|---|
| resume-structurer | ≤ 30 秒 | fallback 解析，标注 `parsing_mode: fallback`，继续流程 |
| jd-decoder | ≤ 20 秒 | JD 文本已在本地，直接结构化，不依赖 URL 抓取重试 |
| company-recon basic | ≤ 30 秒 | 搜索软信息超时则只出硬数据 + “软信息未获取”提示，不阻塞报告 |
| 匹配 + 生成（自我介绍、面试题、知识点） | 分段生成、可流式输出 | 先出摘要与匹配表，再补面试题；单段超时则该段标注“未生成”并给出重试入口 |
| 端到端 basic 路径 | 目标 P90 ≤ 120 秒，卡片上实时显示进度 | 任何一步失败都不许让整份报告空白：出部分报告 + 失败原因 + 待核实清单 |

> 注意：上面是本包的工程预算，不是对外承诺的 SLA。实现后以实测 P50/P90 为准更新本节，
> 不许为了凑 60 秒而删掉校验步骤。

## 5. 数据流与状态

- 一次分析 = 一个 `analysis_id`（UUID），所有工具调用、缓存、日志、报告都挂在这个 ID 下。
- 结构化简历、JD、公司数据是中间产物，必须可单独查看和复核，不能只存在 LLM 的上下文里。
- 报告生成是幂等的：同一组输入（简历哈希 + JD 哈希 + 公司 ID + depth）重复请求时，
  优先返回缓存的报告骨架，deep 付费调用绝不因重复点击而重复扣费（见 `05_COMPANY_RECON_SPEC.md`）。

## 6. 错误契约

每个工具的失败返回必须包含：`code`（如 `TIMEOUT / PARSE_FAILED / COMPANY_AMBIGUOUS / QUOTA_EXHAUSTED / UPSTREAM_ERROR`）、
`message`（给用户看的直白话）、`retryable`（是否可重试）、`fallback`（已采取的降级）。
编排层收到失败时按第 4 节降级，不许把原始异常堆栈直接推给用户。

## 7. 模块边界（Lane 之间不许越界）

- Lane A 只拥有 `starter/dsh-plugin/` 与插件注册、卡片渲染。
- Lane B 只拥有 sidecar 的解析与 FastAPI 骨架。
- Lane C 只拥有 company-recon 的采集、消歧、缓存、记账。
- Lane D 只拥有 orchestrator、匹配、生成 prompt 与报告组装。
- Lane E 只拥有校验器、测试、golden set 与验收报告。
- 公共契约变更走 `AGENTS.md` 第 5 节流程。
