# 求职作战包（dsh-job-skill-plugin）

DSH（DeepSeek Harness）桌面端插件。输入一份简历、一段 JD、一个公司名称，输出一份证据可溯源的求职匹配报告：公司背调、岗位拆解、人岗匹配、三版自我介绍、不少于 8 道针对性面试题、背靠知识点与应对方案。

当前版本 v1.0.1，已在 DSH 桌面端 0.2.1-rc.5 上完成安装与端到端实测。测试基线：sidecar pytest 180 条通过，插件测试 30 条通过，golden 回归 7/7。

## 它解决什么问题

求职者投递一个具体岗位前，通常要在几个地方来回切换：查公司工商信息、读 JD 猜岗位真实要求、对照简历找差距、准备面试话术。这个插件把这条链路收进一次运行：简历传进去，JD 粘进去，公司名输进去，出来的报告里每一条结论都挂在证据 ID 上，面试题指向简历里真实存在的经历，公司硬数据和软信息分开摆放，不混写。

匹配结论只给档位（strong / discussable / gap），不给虚假精度的百分比总分。报告末尾附数据来源与置信度表，以及一份待核实清单。

## 一次完整运行长什么样

1. 用户在 DSH 会话中执行斜杠命令 `/job-fit --resume <简历路径> --jd <JD路径> --company <公司名> --out <输出目录>`，也可以在对话中直接让 agent 依次调用三个工具。
2. 插件层并行调用 resume-structurer、jd-decoder、company-recon（basic 档），请求经 HTTP 转发到本地 sidecar。
3. sidecar 完成解析、匹配与生成，先回一页执行摘要卡片，再落盘一份完整 Markdown 报告。
4. 摘要卡片给出 verdict、最大亮点、最大缺口与建议动作（投 / 补齐后再投 / 慎投）。正文共 8 节：公司背调、岗位拆解、人岗匹配、自我介绍、面试题、背靠知识点、应对方案、数据来源与置信度。

报告文件名格式为 `report-<公司>-<岗位>-<analysis_id 前 8 位>.md`，同一次输入重复请求直接返回缓存结果，deep 档付费调用不会因重复点击重复扣费。

## 功能清单

| 组件 | 类型 | 输入 | 输出 |
|---|---|---|---|
| resume-structurer | 工具 | 简历文件（PDF / DOCX / 图片 / 文本） | 结构化 JSON，经历带 `exp_01` 式证据 ID，解析模式标注 `parsing_mode` |
| jd-decoder | 工具 | JD 文本为主，URL 为辅 | `must_have` / `nice_to_have` / `responsibilities` / `hidden_priorities` / `red_flags`，带 `jd_01` 式 ID |
| company-recon | 工具 | 公司名称 + depth（basic / deep） | 硬数据（verified）与软信息（inferred）分层 JSON，含公司消歧、7 天缓存、额度记账 |
| job-fit-orchestrator | Skill | 三个工具的输出 | 固定顺序编排：并行解析、四维匹配、自我介绍、面试题、报告组装 |
| /job-fit | 斜杠命令 | `--resume --jd --company --out` | 一条命令跑完端到端流程并落盘报告 |

编排顺序固定：三个工具并行调用，匹配分析以关键词重合度为基线叠加语义匹配，输出四维档位（硬性条件 / 职责匹配 / 履历证据 / 加分项），再生成三版自我介绍与面试题，最后组装报告。任何一步超时按预算降级，出部分报告加失败原因，不允许整份报告空白。

## 架构

```
DSH 桌面端
  │
  ▼
┌─────────────────────────────────────────┐
│ 插件层（TypeScript，Cordis 插件）          │
│ resume-structurer / jd-decoder /        │
│ company-recon（defineTool 声明）          │
│ job-fit-orchestrator（Skill 编排层）      │
└──────────────────┬──────────────────────┘
                   │ HTTP（127.0.0.1:8000）
                   ▼
┌─────────────────────────────────────────┐
│ sidecar（FastAPI）                        │
│ 简历解析 / JD 拆解 / 公司背调 /           │
│ 匹配引擎 / 报告生成 / 证据校验            │
└──────────────────┬──────────────────────┘
                   │ 按需，默认 Mock
                   ▼
        SmartResume 适配器 / 天眼查 MCP / 搜索 API
```

重型依赖不进插件包。DSH 插件层只做三件事：声明参数、校验输入、转发请求并渲染结果卡片。Python 运行时、解析模型和外部 API 调用都留在 sidecar 进程或容器里，插件与引擎之间只有 HTTP 和 JSON 契约，后续给 sidecar 套网页壳不需要重写引擎。

## 快速开始

```bash
# 1. 准备环境变量（Mock 模式下 key 全部留空即可跑通）
cp starter/.env.example starter/.env

# 2. 启动 sidecar
cd starter/sidecar && pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# 3. 健康检查（本机设有代理时必须加 --noproxy，否则 127.0.0.1 会被代理拦成 502）
curl --noproxy "*" http://127.0.0.1:8000/health
```

也可以用 Docker：`docker compose -f starter/docker-compose.yml up --build`。

sidecar 起来后，把插件装进 DSH 桌面端：构建 `starter/dsh-plugin`，复制到 `~/.dsh/plugins/dsh-job-skill-plugin`，用 DSH 官方 CLI 装进 desktop profile 并登记到 bundle 列表，重启 DSH。完整步骤、本机实测路径与排障见 [docs/INSTALL.md](docs/INSTALL.md)。

验证插件是否加载：启动 DSH 后看插件目录下的 `load.log`，出现 `tools=resume-structurer,company-recon,jd-decoder` 与 `cmdcheck name=job-fit` 两行即为成功。

包内自检（不启动外部服务，不需要真实 key）：

```bash
bash scripts/verify.sh
```

## 输出示例

- [reports/](reports/) 下保留一份真实运行产出的报告：云栖生活科技（福州）有限公司，本地生活商务拓展岗，2027 届校招。声明句 1 次，`evidence_ref` 8 处，Mock 标注 14 处，与服务端原文哈希一致。
- [docs/evidence/](docs/evidence/) 下是 DSH 桌面端斜杠菜单与运行结果截图。

## 设计约束

1. 证据可溯源。面试题 100% 带 `evidence_ref`，指向真实存在的简历经历 ID 或 JD 句子 ID，ID 不存在即判失败。无来源的数据进待核实清单，不进正文结论。
2. Mock 优先。开发和测试阶段所有外部调用默认走 Mock，真实接口只在显式配置 key 后启用。deep 档背调先展示预估费用，用户确认后才调用，默认费用闸门 5 元，超限拒绝执行。
3. 隐私边界。简历全文、电话、邮箱不进日志、测试固件和 git 历史；发往搜索接口的只有公司名和 JD 关键词。
4. 不绕过登录墙。JD 主路径是粘贴文本，URL 只是辅助，抓取失败明确提示粘贴。不做自动投递、自动填表。

## 已知限制

1. live 链路未实测。Mock 下编排耗时 P50 9.0ms、P90 9.3ms，只证明编排层不是瓶颈；真实搜索与 LLM 调用的时延需要 key 才能测，当前不构成 live 结论。
2. SmartResume 本地模型不是默认路径。实测召回与 fallback 打平，CPU 平均 92 秒、GPU（RTX 3060 6GB）平均 31 秒，超过 30 秒解析预算。默认走文本提取加 LLM 结构化，报告内标注 `parsing_mode`，本地模型作为可选适配器保留。
3. Docker 镜像经 CI 真实构建并运行通过（构建日志、镜像 ID、/health 200 均有证据），但容器内包自检因挂载目录权限未执行，该步未证；本机无 Docker 运行时。细节见 [docs/ENV_FEASIBILITY.md](docs/ENV_FEASIBILITY.md)。
4. 面试题人工评审目前是 AI 自评。真人复核材料已备好（只摊材料留空位），签字后口径才能改。

## 仓库结构

```
README.md                  本文件
docs/
  INSTALL.md               DSH 桌面端安装、sidecar 启动、排障（本机实测记录）
  ENVIRONMENT.md           环境变量、Mock/live 模式、部署形态
  ENV_FEASIBILITY.md       Docker 与 SmartResume 可行性结论，含实测数据
  evidence/                安装与运行截图
  proof/                   外部依赖实证产物（JSON）
starter/
  dsh-plugin/              插件源码（TypeScript，Cordis）
  sidecar/                 sidecar 源码（Python，FastAPI）
  docker-compose.yml
  .env.example
templates/                 报告模板、golden 用例、JD 与简历样例
scripts/                   自检、契约校验、Mock 演示、golden 回归
reports/                   示例报告（真实运行产出）
.github/workflows/         Docker 构建 CI
```

## 上游与致谢

- [SmartResume](https://github.com/alibaba/SmartResume)（Apache-2.0）：简历解析的契约与算法口径参考，未 fork 全仓；sidecar 内的 SmartResume 适配器可按需启用。
- Resume-Matcher（Apache-2.0）：匹配算法口径参考。
