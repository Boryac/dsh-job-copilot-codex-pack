# 环境可行性结论（Docker / SmartResume）

> 本文件只写**已核实**的部分。没有执行过的动作不写"已完成"，未实测的能力不写"已验证"。
> 对应 PROGRESS 已知缺口 3、4；v2 进入前必须按第 3 节的验证步骤复核。

## 1. 结论先行

| 项 | 本轮状态 | 证据 | 结论 |
|---|---|---|---|
| Docker 镜像 | **未构建** | 本机 `docker` 不可用（PATH 中无此命令）；`scripts/check_docker_assets.py` 17 项静态检查全过 | 静态资产可用性成立；构建可用性 **延期到 v2 Phase 0** |
| Dockerfile / compose | 已静态校验 | `python scripts/check_docker_assets.py` → `status=static_only`，`static_ok=true` | 资产本身没有已知缺陷，但没有被真实构建验证过 |
| SmartResume 本地模型 | **未实测** | 本机无 GPU，且不满足上游 ≥8GB 内存 / ≥10GB 存储；`SmartResumeBackend.HARDWARE_MIN.verified = False` | 本地模型效果 **延期到 v2 Phase 0** |
| fallback 解析路径 | 已测 | `tests/test_resume_parser.py` 17 passed（含 TXT/DOCX/文字层 PDF/扫描件/图片/空文件） | v1 主链路可用，且明确标注"这是规则解析，不是模型解析" |

## 2. Docker：做了什么、没做什么

### 2.1 已执行

```
$ docker --version
bash: docker: command not found

$ python scripts/check_docker_assets.py
docker 可用：否 — PATH 中找不到 docker 可执行文件
  ok D1 Dockerfile 存在
  ok D2 基础镜像固定版本、不用 latest -> python:3.11-slim
  ok D3 安装 dependencies 用 requirements.txt
  ok D4 先拷依赖再拷代码（利用层缓存）
  ok D5 非 root 运行
  ok D6 EXPOSE 与 sidecar 端口一致（8000）
  ok D7 声明 HEALTHCHECK（/health 可探活）
  ok D8 镜像内不拷贝 .env
  ok D9 Dockerfile 里没有硬编码密钥
  ok C1 docker-compose.yml 存在
  ok C2 compose 的 build context / dockerfile 指向真实路径
  ok C3 compose 引用的 context 目录存在（静态存在性，非构建验证）
  ok C4 端口映射可用环境变量覆盖且容器端口一致
  ok C5 compose 里没有硬编码密钥
  ok I1 .dockerignore 排除 .cache
  ok I2 .dockerignore 排除 .env
  ok I3 requirements.txt 存在
镜像构建：未执行（PATH 中找不到 docker 可执行文件）
```

`.dockerignore` 原本只排除 `.cache`/`__pycache__`/`tests`，本轮补上 `.env` 与 `.env.*`：
密钥只允许从运行时环境变量或 compose 的 `env_file` 注入，不许进构建上下文。

### 2.2 未执行（不许写成"已构建"）

- `docker build`
- `docker compose up`
- 容器内 `/health` 探活
- 容器内的 Mock 端到端演示

因此当前 Dockerfile 的正确性只有**静态证据**，没有运行时证据。任何文档/汇报里出现"镜像已构建""容器已验证"都属于虚报。

## 3. v2 Phase 0 待验证项

### 3.1 Docker 构建（负责人：Lane B）

1. 在装有 Docker 24+ 的机器上执行 `docker build -t dsh-job-copilot-sidecar:verify starter/sidecar`；
2. `docker run --rm -p 8000:8000 dsh-job-copilot-sidecar:verify`，确认 `GET /health` 返回 200；
3. 容器内跑一次 `python scripts/run_mock_demo.py --all`（需把 `scripts/`、`templates/` 挂载或复制进镜像外的临时目录）；
4. 用非 root 用户验证 `.cache` 可写（Dockerfile 已 `chown`，但未实测）；
5. 把构建日志与 `/health` 响应贴回本文件第 2.1 节，并把 `check_docker_assets.py` 的 `status` 从 `static_only` 改成 `built`。

验收口径：镜像可构建 + 容器内 `/health` 200 + 容器内 Mock demo 产出报告，三者缺一不算通过。

### 3.2 SmartResume 本地模型（负责人：Lane B）

上游要求（记录在 `SmartResumeBackend.HARDWARE_MIN`，来源见 `docs/FORK_LOCK.md` 1.1 与 08 第 5 节）：

| 项 | 最低要求 | 本机 |
|---|---|---|
| 内存 | ≥ 8 GB | 不满足/未核到 |
| 存储 | ≥ 10 GB（含模型权重） | 不满足/未核到 |
| GPU | 非必需但强烈建议（CUDA）；OCR + 本地 LLM 推理无 GPU 时耗时不可接受 | 无 GPU |

验证步骤：

1. 在满足上述硬件的机器上安装 SmartResume，确认 `SmartResumeBackend.available()` 在 `APP_MODE=live` 下为 True；
2. 用 5 份脱敏简历（TXT/DOCX/文字层 PDF）对比 SmartResume 与 fallback 的字段准确率，记录到 `docs/FORK_LOCK.md` 1.1 的"未实测"位置；
3. 重点核对 `_normalize()` 的字段映射（`work_experience`/`education`/`skills` 的键名是按契约推测的，**未实测**）；
4. 若准确率不达标，把 `SmartResumeBackend.available()` 的默认路径关掉，明确只走 fallback。

在完成上述验证之前，`HARDWARE_MIN["verified"]` 必须保持 `False`，报告里的 `parsing_mode` 只能写 `fallback`。

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
| 硬件要求未实测 | `test_smartresume_hardware_requirements_are_recorded_and_unverified` | `verified is False` |
| 结构不合契约 | `test_parse_failure_raises_contract_error` | 抛 `PARSE_FAILED`，不向上传坏结构 |
| ID 连续 | `test_fallback_parser_keeps_ids_continuous` | `exp_01..exp_NN` |

复跑：`cd starter/sidecar && python -m pytest tests/test_resume_parser.py -q`
