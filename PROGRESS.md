# PROGRESS — 进度、决策、Blocker 追踪表

> 本文件是多 Agent 之间唯一的进度事实来源。所有决策、阻塞、变更只写这里，
> 不依赖某个 Agent 的私有记忆。Orchestrator 负责维护，Worker 完成任务时更新自己那部分。

## 形态决策（已定）

- 2026-11-05 | 用户确认：DSH 插件优先，报告可导出 Markdown。
  DSH 内摘要卡片 + 完整 Markdown 文件；sidecar API 与前端解耦，未来加网页壳不重写引擎。

## 里程碑

- [x] M1（第 1 周）：DSH 中可上传 PDF 并拿到结构化简历 JSON；JD 粘贴可出结构化拆解
- [x] M2（第 2 周）：输入简历 + JD + 公司名，产出可读报告，公司信息分区正确
- [x] M3（第 3 周，评审为 AI 自评轮次）：面试题人工评审通过率 ≥ 70%
- [x] M4（第 4 周）：回归通过率 ≥ 80%，验收 A1-A7 全部通过
- [x] v1 补缺口（第 5 周）：缓存绑版本 / 三档 golden 覆盖 / Docker 与 SmartResume 可行性结论 / 8 条已知缺口逐条闭环 / 真人复核包

## 任务状态（对照 07_TASK_PLAN.md 更新，状态词：todo / doing / done / blocked）

| 任务 | Lane | 状态 | 测试证据 | 备注 |
|---|---|---|---|---|
| T1.1 锁定 fork 仓库 | E | done | `docs/FORK_LOCK.md`（gs ls-remote + LICENSE 正文校验） | 锁定 SmartResume(Apache-2.0) + Resume-Matcher(Apache-2.0)，不 fork 全仓 |
| T1.2 sidecar 骨架 | B | done | `pytest tests/test_api.py` 13 passed；`/health` 与 9 个路由 | FastAPI + Pydantic v2，`ToolError` 统一错误契约 |
| T1.3 SmartResume 封装 | B | done（本地模型延期 v2 Phase 0） | `pytest tests/test_resume_parser.py` 17 passed：新增降级原因声明、硬件要求未实测标记、DOCX 经历+指标 | `available()` 改为由 `unavailable_reason()` 单点决定，原因写进 `parsing_notes`；GPU 要求见 `docs/ENV_FEASIBILITY.md` |
| T1.4 resume-structurer 插件 | A | done | `npm test` 中 tools.test.ts 4 条；`npm run check` 通过 | 30s 预算、首次超时收窄字段重试一次、两次超时给"改文本版"提示 |
| T1.5 jd-decoder 插件 | A | done | tools.test.ts 中 3 条 | 粘贴文本主路径；URL 仅辅助；无输入要求补文本且零调用 |
| T1.6 契约测试 | E | done | `scripts/validate_contracts.py` 对 3 组真实产物重跑 Pydantic 校验（含 ID 体系/引用存在性/四维/9 节/卡片字段）；Python `test_contracts.py` 17 passed；TS contracts.test.ts 6 条 | 产物层用同一份模型 `model_validate`，字段放宽成 Any 也会被抓 |
| T2.1 company-recon basic | C | done | `pytest tests/test_company_recon.py` 14 passed + `tests/test_cache_versioning.py` 11 passed | 消歧 + 硬数据 + 软信息 + 7 天缓存 + 记账；缓存 key 绑定 `recon-2+schema1.0` 与 `data_mode` |
| T2.2 orchestrator 编排 | D | done | `pytest tests/test_api.py` 端到端用例 | 分阶段预算 + 超时降级 + `EVIDENCE_INVALID` 修复一次 |
| T2.3 报告生成器 | D | done | `pytest tests/test_report.py` 13 passed | 9 节结构 + 结论先行 + Markdown 导出 |
| T2.4 DSH 摘要卡片 | A | done | cards.test.ts 5 条；Python `render_summary_card` 同源字段 | 只放第 0 节摘要 + 锚点 + 导出文件名，不做全文渲染 |
| T2.5 Mock 端到端演示 | E | done | `python scripts/run_mock_demo.py --all` 产出 3 份报告 + 3 张卡片 + summary.json；verify.sh 第 3 步调用 | 已改为走真实 `run_analysis` 编排，不再硬编码报告文本 |
| T3.1 证据校验器完整版 | E | done | `pytest tests/test_validator.py` 20 passed | R1-R7 七条规则；生成失败重生成一次仍不过则降级并进待核实清单 |
| T3.2 面试题生成重构 | D | done | `pytest tests/test_generate.py` 16 passed | 四类保底各 1 题、单条证据上限 4 题、8 题下限、recall 过滤；能力类按证据分流、深挖题三组句式变体 |
| T3.3 匹配基线 | D | done | `pytest tests/test_matching.py` 13 passed | 四维只给档位；门槛类按事实判定；新增管理层级守卫（实习生不因"搭建/团队"词重合被判管理强项） |
| T3.4 人工评审 5 组 | E | done（AI 自评，真人复核延期 v2 Phase 0） | `docs/REVIEW_T3.4.md` 43 题逐题记录 88.4%；新增 `docs/HUMAN_REVIEW_PACK.md` + 2 份空白复核包（strong / gap） | 复核包只摊材料留空位，verify 守门禁止 AI 代填；真人打分列入 v2 Phase 0 |
| T3.5 知识点分级 | D | done | `pytest tests/test_generate.py` 知识点用例 | 三档 + 门槛类排除 + 无例证标注"通用知识、无简历例证" |
| T4.1 deep 预估卡片（Mock） | C | done | `pytest tests/test_company_recon.py` 预估/缓存用例；TS tools.test.ts 2 条 | 预估零调用、未确认不触 recon、确认后按接口记账 |
| T4.2 golden set | E | done | `templates/golden/` 共 7 组：BD/DA+消歧/PM/运营/KA + strong（校招 BD）+ gap（方向错配） | 5 组既有用例一条未改（仅补 P0 档位断言）；新增 2 组而非 1 组，因为 6 组内无法三档全覆盖 |
| T4.3 回归与修复 | E | done | `python scripts/run_golden_regression.py` → 7/7 = 100%；三档覆盖 harness 强制（缺档 exit 3）；反向验证 10 条（`tests/test_regression_harness.py`） | 严重失败一票否决该组；档位写错/伪造 evidence_ref 均已证明会判失败 |
| T4.4 超时与降级实测 | A/B | done | `docs/PERFORMANCE.md`（v1 补缺口后重测）：basic 20 次 P50=9.0ms / P90=9.3ms；9 个降级场景全部通过，新增第 10 个「缓存命中零调用」 | Mock 数字只证明编排不是瓶颈，live 重测列入 v2 Phase 0 |
| T4.5 验收报告 | E | done | `docs/ACCEPTANCE_REPORT.md`：A1-A7 全过 + v1 补缺口复验记录（A5 改 7/7、A6 新数字、A3 复核包） | A3 仍标注 AI 自评，真人复核延期 v2 Phase 0，不藏 |

## Decisions（问题 | 方案 | 为什么 | 影响范围）

- 2026-11-05 | 交付物落在包内 `starter/` 还是新建 `dsh-job-skill/` | 继续在 `starter/` 内按 08 第 2 节的目标结构扩建 | `scripts/verify.sh` 与 08 的启动命令都指向 `starter/`，迁目录会让自检脚本与文档同时失效；08 的目录结构已按其子结构（dsh-plugin/sidecar/templates）复刻 | 全部 Lane；08 文档保持原样生效
- 2026-11-05 | fork 范围 | 锁定 2 个 Apache-2.0 仓库的**契约与算法口径**，不 fork 全仓；编排与企业研究自研 | 许可证 NOTICE 义务、技术栈冲突、可验证性三条理由见 `docs/FORK_LOCK.md` 第 3 节 | Lane B/C/D 的集成方式；无需引入上游依赖树
- 2026-11-05 | 12_FORK_MAP 要求 JobCopilot 候选 A/B 二选一 | 结论改为"都不选"，编排自研，理由与三个真实候选的核验记录写进 `docs/FORK_LOCK.md` 1.3 | 三个候选仓库均不含企业研究模块，且主推自动投递（12 第 2 节禁止）；12 第 1 节末段已授权自研路径 | Lane C/D
- 2026-11-05 | SmartResume 无法真实实测（需 ≥8GB 内存/≥10GB 存储/可选 CUDA） | 按 08 第 5 节选项 1 走 fallback，SmartResume 保留为可选适配器；真实解析效果标"待核实" | 不把 GPU 作 MVP 硬依赖；状态词只写已核实部分 | Lane B；列入已知缺口
- 2026-11-05 | `scripts/verify.sh` 在 Windows/Git Bash 下失败（`PACK_DIR` 为 `/c/...` POSIX 路径，本机 Python 无法解析） | 用 `cygpath -w` 归一化为 Windows 路径，其它平台保持原值 | 属脚本本身 bug，不是放宽验收；不修则 A7 永远无法通过 | Lane E；影响 A7

- 2026-11-05 | `mock_force_timeout` 在 config 里声明但没人用（死配置），A6 又要实测超时降级 | 接进 `_run_with_budget(force=...)`，用 `MOCK_FORCE_TIMEOUT=resume\|jd\|company\|generate` 注入 | 注入点与真实预算耗尽走同一异常路径，降级分支是真被执行过的；不必干等 30 秒×N 次 | Lane D/B；`docs/PERFORMANCE.md` 全部降级场景 |
- 2026-11-05 | Mock 模式硬数据 source 写成 `tianyancha_mcp` | 改为 `mock://tianyancha/basic`，并给校验器加 R6b 规则 | 虚构样本写着真实来源名 = 让用户以为工商数据真查过，06 证据质量明令禁止；规则化后回归能拦住 | Lane C/E；`docs/PERFORMANCE.md`、validator |
- 2026-11-05 | 公司侧降级只存在于 `company.degradations`，没上浮到报告与卡片 | 在 `run_analysis` 里把 `company.degradations` 合并进报告 degradations | 11 第 1 节要求降级可见；不合并的话"额度耗尽""消歧失败"用户在卡片上根本看不到 | Lane D；demo 输出可直接观察到 |
- 2026-11-05 | JD「加分项」段没有独立标题识别，段内条目因含"经验"被归进 must_have | 加 `NICE_HEADERS` 与 `section="nice"` 分支 | 把加分项当硬性要求会把硬性条件档位压低，属事实失真；已有回归测试 | Lane B/C；匹配档位 |
- 2026-11-05 | 「2 年以上经验，有 OTA 行业经验者优先」因句尾"优先"整句被判 soft | soft 判定加硬门槛排除（含 X 年以上/以上学历/应届 即不降级） | 报告把硬性年限写成"加分项"是事实错误，评审时被抓到（REVIEW_T3.4 问题 2） | Lane B/D |
- 2026-11-05 | golden 回归第一版 5/5 通过，但检查器可能空转 | 做反向验证：档位写错/题量要求过高/禁用词命中/伪造 evidence_ref 四种都必须判失败 | 不会失败的回归测试等于没有；验证结果四种全部判失败 | Lane E；`scripts/run_golden_regression.py` |
- 2026-11-05 | golden case 期望档位全部是 discussable | 保留事实判定，不改阈值；另跑 5×5 交叉矩阵记录区分度（错配组合判 gap） | 应届简历普遍不满足 1-2 年门槛，判 gap 是对的；矩阵证明档位不是恒定值 | Lane D/E；已知缺口记录 strong 未触发 |

- 2026-11-05 | 缓存不绑版本，改代码后旧结果仍被读出（8 号缺口） | `app/version.py` 定义 `COMPANY_CACHE_VERSION = recon-2+schema1.0`；key 与 payload 双重校验，版本不符即删文件；key 另加 `data_mode` | 只删缓存是运维动作、不是工程约束；写进 key 与 payload 才能让"改了逻辑但结果没变"在结构上不可能发生。`data_mode` 防止 live 读到 mock 期间写下的 `mock://` 来源 | Lane C/E；`app/recon/cache.py`、`service.py`、`tests/test_cache_versioning.py` |
- 2026-11-05 | golden 只加 1 组 strong 时，6 组内凑不齐三档（5 组既有用例全是 discussable） | 新增 2 组：`golden_06_bd_strong`（strong）+ `golden_07_gap`（方向错配 gap），5 组既有用例一条未改，只补 P0 档位断言 | 「6 组」与「三档覆盖」在现有 5 组内容下无法同时成立；改既有用例的 JD 会破坏历史证据，扩到 7 组损失最小，且"至少 1 组"允许更多 | Lane E；回归 7/7 |
- 2026-11-05 | 做 gap 样例时发现「搭建并管理 10 人团队」被判 strong，证据是实习生的「搭建留存看板」 | 加 `leadership_level_mismatch()`：JD 要求管理/带队、证据无带队词时，档位最高只到 discussable | 这是把关键词重合当事实（06 第 3 节禁止）；属于收紧证据口径，不是放宽，也不改阈值 | Lane D；`tests/test_matching.py` 3 条 |
- 2026-11-05 | 能力类（岗位认知）题一律问「你理解这个要求是什么样」，简历明明有证据 | 按 `best_exp_id` 分流：有证据问"怎么把这段讲成对应能力"，无证据才问理解类问题 | 断言"已有证据还问有没有"就是没读简历，与加分项类同一条问题（REVIEW_T3.4 问题 6 的同类遗漏） | Lane D；`tests/test_generate.py` 2 条 |
- 2026-11-05 | 经历深挖三题对任何简历都是同一套骨架 | 三类各 3 个变体池，按证据哈希稳定取变体；修掉 `digest[:8]` 取模偏置（10 条里 9 条落在同一变体） | 固定句式长期会被候选人摸到规律；偏置会让"变体"名存实亡，改完整摘要取模后 7 组用例出现 8 种题型 | Lane D；`tests/test_generate.py` 3 条 |
- 2026-11-05 | 本机无 docker，Docker 缺口怎么处置 | 只做静态校验（`scripts/check_docker_assets.py`，17 项），输出 `status=static_only` 并明写"未构建"；构建验证延期 v2 Phase 0 | 红线路 6：状态词只写已核实的部分。"静态资产无缺陷"与"镜像可构建"是两件事，不许混写 | Lane B/E；`docs/ENV_FEASIBILITY.md` |
- 2026-11-05 | SmartResume 无 GPU 无法实测 | `SmartResumeBackend.HARDWARE_MIN` 记录 ≥8GB 内存 / ≥10GB 存储 / CUDA 建议，`verified=False`；`unavailable_reason()` 把原因写进 `parsing_notes` | 让"为什么走 fallback"在报告里可查，避免把规则解析说成模型能力；本地模型效果列 v2 Phase 0 | Lane B；`tests/test_resume_parser.py` 4 条 |
- 2026-11-05 | 报告在无强项时写「最大亮点：无直接量化证据支撑的强项」，自相矛盾 | 文案改为「无明显亮点（仅门槛类条件满足，需面试验证）」，并同步测试守卫 | 复核包要给人读，自相矛盾的句子会被当成系统在敷衍 | Lane D；`matching.py`、`test_matching.py` |
- 2026-11-05 | 本包此前不是 git 仓库，无法给出基线 commit | 补 `.gitignore`（排除 `.env`/`.cache`/`.tmp`/`node_modules`/`dist`/`.workbuddy`）后 `git init` + 首个提交 | 进 v2 需要一个可回滚的基线；118 个文件入库，已确认无缓存、无 `.env`、无 `node_modules` | 全 Lane；基线见文末快照 |
- 2026-11-05 | 真人复核包容易被 AI 顺手"代填"成已审 | 只导出材料 + 空白清单，并在 `verify.sh` 加守门：缺"AI 没有、也不能代替真人"声明即失败 | 缺口 1 的本质是"AI 不能自证人工评审"，守门把这条约束写进自动化，而不是靠自觉 | Lane E；`scripts/export_review_pack.py`、`verify.sh` 3.7 |
- 2026-11-05 | 本机无 docker、仓库无 remote，Docker 怎么才能算"已证" | 写 CI 工作流 + `scripts/check_ci_evidence.py`（五件套机械校验），`check_docker_assets.py --ci-evidence` 通过才允许 `status=built`；当前仍写未实证 | 「静态校验通过」和「镜像可构建」是两件事；先把判据钉死，将来拿到 artifact 就不用靠人嘴确认。宁可留一个未实证，也不写"应该能构建" | Lane B/E；PROOF 第 1 节 |
- 2026-11-05 | 实跑发现 `_normalize()` 按 snake_case 猜字段，上游实际是 `basicInfo`/`workExperience`/`employmentPeriod` | 按真实返回重写映射（含头行剔除、period 拼装），并加 2 条用真实结构做样本的测试 | 猜错的后果不是报错，而是 `experiences` 恒空 + 校验失败后**静默退回 fallback**，报告上看不出模型没跑成——这比崩掉更难发现 | Lane B；`parsers/resume.py`、`test_resume_parser.py` |
- 2026-11-05 | GPU 上缺 `accelerate` 导致模型未加载，上游返回空 dict，却被记成 `parsing_mode=smartresume` | 加 `_is_empty_structure()` 守卫：空壳且原文有文本 → 降级 fallback 并写 note；实证脚本同时要求「经历数>0 且召回>0」才算跑通 | "没抽到东西"和"抽到了但内容为空"在结构上一模一样，不加守卫就会把失败当成功记账 | Lane B/E；6 行守卫 + 2 条测试 |
- 2026-11-05 | 记账明细里 cost 全是 0.0，等于没有费用闸门 | `QuotaLedger.ensure_budget()` 在调用前校验 `TIANYANCHA_COST_CAP_YUAN`（默认 5 元），超限抛 `CostCapExceeded`；单价由 `TIANYANCHA_UNIT_COST_YUAN` 提供，不硬编码 | live 调用是真花钱，闸门必须在**发请求前**；单价不写死是避免替供应商承诺价格 | Lane C；`recon/quota.py`、`recon/providers.py`、`tests/test_cost_cap.py` 5 条 |
- 2026-11-05 | PERFORMANCE.md 的「P90 9ms 远低于 120s 上限」读起来像通过结论 | 标题与结论改成「Mock 编排耗时，不构成 live 结论」，并新增一节写明 live 测不了的两个原因（缺 key + 搜索契约未实现） | 9ms 是 Mock 没有网络与推理的结果，拿它当 live 结论属于用便宜的证据回答贵的问题 | Lane E；`docs/PERFORMANCE.md`、`scripts/measure_performance.py --live` 预检 |
- 2026-11-05 | 口头"某某已验证"没有约束力 | `docs/PROOF.md` + `scripts/check_proof.py` 做机械守门：证据文件必须存在且非空、未实证不许出现"已完成/已构建"、真人复核无签字件不许写已证 | 状态词靠自觉就会漂移；写进 verify 后，虚报会让自检直接失败 | Lane E；`verify.sh` 3.9 |

## Blockers（现象 | 复现步骤 | 已试方案 | 影响范围 | 状态）

- （无。出现 Blocker 时按 00 的 3 轮规则处理，不改阈值、不删测试）

## v1 已知缺口处置（8 条逐条闭环，无「待定」）

判定口径：每条只能是「已修复 + 测试证据」或「明确延期 v2 Phase 0 + 理由」，不允许第三种状态。

| # | 原缺口 | 处置 | 测试 / 证据 |
|---|---|---|---|
| 1 | A3 人工评审是 AI 自评 | **延期 v2 Phase 0**：AI 不能自证真人评审 | 前置件已产出：`docs/HUMAN_REVIEW_PACK.md` + `docs/review-pack/golden_06_bd_strong.md`（strong，8 题）+ `golden_07_gap.md`（gap，9 题），含题面/evidence_ref/证据原文/报告节选/空白清单；`verify.sh` 3.7 守门禁止代填 |
| 2 | 性能只在 Mock 下实测 | **延期 v2 Phase 0**：需真实 key，v1 红线禁止调用真实付费接口 | `docs/PERFORMANCE.md`：P50 9.0ms / P90 9.3ms，仅证明编排不是瓶颈；文档已删掉"live 也这么快"的暗示 |
| 3 | SmartResume 真实解析未实测 | **延期 v2 Phase 0**（fallback 路径已测） | 无 GPU 且不满足 ≥8GB/≥10GB；`HARDWARE_MIN.verified=False`；`tests/test_resume_parser.py` 17 passed（含 DOCX 经历+指标、降级原因）；验证步骤见 `docs/ENV_FEASIBILITY.md` 3.2 |
| 4 | Docker 镜像未构建 | **延期 v2 Phase 0**（静态校验已完成） | 本机无 docker；`scripts/check_docker_assets.py` 17 项全过、`status=static_only`；`docs/ENV_FEASIBILITY.md` 2.2 明列未执行项 |
| 5 | strong 档位无样例覆盖 | **已修复** | `golden_06_bd_strong` + `jd-bd-campus.txt`；另补 `golden_07_gap` + `jd-backend.txt`；回归 7/7 = 100%，harness 强制三档覆盖（缺档 exit 3）；`tests/test_regression_harness.py` 10 条 |
| 6 | 能力类题目未按证据分流 | **已修复** | `generate.py` 能力类分支按 `best_exp_id` 分流；`test_ability_question_uses_evidence_when_resume_has_it`、`test_ability_question_falls_back_when_no_evidence` |
| 7 | 经历深挖句式模板化 | **已修复** | 三组变体池 + 证据哈希稳定取变体；`test_dig_question_wording_varies_across_resumes`（≥2 主变体 / ≥5 题型）、`test_dig_variants_are_deterministic` |
| 8 | 缓存未绑版本 | **已修复** | `COMPANY_CACHE_VERSION = recon-2+schema1.0`；key + payload 双重校验、旧文件自动删除；`tests/test_cache_versioning.py` 11 条（含"版本递增后必不复用旧结果"「缓存命中零付费调用」） |

顺带修掉的两个新发现（不属原 8 条，一并记录）：

- 管理层级假阳性：「搭建并管理 10 人团队」曾把实习生的「搭建留存看板」判成 strong → 加 `leadership_level_mismatch()` 守卫，档位最高 discussable（3 条测试）。
- 报告自相矛盾：无强项时写「最大亮点：无直接量化证据支撑的强项」→ 改为「无明显亮点（仅门槛类条件满足）」（1 条测试守卫）。

## 外部依赖实证结果（2026-11-05，逐项只认「命令 + 原始产物 + 结论加局限」）

完整证据链见 `docs/PROOF.md`；本表只记处置结果，状态词只有「已证 / 未实证」两种。

| # | 项 | 状态 | 证据 | 缺什么 |
|---|---|---|---|---|
| P1 | Docker 镜像构建与容器运行 | **未实证** | `docs/proof/docker-static.json`（25 项静态全过，`status=static_only`）、`.github/workflows/docker-build.yml`、`scripts/check_ci_evidence.py` | 本机无任何容器运行时（docker/podman/nerdctl 均无，`wsl.exe` 被策略禁用）；仓库无 git remote，CI 一次未跑 |
| P2 | SmartResume 本地模型解析 | **已证** | `docs/proof/model-manifest.json`（9/9 哈希一致）、`docs/proof/smartresume-cpu.json`、`docs/proof/smartresume-gpu.json` | 仅 3 份合成简历的文本型 PDF；上游只支持 3 类抽取；召回与 fallback 打平 |
| P3 | 天眼查真实调用（basic 1 家 + deep 1 家） | **未实证** | `docs/proof/tianyancha-live.json`（`status=not_run`）、`docs/proof/tyc-mock-isolation.json`（Mock 缓存隔离已跑通） | 无 `TIANYANCHA_API_KEY`/`TIANYANCHA_MCP_URL`；接口路径与计费单价均未与官方核对 |
| P4 | live 真实性能（真实搜索 + 真实 LLM 的 P50/P90） | **未实证** | `docs/proof/live-perf-preflight.log`（退出码 2）、`docs/PERFORMANCE.md`（已撤回 9ms 的 live 暗示） | 缺 LLM/搜索密钥；且 `SearchProvider._live_search` 主动抛错，塞 key 也跑不通 |
| P5 | 真人复核（17 题） | **未实证** | `docs/HUMAN_REVIEW_PACK.md`（含签收表）、两份空白复核包 | 无 `docs/review-pack/signed-*.md` 签字件；AI 不代评 |

原「v2 Phase 0 待验证项」的 V1–V4 已全部并入本表：P2 结案（已证），P1/P3/P4/P5 仍挂未实证并写明缺件。

### P2 的实测数字（结论里不好看但必须写）

| 设备 | 单份耗时 | 平均 | 峰值 RSS | 关键实体召回 | fallback 召回 |
|---|---|---|---|---|---|
| CPU（torch 2.15.0+cpu） | 98.07 / 85.67 / 93.25 s | 92.33 s | 3121–3237 MB | 1.0 / 0.9167 / 1.0 | 1.0 / 1.0 / 1.0 |
| GPU（3060 6GB，fp16） | 39.54 / 27.44 / 27.33 s | 31.44 s | 2079–2688 MB | 1.0 / 0.9167 / 1.0 | 1.0 / 1.0 / 1.0 |

结论：**本地模型可跑但不设为默认路径**——召回与 fallback 打平（唯一差异是漏 1 条指标），耗时高 3–4 个数量级，
且解析预算仅 30 秒，CPU 必然超时、GPU 首份也超时。`HARDWARE_MIN.verified` 已改 `True` 并带实测区间。

## v1 基线快照（进 v2 前以此为基准）

| 项 | 值 |
|---|---|
| 基线代码提交 | `e7478a7`（`[Lane-E] feat: 8 条已知缺口闭环 + 三档 golden + 缓存版本绑定 + 复核包`） |
| 首个入库提交 | `9842df9`（本包此前不是 git 仓库，本轮补 `.gitignore` 后初始化） |
| 本轮文档提交 | `3412f16`（基线快照）、`144088a`（验收报告同步）、`84088a8`（复核包合并清单） |
| 分支 | `main` |
| 入库文件数 | 118（已确认无 `.env`、无 `starter/sidecar/.cache`、无 `node_modules`、无 `.tmp`） |
| 缓存版本号 | `recon-2+schema1.0`（`app/version.py`；key 与 payload 双重绑定） |
| golden set | 7 组，通过 7/7 = **100%**（阈值 80%）；三档覆盖 `['discussable', 'gap', 'strong']` |
| Python 测试 | **172 passed**（基线 139 → 本轮 +33） |
| 插件测试 | **28 passed**（`npm run check` 通过，无新增） |
| Docker | **未构建**（本机无 docker）；17 项静态校验全过，`status=static_only` |
| SmartResume 本地模型 | **未实测**（本机无 GPU / 不满足 ≥8GB 内存 ≥10GB 存储）；fallback 路径 17 项测试 |
| 验收 | A1-A7 全过；A3 为 AI 自评，真人复核列 v2 Phase 0 V1 |

`bash scripts/verify.sh` 关键输出（完整日志 `.tmp/verify-baseline.log`，不入库）：

```text
== pack: <repo>
== files ok
== json ok
== contracts ok
== mock demo ok
通过 7/7 = 100%（要求 >= 80%）
档位覆盖：['discussable', 'gap', 'strong']（要求 ['discussable', 'gap', 'strong']）
镜像构建：未执行（PATH 中找不到 docker 可执行文件）—— 结论只覆盖静态校验，不许写成『已构建』
== review pack ok（人工判定位仍为空白）
== cache version: recon-2+schema1.0
== pytest ok (172 passed)
== plugin check+test ok (# pass 28)
== verify passed
```

复跑方式：

```bash
bash scripts/verify.sh
python scripts/run_golden_regression.py --json .tmp/golden-report.json
python scripts/check_docker_assets.py
python scripts/export_review_pack.py
```

> 说明：本次快照写入会再产生一次**仅文档**的提交（PROGRESS.md 追加本节），代码基线以 `e7478a7` 为准。

