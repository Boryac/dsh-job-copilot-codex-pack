# 环境可行性结论（Docker / SmartResume）

> 本文件只写**已核实**的部分。没有执行过的动作不写"已完成"，未实测的能力不写"已验证"。
> 2026-11-05 外部依赖实证阶段更新：SmartResume 已真跑（CPU + GPU）。
> 2026-11-05 晚间更新：仓库已推送到 GitHub，CI 工作流真实跑过一次（run 41997650783）。
> 镜像构建、容器运行、/health 探活均已证（证据包已下载并过机械复核）；容器内包自检因挂载目录
> 权限未执行，该项仍未证。逐项证据见 `docs/proof/` 与 CI artifact `docker-evidence`，
> 复跑命令见 `scripts/` 下各脚本，本文件只做环境角度的归纳。

## 1. 结论先行

| 项 | 本轮状态 | 证据 | 结论 |
|---|---|---|---|
| SmartResume 本地模型 | **已证（CPU + GPU）** | `docs/proof/model-manifest.json`（9/9 哈希一致）、`docs/proof/smartresume-cpu.json`、`docs/proof/smartresume-gpu.json` | 能跑通且 3/3 非空壳；但召回与 fallback 打平、耗时 27–98 秒，**不设为默认路径** |
| Dockerfile / compose / CI 工作流 | 已静态校验（25 项） | `python3 scripts/check_docker_assets.py` → `status=static_only`、`static_ok=true` | 资产无已知缺陷 |
| Docker 镜像构建与容器运行 | **已证（CI）** | CI run `41997650783`（push 触发，success）：`build.log`（真实 BuildKit 构建）、`image-id.txt`（`sha256:1114bea4…`）、`container.log`（uvicorn 启动）、`health-status.txt`（200）、`health.json`（可解析响应体）；本机无 `docker` 运行时 | 镜像可构建、容器可运行、/health 返回 200，五项证据经 `scripts/check_ci_evidence.py` 复核 E1–E6 全过 |
| 容器内包自检 | **未执行** | 同一证据包的 `verify.log` 仅 82 字节：`mkdir: cannot create directory '/pack/.tmp': Permission denied` | 挂载目录属 CI runner 用户，容器内非 root 用户无写权限，`verify.sh` 建 `.tmp` 即退出；机械复核 E7 失败，整体 `status=contradictory`。"镜像运行时满足包自检"仍未证 |
| fallback 解析路径 | 已测 | `tests/test_resume_parser.py` 20 passed | v1 主链路，仍是默认路径 |

机器实测环境：Windows 11 / Python 3.13.14 / 16 逻辑核 / 15.4GB RAM / **RTX 3060 Laptop 6GB（CUDA 13.4 驱动）** / 磁盘余量 80GB。
上一版本文写的"本机无 GPU"是错的，本轮已更正——核验方式 `nvidia-smi` 与 `torch.cuda.is_available()`。

## 2. Docker：做了什么、没做什么

### 2.1 已执行（静态，25 项）

```
$ python3 scripts/check_docker_assets.py
docker 可用：否 — PATH 中找不到 docker 可执行文件
  ok D1..D9   Dockerfile：固定 python:3.11-slim / 先依赖后代码 / 非 root / EXPOSE 8000
              / HEALTHCHECK / 不拷 .env / 无硬编码密钥
  ok C1..C5   compose：context 与 dockerfile 路径真实 / 端口可 env 覆盖 / 无密钥
  ok I1..I3   .dockerignore 排 .cache 与 .env；requirements.txt 存在
  ok W1..W8   CI 工作流：YAML 可解析 / 有 docker build / 有 docker run / 探活并断言 200
              / 容器内跑 verify.sh / artifact 留存 / 记录镜像 ID
本机构建：未执行（PATH 中找不到 docker 可执行文件）—— 静态校验不等于构建通过
CI 证据包：未提供 —— 未实证
镜像构建：未实证（缺镜像 ID / 构建日志 / 容器日志三件套）—— 不许写成『已构建』
```

本轮新增的资产：

- `.github/workflows/docker-build.yml`：CI 里完成 build → run → 容器内探活 → 容器内 `verify.sh` → 抓日志 → 上传 `docker-evidence`。
- `scripts/check_ci_evidence.py`：把「三件套」落成机械判据（构建日志/镜像 ID/容器日志/health/verify），
  空文件判 `incomplete`、内容矛盾判 `contradictory`，只有全过才 `certified`，`check_docker_assets.py` 才会把 `status` 改成 `built`。

### 2.1.1 CI 实测结果（2026-11-05，run 41997650783）

仓库推送到 GitHub 后，`docker-build` 工作流由 push 触发真实跑完一次（conclusion: success）。证据包 `docker-evidence` 已下载，内容如下：

- `build.log`：真实 BuildKit 构建输出，含 `naming to docker.io/library/dsh-job-copilot-sidecar:ci`。
- `image-id.txt`：`sha256:1114bea4f539ebbaccedd55d9fccf48c7d1c1cdaa08da44878381376676878dd`，与 build.log 末尾 manifest list 一致。
- `container.log`：uvicorn 启动完成，3 次 `GET /health` 均 200。
- `health-status.txt`：`200`（宿主侧取的状态码）。
- `health.json`：`{"status":"ok","version":"1.0.0","mode":"mock","degraded_modules":[],"cache_days":7}`。
- `health-transport.txt`：`python-urllib（镜像内无 curl）`，探活方式如实记录。
- `verify.log`：仅 82 字节，内容为 `mkdir: cannot create directory '/pack/.tmp': Permission denied`。

`python3 scripts/check_ci_evidence.py --dir <证据目录>` 复核：E1–E6 全过，E7（verify 以 `== verify passed` 收尾）失败，整体 `status: contradictory`。即：镜像构建、容器运行、探活已证；容器内自检未执行，未证。

### 2.2 未执行（不许写成"已验证"）

- 容器内 `verify.sh`：未真正执行。根因是 `-v "$GITHUB_WORKSPACE":/pack` 挂载的目录属 CI runner 用户，而镜像以非 root 用户运行（Dockerfile 的 D 组检查要求），容器内建不了 `/pack/.tmp`，脚本 `set -e` 直接退出。工作流这一步用了 `| tee` 管道且未加 `set -o pipefail`，退出码被 tee 吞掉，所以步骤显示 success 而自检一行未跑。修复方向：verify 步之前对 workspace 赋写权限（如 `chmod -R a+rwX "$GITHUB_WORKSPACE"`），或让 `verify.sh` 在包目录不可写时把临时目录改到容器内可写路径。
- 本机 `docker build` / `docker run` / `docker compose up`：未执行，本机无 Docker 运行时。

口径边界：可以说"CI 构建并运行过镜像、/health 200 已证"；不能说"容器内自检通过"或"镜像已验证满足包自检"，后者要等 E7 过。

### 2.3 拿到证据后怎么改口径

1. 按 2.2 的根因修掉挂载权限问题，推一次 main 触发 `docker-build`；
2. 从 Actions 下载 `docker-evidence` artifact；
3. `python3 scripts/check_ci_evidence.py --dir <证据目录>` 必须返回 `certified`，再用
   `python3 scripts/check_docker_assets.py --ci-evidence <证据目录>` 复核 `status=built`；
4. 最后改本文件第 1 节状态表与 2.2 的口径边界。E7 不过之前，容器内自检一律写未证。

## 3. SmartResume：实测数据与结论

### 3.1 环境与模型

| 项 | 值 |
|---|---|
| 上游包 | PyPI `smartresume==0.1.1`（Homepage = `github.com/alibaba/SmartResume`，Apache-2.0） |
| 权重 | ModelScope `Alibaba-EI/SmartResume`，revision `df45f06c…`，子目录 `Qwen3-0.6B`，9 文件 1152.1 MiB |
| 哈希核对 | 远端 `Sha256` vs 本地复算，9/9 一致（`model.safetensors` = `a7c610ac45e69b57…`） |
| 推理方式 | 上游 `use_direct_models=true`，本地 transformers 加载权重，**不走任何外部 API** |
| 依赖 | 单独 venv（`.tmp/sr-venv`），`vllm`/`easyocr` 未装（前者 Windows 装不上，后者惰性导入且 OCR 关闭） |

### 3.2 实测（3 份虚构脱敏简历：BD / DA / PM，文本型 PDF）

| 设备 | 单份耗时（秒） | 平均 | 峰值 RSS | 召回 | fallback 耗时 | fallback 召回 |
|---|---|---|---|---|---|---|
| CPU | 98.07 / 85.67 / 93.25 | 92.33 | 3121–3237 MB | 1.0 / 0.9167 / 1.0 | 7–10 ms | 1.0 / 1.0 / 1.0 |
| GPU（3060 6GB, fp16） | 39.54 / 27.44 / 27.33 | 31.44 | 2079–2688 MB | 1.0 / 0.9167 / 1.0 | 7–12 ms | 1.0 / 1.0 / 1.0 |

### 3.3 结论与边界

- **能跑，但不值得默认开**：召回与 fallback 打平（唯一差异是 `resume-da` 漏了 `0.82` 这条指标），
  耗时长 3–4 个数量级，且解析预算只有 30 秒——CPU 必然超时、GPU 首份 39.5 秒也超时。
- **上游能力边界**：`get_prompts()` 只有 `basic_info/education/work_experience`；`projects/skills` 会 KeyError；
  `.txt` 输入没有行号索引，`jobDescription` 回填为空，必须用 PDF。
- **映射已按真实返回核对**（这是原计划里"复核 `_normalize()`"那一条，已完成）：上游是
  `basicInfo`/`workExperience`/`employmentPeriod{startDate,endDate}`，不是此前猜的 snake_case。
  旧映射会让 `experiences` 恒空且静默降级，已修并加测试。
- **新增空壳守卫**：上游模型未加载时返回合法空结构，会被误当成功；现已降级为 fallback 并写明原因。

**仍缺**：扫描件/图片 OCR、英文简历、多页排版未覆盖；召回口径是 13 个关键实体锚点，不是字段级准确率；
单机单次测量，未取分位。

## 4. fallback 路径的测试证据

| 场景 | 测试 | 断言要点 |
|---|---|---|
| TXT | `test_txt_resume_parses_core_fields` | 教育/经历/技能字段齐 |
| PII 不进结构化输出 | `test_pii_never_enters_structured_output` | 电话/邮箱在结构上无字段可落 |
| 量化成果来自原文 | `test_metrics_come_from_original_bullets` | 数字必须能在 bullet 原文里找到 |
| DOCX | `test_docx_resume_is_supported` | 提取经历 |
| DOCX 经历+指标 | `test_docx_fallback_keeps_experiences_and_metrics` | 经历非空且带 metrics |
| 文字层 PDF | `test_text_layer_pdf_is_supported` | 正常解析 |
| 扫描件 PDF | `test_scanned_pdf_is_flagged_and_not_fabricated` | `is_scanned=True` + 提示，不编内容 |
| 图片简历 | `test_image_resume_requires_ocr_without_pretending` | 缺 OCR 时明确要求文本版 |
| 文件不存在 | `test_missing_file_returns_empty_structure_not_exception` | 空结构不抛异常 |
| 空文件 | `test_empty_resume_does_not_raise` | 不崩 |
| 中英混排 | `test_mixed_language_resume_keeps_english_tokens` | 英文 token 保留 |
| 解析模式声明 | `test_fallback_path_declares_mode_and_reason` | `parsing_mode=fallback` 且写明原因 |
| 不可用原因 | `test_smartresume_unavailable_reason_is_explicit` | 原因可读，不静默降级 |
| 硬件要求 | `test_smartresume_hardware_requirements_are_recorded_and_measured` | `verified is True` 且带实测数字区间 |
| 真实映射 | `test_normalize_maps_real_upstream_payload` | 驼峰字段/嵌套 period/头行不入 bullet |
| 上游边界 | `test_normalize_flags_upstream_limits` | notes 写明 3 类抽取与 bullet 缺失 |
| 空壳降级 | `test_empty_smartresume_result_degrades_instead_of_claiming_success` | 空壳 → fallback + 说明 |
| 结构不合契约 | `test_parse_failure_raises_contract_error` | 抛 `PARSE_FAILED`，不向上传坏结构 |
| ID 连续 | `test_fallback_parser_keeps_ids_continuous` | `exp_01..exp_NN` |

复跑：`cd starter/sidecar && python -m pytest tests/test_resume_parser.py -q`
