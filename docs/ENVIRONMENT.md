# ENVIRONMENT — 环境、依赖、Mock 模式

## 1. 工具链

- Node.js 20+（插件层，TypeScript）
- Python 3.11+（sidecar，FastAPI）
- Docker + Docker Compose（sidecar 一键启动，可选但推荐）
- Git

> DSH 插件 SDK 的具体 API（defineTool 签名、卡片渲染、http-client 模式）以开发机上实际安装的 DSH SDK 文档为准。本仓库只规定"插件声明参数与输出、execute 返回 canonical 值、有 timeoutMs 约束"这一层语义，不硬编码 SDK 内部 API。升级 DSH 版本后，先核对 SDK 文档再改代码，不凭记忆写 API。

## 2. 目录结构

```
starter/
  dsh-plugin/                DSH 插件层（TypeScript，Cordis）
    src/tools/               resume-structurer / jd-decoder / company-recon
    src/skill/               job-fit-orchestrator（Skill 编排层）
    src/cards/               摘要卡片渲染
    tests/                   插件测试（node --test）
  sidecar/                   引擎层（Python，FastAPI）
    app/parsers/             简历解析（SmartResume 封装 + fallback）
    app/recon/               公司背调采集、消歧、缓存、记账
    app/orchestrator/        匹配、生成、报告组装
    app/validator.py         证据校验器
    tests/                   sidecar 测试（pytest）
  docker-compose.yml
  .env.example
templates/                   报告模板、golden 用例、JD 与简历样例
scripts/                     自检、契约校验、Mock 演示、golden 回归
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

插件侧启动与 DSH 桌面端安装见 [docs/INSTALL.md](INSTALL.md)。

## 5. SmartResume 部署选项

- 选项 1（默认）：文本提取 + LLM 结构化，不要求本地 GPU，输出标注 `parsing_mode: fallback`。
- 选项 2（可选）：SmartResume 本地部署（Qwen + 版面检测模型），需要 GPU 与模型下载时间。实测召回与 fallback 打平、耗时高出 3 到 4 个数量级，结论与数据见 [docs/ENV_FEASIBILITY.md](ENV_FEASIBILITY.md) 第 3 节。
- 两种选项的输出 Schema 必须一致，切换选项不许改报告结构。

## 6. 常见环境问题

- 端口占用：改 `SIDECAR_PORT`，不要改代码里的硬编码端口。
- 模型下载慢或失败：先用 Mock 与 fallback 跑通流程，模型问题单独记录，不阻塞其它部分。
- 本机设有代理时访问 127.0.0.1 会被代理拦成 502，curl 加 `--noproxy "*"`，详见 [docs/INSTALL.md](INSTALL.md) 第 5 节。
- DSH SDK 版本不一致：以本地 SDK 文档为准，不凭记忆写 API。
