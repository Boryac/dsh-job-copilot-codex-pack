# FORK_LOCK — T1.1 fork 锁定表（Lane E 交付物）

> 核验时间：2026-11-05（GMT+8）。
> 核验方式：`git ls-remote` 取真实提交哈希；`raw.githubusercontent.com` 直取 LICENSE 正文；
> GitHub 页面读取 README 与目录说明。未使用任何需要登录的接口，未克隆全仓（避免把上游大仓塞进本包）。
> 结论先行：**锁定 2 个仓库 + 2 个只借思路来源，不 fork 任何全仓**。理由见第 3 节。

## 1. 锁定结果

### 1.1 SmartResume（简历解析，主选）

```
项目名：SmartResume
仓库地址：https://github.com/alibaba/SmartResume
提交版本 / Tag：main @ 3b62157be4b07e1d89f03567536524cb89e4ea46（无 tag，无 release）
LICENSE 文件位置与结论：/LICENSE，Apache License 2.0 正文（2026-11-05 直取校验通过）
借用的目录/文件：
  - smartresume.ResumeAnalyzer 的调用契约（init_ocr / init_llm / pipeline(cv_path, resume_id, extract_types)）
  - scripts/start.py 的 --extract_types 用法（按需抽取字段）
  - demo/web_app.py 的“进程内常驻模型、避免每次重载”思路
不借用的部分：
  - 本地 vLLM 推理链路（Qwen 权重 + 版面检测模型）——08 第 5 节已定 MVP 不用 GPU 硬依赖
  - configs/config.yaml 的模型与 key 配置（本项目只走环境变量，不引入上游配置文件）
  - 其 OCR / PDF 解析内部实现（上游 README 明确说明开源版为重构版，内部组件已替换）
实测结果：**未实测真实后端**。真实调用需要 ≥8GB 内存、≥10GB 存储、可选 CUDA，
  当前开发机不满足“装完即可跑”的条件，且会引入模型下载。按 08 第 5 节走选项 1
  （文本提取 + LLM 结构化，parsing_mode=fallback），SmartResume 作为可选后端适配器保留：
  `starter/sidecar/app/parsers/resume.py` 里 `SmartResumeBackend` 在 import 失败或
  `APP_MODE=mock` 时自动让位给 fallback。实测记录见 docs/PERFORMANCE.md。
备选方案：pdfplumber / pypdf 文本提取 + 规则分区 + LLM 结构化（已落地为默认路径）
```

**T1.1 需要说明的诚实结论**：12_FORK_MAP 把“实测 1 份简历 + 1 段 JD”写进锁定表，本项无法在无 GPU
环境下完成真实实测。处理方式是按 00 的 3 轮规则降级为“契约级实测”：适配器按上游 README 的
`ResumeAnalyzer.pipeline` 签名实现并有单元测试覆盖调用参数，真实解析效果标记为**待核实**，
写入 PROGRESS.md 的已知缺口，不用“跑通了”这类没核实的状态词。

### 1.2 Resume-Matcher（匹配基线，主选）

```
项目名：Resume Matcher
仓库地址：https://github.com/srbhr/Resume-Matcher
提交版本 / Tag：main @ d480551798b7aa97f5b57ba1972ee383bd882238；最新 tag v1.4.0（dcd0962656e3e1ac2b4490689159362f9d48cd32）
LICENSE 文件位置与结论：/LICENSE，Apache License 2.0 正文（2026-11-05 直取校验通过）
借用的目录/文件：
  - services/ats.py 的确定性关键词覆盖算法思路（不调 LLM 的纯代码打分）
  - services/ats_parse/ 的“按 ATS 文本抽取视角回读 PDF”校验思路
  - 其 ATS 权重口径（关键词 40 / 技能 20 / 岗位名 15 / 结构完整 15 / 日期一致 10）作为**基线权重参考**
不借用的部分：
  - 整个 Next.js 前端与 SQLite 应用外壳（本项目 sidecar 与前端解耦，只留 HTTP API）
  - 它的演示数据与“mocked/faked”示例结果（12 第 2 节明令禁止进测试）
  - 简历改写 / 覆盖信生成 / Playwright 出 PDF 的部分（非本项目范围）
实测结果：借的是**算法口径**，不是代码。按其权重口径实现的关键词基线在
  `starter/sidecar/app/orchestrator/matching.py::keyword_baseline`，
  已用 golden set 5 组回归验证（见 docs/ACCEPTANCE_REPORT.md A5）。
  注意：本项目**只把关键词覆盖率当“硬性条件”维度的基线**，最终档位由基线 + 语义 + 证据强度
  三者共同决定，输出档位不输出百分比（06 第 3 节禁止把重合度当通过率）。
备选方案：自研 TF-IDF 基线（已作为 matching.py 的 fallback 路径保留）
```

> 技术栈更正记录：12_FORK_MAP 原文未写 Resume-Matcher 的技术栈，实际核验为
> **FastAPI + Python 3.13 + SQLite + Next.js 前端**，后端与我们的 sidecar 同构，
> 这也是它能胜出的关键原因（改造成本低于预期）。

### 1.3 编排 / 公司库候选（候选 A / B 均未采用，走自研）

12_FORK_MAP 要求“JobCopilot 类项目二选一并记录理由”。核验了三个真实仓库：

| 候选 | 仓库 | 星数 | 许可证 | 结论 |
|---|---|---|---|---|
| huluobo2237-pixel/JobCopilot | github.com/huluobo2237-pixel/JobCopilot | 143 | MIT（已核验正文） | 拒绝：核心卖点是**自动投递浏览器扩展**，属 12 第 2 节明令不借的范围；去掉投递后剩下的编排价值不足以抵消引入成本 |
| huluobo2237-pixel 类之外的轻量候选 | github.com/NaniToka/resume-match-engine | 5 | MIT（已核验正文） | 拒绝：Streamlit + 单文件脚本，无测试、无契约层、无来源标注，接进来等于重写 |
| 其它同名 JobCopilot | CanerPiskin / hzhan516 / YuanshuoDu | ≤8 | MIT / NOASSERTION / 无 | 拒绝：星数与维护度不足，无法评估许可证完整性与长期可用性 |

**决策：二选一结论为“都不选”，编排层与 company-recon 按本包 01/04/05 自研。**
依据 12 第 1 节末段：“如果锁定仓库里没有可复用的企业研究模块，company-recon 就按 05 自研，
不许为了‘复用’而强行拼一个不存在的模块。” 实测三个候选仓库均**不含任何企业研究 / 工商数据模块**
（核验方式：README 功能列表与目录说明，均无 recon / company research 相关模块）。
强行拼装会同时违反 11 第 4 节（许可证与来源标注）和 03（分区契约）。

### 1.4 面试题证据锁定（只借思路，不 fork）

```
项目名：CareerPilot / interview-coach 类实现（12 第 1 节要求“复核存在性”）
仓库地址：GitHub 检索 “CareerPilot interview” 前 4 结果为 3/1/0/0 星个人项目
提交版本 / Tag：不具备可锁定条件（无 tag、无测试、部分无 LICENSE）
LICENSE 文件位置与结论：前三名均无 LICENSE 文件 → 默认版权保留，**不可复制代码**
借用的目录/文件：只借“每题强制引用简历经历 ID 或 JD 句子 ID + STAR + 三层追问链”的**思路**
不借用的部分：任何代码、任何 prompt 原文
实测结果：思路已落地为“生成时只喂已生成 ID 列表 + 生成后强制校验器”的双保险
  （starter/sidecar/app/orchestrator/generate.py + app/validator.py），
  校验器 6 条规则各带正反例测试。
备选方案：无（12 明确“不借任何只靠 prompt 要求证据的实现”）
```

## 2. 移植映射表（对应 12 第 3 节）

| 本项目模块 | 来源项目与文件 | 移植方式 | 许可证 | 备注 |
|---|---|---|---|---|
| resume 解析 | alibaba/SmartResume `smartresume.ResumeAnalyzer` | 只借接口契约（适配器）+ 自研 fallback | Apache-2.0 | 真实后端未实测，fallback 为默认路径 |
| jd 解析 | 无上游（自研） | 自研，按 03 第 3.3 节契约 | — | 粘文本主路径，URL 仅辅助 |
| 匹配基线 | srbhr/Resume-Matcher `services/ats.py` | 只借思路（权重口径 + 纯代码确定性打分） | Apache-2.0 | 输出档位不输出百分比 |
| 企业研究 | 无上游（12 第 1 节已预判） | 自研，按 05 全部三层 + 消歧 + 记账 | — | 天眼查/搜索默认 Mock |
| 面试陪练编排 | CareerPilot 类（无 LICENSE） | 只借思路 | 不可复制 | 必须有生成后校验器 |

## 3. 为什么不 fork 全仓（Orchestrator 裁决，已记入 PROGRESS.md）

1. **许可证**：SmartResume 与 Resume-Matcher 均为 Apache-2.0，允许商用与修改，但要求保留
   NOTICE 与变更声明。全仓 fork 会把两个完全不同技术栈的应用塞进同一个仓库，NOTICE 义务难以对齐。
2. **技术栈冲突**：Resume-Matcher 前端是 Next.js，本项目前端是 DSH 卡片；SmartResume 需要
   10GB 存储与 GPU 可选依赖。全仓 fork 后两份依赖树都会成为负担（11 第 1 节“只 fork 必要目录”）。
3. **可验证性**：只借契约与算法口径时，每个借用点都能写单元测试（本项目已对
   `keyword_baseline` 与 `SmartResumeBackend` 各写测试）；全仓 fork 的“集成成功”很难验证，
   容易退化成“看起来接上了”。
4. **本包红线**：00 第 4 条要求“不把第三方数据原样宣称是自己的数据”，同理不把第三方
   应用原样宣称是本项目成果。只借思路 + 自研，来源可追溯。

## 4. 后续换源规则

任何人更换锁定仓库，必须重跑本节流程并在 PROGRESS.md 发起变更记录，由 Orchestrator 批准。
不允许私下换源，不允许为了“能跑起来”临时 clone 一个未核验许可证的仓库进 `starter/`。
