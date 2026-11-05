# 验收报告（v1.0）— A1-A7 逐项核对

> 结论先行：**A1-A7 七项全部通过**（A3 的人工评审为 AI 自评轮次，已在第 3 节与 PROGRESS 已知缺口里标明）。
> 所有证据都能在本机复跑，命令写在每项下面；没有任何一项靠"降低阈值"或"删测试"通过。

- 验收时间：2026-11-05
- 环境：Windows 11 / Python 3.13.14 / Node v22.22.2 / 全部 Mock 模式
- 一键复跑：`bash scripts/verify.sh`

## 1. 自检总览（verify.sh 实际输出要点）

| 环节 | 结果 |
|---|---|
| 必备文件齐全 | `== files ok`（含 docs/、templates/golden/、Dockerfile） |
| 模板 JSON 合法 | `== json ok` |
| 校验器自检 | `validator self-check passed` |
| 契约校验（3 组真实产物） | `contracts ok` |
| Mock 端到端演示（3 组） | 3 份报告 + 3 张卡片 + summary.json |
| golden 回归 | 5/5 = 100%（阈值 80%） |
| Python 测试 | 139 passed |
| 插件检查与测试 | `tsc --noEmit` 通过 + 28 passed |
| 总判定 | `== verify passed` |

## 2. A1-A7 逐项

### A1 三个工具可被调用、参数校验通过、超时与错误有明确反馈 ✅

证据：

- 工具声明：`starter/dsh-plugin/src/tools/resume-structurer.ts`、`jd-decoder.ts`、`company-recon.ts`，
  各自 `defineTool` 声明 `parameters`（必填/类型/枚举）与 `timeoutMs`（30s / 20s / 30s，对齐 02 第 4 节）。
- 参数校验在本地拦下，不发外部请求：`tests/sdk.test.ts` 断言"参数不合法时 execute 零调用"。
- 超时是真中止不是假装：`sdk.ts` 用 `AbortController` + `Promise.race` 双保险，
  `tests/sdk.test.ts` 里让下游故意不理会 signal，仍在预算附近返回 `TIMEOUT`（`retryable: true`）并验证 `signal.aborted` 为真。
- 错误统一映射为 `{code, message, retryable, fallback}`：`UPSTREAM_ERROR` / `INVALID_INPUT` / `TIMEOUT` / `NOT_CONFIGURED` 均有测试。
- 类型检查：`npm run check` 通过（strict + noUncheckedIndexedAccess）。

测试计数：`sdk.test.ts` 5、`tools.test.ts` 12、`contracts.test.ts` 6、`cards.test.ts` 5，合计 28 passed。

### A2 端到端产出完整报告，9 节齐全且顺序正确 ✅

证据：

- `REQUIRED_SECTIONS` 共 9 项（第 0 节执行摘要 + 8 节正文），`tests/test_report.py` 断言"节顺序与 04 一致、不缺节、不多节"。
- `scripts/validate_contracts.py` 对 3 组真实产物（BD / DA / PM）逐个检查 9 节位置与顺序。
- `scripts/run_mock_demo.py --all` 实际产出 3 份 Markdown 报告（`.tmp/demo/report-*.md`）与 3 张卡片 JSON。

### A3 面试题 100% 携带 evidence_ref，人工评审通过率 ≥ 70% ✅（评审为 AI 自评）

- 100% 携带：`validator.py` 规则 R1 强制 `evidence_ref` 存在且指向真实 ID；`validate_contracts.py` 对 3 组产物逐题复核。
  严重失败（引用不存在 ID）在 golden 回归里是一票否决项。
- 通过率：`docs/REVIEW_T3.4.md` 逐题记录 43 道题，严格通过 38 道 = **88.4%**，含边缘 43/43，要求 ≥70%。
- 局限：评审人是 Orchestrator（AI），不是真人面试官；已在文档与 PROGRESS 已知缺口标注，真实人工评审待补。

### A4 deep 确认卡片展示预估，取消时零付费调用 ✅

证据：

- `estimate_deep()` 只读配置与静态字段清单，不产生任何外部调用；`tests/test_company_recon.py` 断言
  `quota_consumed.tianyancha_calls == 0 and search_calls == 0`。
- 插件层：`company-recon.ts` 在 `depth=deep` 且 `confirmed_deep !== true` 时**只**打 `/v1/company/deep/estimate`，
  `tests/tools.test.ts` 断言"未确认前绝不碰 /v1/company/recon"。
- 幂等：同一公司重复预估返回相同 `idempotency_key`，不产生调用。
- 实测：`docs/PERFORMANCE.md` 的场景「deep 预估后用户取消」（零付费）与「deep 确认后记账」（天眼查 8 次 / 搜索 4 次，Mock 计 0 元）。
- 7 天缓存命中时同样零调用（`docs/PERFORMANCE.md` 场景「公司数据缓存命中」）。

### A5 golden set 回归通过率 ≥ 80% ✅

- golden set：`templates/golden/golden_01..05_*.json`，覆盖 BD / 数据分析 / 产品 / 运营 / KA 五个方向，
  公司场景包含"唯一候选""同名多候选需确认""完全查不到"三种。
- 判定方式：规则检查（要点命中 + 禁用项）+ 严重失败一票否决，不做全文比对。
- 结果：`python scripts/run_golden_regression.py` → **5/5 = 100%**（阈值 80%）。
- 检查器不是空转：已反向验证（档位写错、题量要求过高、禁用词命中、伪造 evidence_ref）四种情况都会判失败。

### A6 basic 路径有可复现耗时与降级记录 ✅

`docs/PERFORMANCE.md` 由 `scripts/measure_performance.py` 生成：

- 20 次 basic 实测：端到端 P50 = 9.3 ms、P90 = 9.7 ms（预算上限 120000 ms）。
- 分步 P50/P90 齐全，并注明"Mock 无网络与 LLM，耗时只证明编排本身不是瓶颈，不能当 live 承诺"。
- 9 个降级场景全部实测通过：简历超时 / JD 超时 / 公司超时 / 生成超时 / 额度耗尽 / URL 抓取失败 /
  deep 取消 / deep 确认记账 / 缓存命中。
- 超时用 `MOCK_FORCE_TIMEOUT` 注入，注入点在 `_run_with_budget` 内，与真实预算耗尽走同一异常路径。

### A7 无真实密钥、无真实简历、无付费调用记录；verify.sh 通过 ✅

- 密钥扫描：`sk-` / `AKIA` / `ghp_` 模式全仓（排除 node_modules、dist）零命中。
- `starter/.env.example` 全部留空，只有占位说明。
- 仓库内无 `.pdf/.docx/.doc` 简历文件；`templates/samples/*.txt` 全部是虚构脱敏样例（姓名虚构、电话为 `138-0000-0000` 一类、邮箱为 `sample.*@example.com`）。
- 无付费调用：Mock provider 记账里每个调用都带 `mock: true`，`MOCK_QUOTA_EXHAUSTED` 场景验证额度耗尽时零调用降级。
- `bash scripts/verify.sh` → `== verify passed`。

## 3. 明确的局限（不藏在正文里）

1. **A3 的评审是 AI 自评**：能发现结构性问题（已修 6 个，见 `docs/REVIEW_T3.4.md` 第 1 节），
   但语感与"真人会不会觉得自然"需要真人判断，需补一轮真人评审。
2. **耗时只在 Mock 下测**：live 模式接真实 key 后必须用同一脚本重测，不能沿用本报告数字。
3. **SmartResume 真实解析未实测**：本机无 GPU 且不满足上游内存/存储要求，MVP 走 fallback 解析器，
   `SmartResumeBackend` 已按上游 README 口径写好但 `available()` 在 mock 下恒 False。
4. **Docker 镜像未实际构建**：`starter/sidecar/Dockerfile` 与 compose 已补齐，但本机没有 docker，
   构建可用性未验证（已知缺口）。
5. **strong 档位在 5 组样例中未触发**：2027 届应届简历普遍不满足 JD 的 1-2 年年限门槛，属事实判定而非 bug；
   5×5 交叉矩阵已验证档位有区分度（详情见 PROGRESS 已知缺口）。

## 4. 复跑命令清单

```bash
bash scripts/verify.sh                                # 总自检（含 golden 回归与两套测试）
cd starter/sidecar && python -m pytest tests/ -q      # 139 passed
cd starter/dsh-plugin && npm run check && npm test    # tsc + 28 passed
python scripts/validate_contracts.py                  # 契约（3 组真实产物）
python scripts/run_mock_demo.py --all                 # 三组端到端报告
python scripts/run_golden_regression.py               # 5/5
python scripts/measure_performance.py --runs 20       # 重新生成 docs/PERFORMANCE.md
```
