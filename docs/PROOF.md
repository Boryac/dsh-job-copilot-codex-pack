# PROOF — 外部依赖实证清单

> 口径（用户定的三条，本文严格遵守）：一项只有同时具备 **可复现命令 + 原始日志/产物 + 结论加局限** 才算「已证」；
> 缺任何一件就写「未实证」。全文没有第二种状态词，也不接受「大致跑通了」这种描述。
> 本文件由 `scripts/check_proof.py` 机械校验（`scripts/verify.sh` 第 3.9 步）：证据文件缺失、状态词含糊、
> 未实证却写「已完成/已构建」，都会让自检直接失败。

- 实证日期：2026-11-05（GMT+8）
- 机器：Windows 11 / Python 3.13.14 / 16 逻辑核 / 15.4GB RAM / NVIDIA RTX 3060 Laptop 6GB（驱动 616.92，CUDA UMD 13.4）
- 关键环境事实：**本机没有任何容器运行时**（`docker`、`podman`、`nerdctl` 均不在 PATH，`C:\Program Files\Docker` 不存在，`wsl.exe` 被安全策略禁止），
  且 **本仓库没有 git remote**，所以 CI 也不会被触发。

## 结论总表

| 项 | 状态 | 证据文件 | 仍缺/局限 |
|---|---|---|---|
| Docker 镜像构建与容器运行 | 未实证 | `docs/proof/docker-static.json`, `docs/proof/docker-static.log`, `.github/workflows/docker-build.yml` | 本机无容器运行时且无 git remote，`docker build` 与 CI 均未执行；现有证据只覆盖 25 项静态校验（`status=static_only`） |
| SmartResume 本地模型解析 | 已证 | `docs/proof/model-manifest.json`, `docs/proof/smartresume-cpu.json`, `docs/proof/smartresume-gpu.json` | 只测 3 份合成简历的文本型 PDF；上游仅 3 类抽取、不含 projects/skills；关键实体召回与 fallback 打平（0.9167 vs 1.0 差 1 条指标），耗时高 3–4 个数量级 |
| 天眼查真实调用（1 家 basic + 1 家 deep） | 未实证 | `docs/proof/tianyancha-live.json`, `docs/proof/tyc-mock-isolation.json` | 本机无 `TIANYANCHA_API_KEY`/`TIANYANCHA_MCP_URL`，未发任何真实请求；且 live 接口路径与计费单价均未与官方核对 |
| live 真实性能（真实搜索 + 真实 LLM 的 P50/P90） | 未实证 | `docs/proof/live-perf-preflight.log`, `docs/PERFORMANCE.md` | 缺 LLM/搜索密钥；更关键的是 `SearchProvider._live_search` 目前主动抛错（搜索契约未核验），塞 key 也跑不通 |
| 真人复核（人工评审 17 题） | 未实证 | `docs/HUMAN_REVIEW_PACK.md`, `docs/review-pack/golden_06_bd_strong.md`, `docs/review-pack/golden_07_gap.md` | 没有任何签字件（`docs/review-pack/signed-*.md` 不存在）；AI 不自评、不代签 |

统计：**已证 1 / 未实证 4**。四项未实证里，三项是「缺外部凭证」（密钥、容器运行时、真人），一项是「缺契约核对」（搜索接口）。

- 复现命令：`python3 scripts/check_proof.py`（校验本文自身），逐项命令见下文各节
- 关键日志：`== PROOF 守门通过（5 项，状态词合法，证据文件齐全，三件套完整）`

## 1. Docker 镜像构建与容器运行

**状态：未实证。**

为什么不是「已证」：用户明确要求「无 docker 时改写 CI 工作流由 CI 构建，CI 日志就是证据，本地不许冒充已构建」。
本机没有 docker，我写了 CI 工作流，但**仓库没有 git remote，工作流一次都没运行**——没有 CI 日志，就没有证据。
所以这里只能挂在「未实证」，同时把未来拿到证据时的机械判据先立起来。

已经做到的（属静态校验，不等于构建通过）：

- `scripts/check_docker_assets.py`：25 项检查全过，`status=static_only`、`build.attempted=false`。
  其中 D1–D9 覆盖 Dockerfile（固定基础镜像、先依赖后代码、非 root、EXPOSE 8000、HEALTHCHECK、不拷 `.env`、无硬编码密钥、`.dockerignore`），
  C1–C5 覆盖 compose（context/dockerfile 路径、端口可覆盖、无密钥），W1–W8 覆盖 CI 工作流（YAML 可解析、有 build/run、探活并校验 200、容器内跑 verify、上传 artifact、记录镜像 ID）。
- `.github/workflows/docker-build.yml`：`docker build` → `docker run` → 容器内探活 `/health` 且断言 200 → 容器内跑 `scripts/verify.sh` → 抓 `docker logs` 与镜像 ID → 以 `docker-evidence` artifact 上传。
- `scripts/check_ci_evidence.py`：把「三件套」落成五件套机械判据（build.log / image-id.txt / container.log / health.json+health-status.txt / verify.log），
  镜像 ID 必须匹配 `sha256:<64hex>`，构建日志必须有成功标记且无 `ERROR:` 行，health 必须 200，容器日志必须有 uvicorn 启动，verify.log 必须以 `== verify passed` 收尾。

- 复现命令：
  ```bash
  python3 scripts/check_docker_assets.py --json docs/proof/docker-static.json
  # 拿到 CI artifact 解压到 .tmp/docker-evidence 之后：
  python3 scripts/check_ci_evidence.py --dir .tmp/docker-evidence
  python3 scripts/check_docker_assets.py --ci-evidence .tmp/docker-evidence   # 通过才会把 status 改成 built
  ```
- 关键日志：
  ```text
  docker 可用：否 — PATH 中找不到 docker 可执行文件
  ok W8 工作流记录镜像 ID
  本机构建：未执行（PATH 中找不到 docker 可执行文件）—— 静态校验不等于构建通过
  CI 证据包：未提供 —— 未实证
  镜像构建：未实证（缺镜像 ID / 构建日志 / 容器日志三件套）—— 不许写成『已构建』
  ```
  反向验证（证明校验器不会空转）：空文件 → `status: incomplete`、退出码 2；内容拼凑但构建日志无成功标记且 health=500 → `status: contradictory`、退出码 1；五件套齐全 → 退出码 0。

**仍缺什么**：① 一台有 docker 的机器，或 ② 给仓库配一个 remote 并推一次触发 `docker-build`，把 artifact 取回后按上面命令校验。
两项都做不到之前，Docker 一项永远写「未实证」。

## 2. SmartResume 本地模型解析

**状态：已证（CPU 与 GPU 各跑一遍，3 份简历全部 `parsing_mode=smartresume` 且非空壳）。**

### 2.1 模型来源与哈希核对

- 仓库：ModelScope `Alibaba-EI/SmartResume`，revision `df45f06c6889d89c2a4d79de485e5174ada7d030`
- 权重：`Qwen3-0.6B`，9 个文件、共 1152.1 MiB
- `model.safetensors`：1,192,135,096 字节，本地 sha256 `a7c610ac45e69b57becd8e9cbae37fb85a0634615e7039c5f6d7d0940c249045`
- 核对方式：先取 ModelScope 文件接口的远端 `Sha256`，再对本地逐文件复算，**9/9 全部一致**（`all_ok: true`）。
  该包不是 pip 上的同名第三方包：wheel METADATA 的 Homepage 就是 `github.com/alibaba/SmartResume`，Apache-2.0。

- 复现命令：
  ```bash
  .tmp/sr-venv/Scripts/python.exe scripts/fetch_smartresume_model.py --dest .tmp/models/llm --json docs/proof/model-manifest.json
  .tmp/sr-venv/Scripts/python.exe scripts/make_sample_pdfs.py --out .tmp/resumes-pdf
  .tmp/sr-venv/Scripts/python.exe scripts/proof_smartresume.py --model-dir .tmp/models/llm/Qwen3-0.6B --out docs/proof/smartresume-cpu.json --device cpu
  .tmp/sr-venv/Scripts/python.exe scripts/proof_smartresume.py --model-dir .tmp/models/llm/Qwen3-0.6B --out docs/proof/smartresume-gpu.json --device cuda
  ```
- 关键日志：
  ```text
  ok  Qwen3-0.6B/model.safetensors  size=1192135096  sha256=a7c610ac45e69b57…
  == 哈希核对：全部一致 -> docs\proof\model-manifest.json
  == SmartResume 可用性：可用
     smartresume: mode=smartresume 98.07s peak=3121.4MB recall=1.0
     fallback:    0.01s recall=1.0
  == 结论：3 份全部 parsing_mode=smartresume 且非空壳
  ```

### 2.2 实测数字（3 份虚构脱敏简历：BD / DA / PM）

| 设备 | 单份耗时（秒） | 平均 | 峰值 RSS（MB） | 关键实体召回 | fallback 耗时 | fallback 召回 |
|---|---|---|---|---|---|---|
| CPU（torch 2.15.0+cpu） | 98.07 / 85.67 / 93.25 | 92.33 | 3121 / 3219 / 3237 | 1.0 / 0.9167 / 1.0 | 0.010 / 0.010 / 0.007 | 1.0 / 1.0 / 1.0 |
| GPU（RTX 3060 6GB，torch 2.6.0+cu124，fp16） | 39.54 / 27.44 / 27.33 | 31.44 | 2079 / 2688 / 2685 | 1.0 / 0.9167 / 1.0 | 0.007 / 0.007 / 0.012 | 1.0 / 1.0 / 1.0 |

### 2.3 结论（含不受欢迎的部分）

1. **模型能真跑通，但没比规则解析更准**。3 份样本上，SmartResume 与 fallback 抽到的经历条数、bullet 数、指标数完全相同，
   召回唯一的差异是 `resume-da` 漏了 `0.82`（XGBoost AUC 那条指标被上游的行号区间截掉）。
2. **耗时差距是 3–4 个数量级，且直接顶破预算**。解析环节预算是 30 秒（02 第 4 节），
   CPU 单份 86–98 秒、GPU 首份 39.5 秒都超预算，意味着**按当前预算配置，本地模型在生产里会必然超时降级**。
3. **上游能力边界是真的**：`get_prompts()` 只有 `basic_info / education / work_experience` 三个键，
   传 `projects`/`skills` 直接 KeyError（我第一次跑就是 5 类全传，结果 3 份全部静默降级）；
   文本输入（.txt）没有行号索引，`jobDescription` 回填为空、bullet 全丢，必须用 PDF。
4. 因此本包保持 **fallback 为默认路径**，SmartResume 仅作可选后端；这条判断现在有数字支撑，不再是"因为没 GPU 所以不测"。

### 2.4 顺带修掉的两个真实缺陷（都被本次实测暴露）

- **映射猜错**：旧 `_normalize()` 按 snake_case 猜字段（`work_experience`/`company`/`period` 字符串），
  实际上游是 `basicInfo`/`workExperience`/`employmentPeriod{startDate,endDate}`。结果 `experiences` 恒为空，
  且校验失败后**静默退回 fallback**，报告上看不出模型其实没跑成。已按真实返回重写，并加 2 条测试。
- **空壳当成功**：GPU 上缺 `accelerate` 时模型没加载，上游返回空 dict，映射后是合法但全空的 `parsing_mode=smartresume`。
  已加 `_is_empty_structure()` 守卫：空壳且原文有文本 → 降级 fallback 并在 `parsing_notes` 写明原因（1 条测试）。
  实证脚本也同步收紧判据：必须「经历数 > 0 且召回 > 0」才算真跑通。

**局限**：样本是 3 份人工合成的中文简历（文本型 PDF），没有覆盖扫描件/图片 OCR、英文简历、多页排版；
召回口径是「关键实体是否出现在结构化输出里」的 13 个锚点，不是字段级准确率；
单机单次测量，未做多次重复取分位。

## 3. 天眼查真实调用（basic 1 家 + deep 1 家）

**状态：未实证。**

原因很直接：本机 `starter/.env` 不存在，`TIANYANCHA_API_KEY` 与 `TIANYANCHA_MCP_URL` 都为空，
脚本在预检阶段就退出（退出码 2），**没有发出任何真实请求**，`docs/proof/tianyancha-live.json` 里 `status=not_run`、`key_present=false`。

已经做到的部分（不含任何真实调用）：

- **缓存不串 Mock 已实证**：缓存 key 由 `data_mode` 参与哈希（`app/recon/service.py::_cache_key`），
  Mock 期间写下的 `mock://tianyancha/basic` 结果落在 mock 专属 key 上；dry-run 段确认 mock 缓存文件生成、
  来源为 `mock://`、计 2 次 mock 调用、cost=0。live 模式用另一个 key，结构上读不到那条 mock 结果。
- **费用上限闸门已落地**：`QuotaLedger.ensure_budget()` 在**调用前**校验，超过 `TIANYANCHA_COST_CAP_YUAN`（默认 5 元）直接抛
  `CostCapExceeded` 并停手；单价来自 `TIANYANCHA_UNIT_COST_YUAN`（不硬编码价格）。5 条测试覆盖边界值、超限、env 覆盖、脏值回退。
- **脚本已把纪律写死**：key 只从 `starter/.env` 或环境读，输出里只出现 `sha256` 前 12 位；硬数据来源出现 `mock://` 即判失败；
  deep 必须先出预估卡片、`confirmed_deep=True` 后才查。

- 复现命令：
  ```bash
  python3 scripts/proof_tianyancha.py --dry-run --json docs/proof/tyc-mock-isolation.json   # 现在能跑的部分
  TIANYANCHA_COST_CAP_YUAN=5 TIANYANCHA_UNIT_COST_YUAN=<按合同填> python3 scripts/proof_tianyancha.py --json docs/proof/tianyancha-live.json
  ```
- 关键日志：
  ```text
  ok mock 缓存落盘
  == dry-run：未发起任何真实调用
  == 未实证：缺少 ['TIANYANCHA_MCP_URL', 'TIANYANCHA_API_KEY']，未发请求 -> docs/proof/tianyancha-live.json
  ```
  产物里 `"key_fingerprint": "<empty>"`、`"missing": ["TIANYANCHA_MCP_URL","TIANYANCHA_API_KEY"]`、`"status": "not_run"`。

**仍缺什么**：① 天眼查 MCP 的可用凭据；② **接口契约核对**——`_live_call` 打的是 `{mcp_url}/company/basic` 与 `/company/deep`，
这两个路径与字段是按 05 的设想写的，从未与官方 MCP 文档核对过，真实接入大概率要改；③ 官方计费单价（现在记 0 元，等于费用核算不成立）。
补齐①②③后按上面命令跑一次，`status` 变成 `proven` 才能改这里的结论。

## 4. live 真实性能（真实搜索 + 真实 LLM）

**状态：未实证。**

两处独立的阻塞，缺一不可：

1. 无 `LLM_API_KEY` / `LLM_BASE_URL` / `SEARCH_API_KEY`，live 分支进不去（`docs/proof/live-perf-preflight.log`，退出码 2）。
2. **即使塞进 key 也测不了**：`app/recon/providers.py::SearchProvider._live_search` 目前主动 `raise ToolError(UPSTREAM_ERROR)`，
   理由是搜索 API 契约从未核验。也就是说「真实搜索时延」不是密钥问题，是功能没接。

同时按用户要求把旧口径撤回：`docs/PERFORMANCE.md` 已改写，明确 **P50 9.0ms / P90 9.3ms 只是 Mock 编排开销**，
不代表 live，也不构成对 120 秒预算的通过性结论；原文"远低于上限"的表述已删除。

- 复现命令：
  ```bash
  python3 scripts/measure_performance.py            # Mock：只证明编排不是瓶颈
  python3 scripts/measure_performance.py --live     # live 预检：缺件即退出，不产生任何耗时数字
  ```
- 关键日志：
  ```text
  == live 预检：未通过
     live 模式缺少 ['llm', 'tianyancha', 'search'] 的密钥/地址，未发起任何请求
  == 结论：live 时延未实证（本次未产生任何耗时数字）
  ```

**仍缺什么**：真实的 LLM 与搜索凭据；以及先定搜索供应商、核验请求/响应契约并实现 `_live_search`。
在此之前，「真实 P50/P90 ≥3 组」无法产出，本项不得写「已证」。

## 5. 真人复核（人工评审）

**状态：未实证。**

AI 能做的只有准备材料：`docs/HUMAN_REVIEW_PACK.md`（索引 + 17 题合并空白清单 + 签收表）、
`docs/review-pack/golden_06_bd_strong.md`（strong，8 题）、`docs/review-pack/golden_07_gap.md`（gap，9 题），
每题都摊开了题面、`evidence_ref`、证据原文与报告节选，判定列全部留空。

本轮新增的守门：`docs/HUMAN_REVIEW_PACK.md` 末尾加了「签收与存档」——签字后另存 `docs/review-pack/signed-YYYYMMDD-<姓名>.md`，
保持原样不改写，只在 PROGRESS 里登记路径 / sha256 / 日期；`scripts/check_proof.py` 规定：
**没有 `docs/review-pack/signed-*.md` 时，「真人复核」这一行不许写「已证」**，写了就直接判失败。

- 复现命令：
  ```bash
  python3 scripts/export_review_pack.py --case golden_06_bd_strong --case golden_07_gap
  ls docs/review-pack/signed-*.md 2>/dev/null || echo "无签字件 -> 未实证"
  ```
- 关键日志：
  ```text
  == review pack ok（人工判定位仍为空白）
  无签字件 -> 未实证
  ```

**仍缺什么**：1–2 位招聘/用人侧真人的实际打分与签字。签字件到位后，按「签收与存档」规则登记，才可把本项改为已证。

## 6. 本轮改动与红线条目对照

| 红线 | 是否触碰 | 说明 |
|---|---|---|
| 不改 3 个工具签名 | 未触碰 | `tools.ts` 未改；只改了 sidecar 内部实现 |
| 不改 8 节报告顺序 | 未触碰 | 报告生成与排序逻辑零改动 |
| 不放宽证据规则 | 未触碰（只收紧） | 新增空壳降级、费用上限、CI 证据校验，都是收紧 |
| 不改 A1-A7 阈值 | 未触碰 | golden 仍 ≥80%，题量/题库阈值未动 |
| 不删测试 | 未删除 | 172 → 180 passed（新增 5 条费用上限、2 条真实映射、1 条空壳降级） |
| 默认 Mock、不调真实付费接口 | 遵守 | 天眼查/LLM 一次未调；SmartResume 用本地权重，无外部 API 计费 |
| 不写真实密钥与简历 | 遵守 | 无 `.env`；3 份简历为原有虚构样例；key 指纹只存 sha256 前 12 位 |
