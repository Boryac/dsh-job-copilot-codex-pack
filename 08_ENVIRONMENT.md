# 08_ENVIRONMENT — 环境、依赖、Mock 模式

## 1. 工具链（版本下限，Lane B 在 T1.2 时复核并锁定）

- Node.js 20+（DSH 插件层，TypeScript）
- Python 3.11+（sidecar，FastAPI）
- Docker + Docker Compose（sidecar 一键启动，可选但推荐）
- Git（分支与合并用 Lane 隔离）

> DSH 插件 SDK 的具体 API（defineTool 签名、卡片渲染、http-client 模式）以开发机上实际安装的
> DSH SDK 文档为准。本包只规定“插件声明参数与输出、execute 返回 canonical 值、有 timeoutMs 约束”
> 这一层语义，不硬编码 SDK 内部 API。Lane A 的第一个任务就是核对 SDK 文档并把核对结果写进 PROGRESS.md。

## 2. 目录结构（目标项目，Codex 按此搭建，不要自创一套）

```
dsh-job-skill/
  dsh-plugin/                 # Lane A：TypeScript 插件
    src/tools/resume-structurer.ts
    src/tools/company-recon.ts
    src/tools/jd-decoder.ts
    src/skill/job-fit-orchestrator.md
    src/cards/summary-card.ts
  sidecar/                    # Lane B/C：Python FastAPI
    app/main.py
    app/parsers/              # SmartResume 封装 + fallback
    app/recon/                # company-recon 采集、消歧、缓存、记账
    app/orchestrator/         # Lane D：匹配、生成、报告组装
    app/validator.py          # Lane E：证据校验器
    tests/
  templates/report-template.md
  .env.example
  docker-compose.yml
```

## 3. 环境变量（只走环境变量，绝不写进代码）

见 `starter/.env.example`，关键项：

```
# 模式：mock（默认）| live
APP_MODE=mock
SIDECAR_PORT=8000
SIDECAR_BASE_URL=http://localhost:8000
# 以下只在 live 模式下填，mock 模式留空即可跑通全流程
LLM_API_KEY=
LLM_BASE_URL=
TIANYANCHA_MCP_URL=
TIANYANCHA_API_KEY=
SEARCH_API_KEY=
# 缓存与额度
COMPANY_CACHE_DAYS=7
```

- `APP_MODE=mock` 时：所有天眼查、搜索、LLM 调用走 Mock 数据，deep 费用为 0 但仍走预估卡片逻辑。
- `APP_MODE=live` 时：key 缺失的模块自动降级为 Mock 并在卡片上明示，不许静默失败或编数据。

## 4. 启动步骤（Mock 模式，零外部依赖）

```bash
# 1. 复制环境变量模板
cp starter/.env.example starter/.env
# 2. 包自检（不启动外部服务）
bash scripts/verify.sh
# 3. 契约校验 + Mock 演示
python3 scripts/validate_contracts.py
python3 scripts/run_mock_demo.py
# 4. 启动 sidecar（真实开发时）
cd starter/sidecar && pip install -r requirements.txt && uvicorn app.main:app --port 8000
curl http://localhost:8000/health
# 或 Docker
docker compose -f starter/docker-compose.yml up --build
```

## 5. SmartResume 部署选项（Lane B 在 T1.3 时二选一并记录）

- 选项 1（推荐 MVP）：远程解析 / 文本提取 + LLM 结构化，不要求本地 GPU，输出 `parsing_mode: fallback` 时要标注。
- 选项 2（本地模型）：SmartResume 本地部署（Qwen + 版面检测模型），需要 GPU/显存与模型下载时间，
  只在有 GPU 的机器上启用，不作为 MVP 硬依赖。
- 两种选项的输出 Schema 必须一致（03），切换选项不许改报告结构。

## 6. 常见环境问题（先查这里，再报 Blocker）

- 端口占用：改 `SIDECAR_PORT`，不要改代码里的硬编码端口。
- 模型下载慢/失败：先用 Mock 与 fallback 跑通流程，模型问题记为 P1 Blocker，不阻塞其它 Lane。
- DSH SDK 版本不一致：以本地 SDK 文档为准，更新 PROGRESS.md 的 SDK 核对记录，不要凭记忆写 API。
