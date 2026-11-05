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

## 任务状态（对照 07_TASK_PLAN.md 更新，状态词：todo / doing / done / blocked）

| 任务 | Lane | 状态 | 测试证据 | 备注 |
|---|---|---|---|---|
| T1.1 锁定 fork 仓库 | E | done | `docs/FORK_LOCK.md`（gs ls-remote + LICENSE 正文校验） | 锁定 SmartResume(Apache-2.0) + Resume-Matcher(Apache-2.0)，不 fork 全仓 |
| T1.2 sidecar 骨架 | B | done | `pytest tests/test_api.py` 13 passed；`/health` 与 9 个路由 | FastAPI + Pydantic v2，`ToolError` 统一错误契约 |
| T1.3 SmartResume 封装 | B | done（限制项见备注） | `pytest tests/test_resume_parser.py` 13 passed | `SmartResumeBackend` 已按上游 README 口径写好但 `available()` 在 mock 下恒 False；真实解析效果仍"待核实"（无 GPU），链路走 fallback 解析器 |
| T1.4 resume-structurer 插件 | A | done | `npm test` 中 tools.test.ts 4 条；`npm run check` 通过 | 30s 预算、首次超时收窄字段重试一次、两次超时给"改文本版"提示 |
| T1.5 jd-decoder 插件 | A | done | tools.test.ts 中 3 条 | 粘贴文本主路径；URL 仅辅助；无输入要求补文本且零调用 |
| T1.6 契约测试 | E | done | `scripts/validate_contracts.py` 对 3 组真实产物重跑 Pydantic 校验（含 ID 体系/引用存在性/四维/9 节/卡片字段）；Python `test_contracts.py` 17 passed；TS contracts.test.ts 6 条 | 产物层用同一份模型 `model_validate`，字段放宽成 Any 也会被抓 |
| T2.1 company-recon basic | C | done | `pytest tests/test_company_recon.py` 14 passed | 消歧 + 工商硬数据 + 搜索软信息 + 7 天缓存 + 记账 |
| T2.2 orchestrator 编排 | D | done | `pytest tests/test_api.py` 端到端用例 | 分阶段预算 + 超时降级 + `EVIDENCE_INVALID` 修复一次 |
| T2.3 报告生成器 | D | done | `pytest tests/test_report.py` 13 passed | 9 节结构 + 结论先行 + Markdown 导出 |
| T2.4 DSH 摘要卡片 | A | done | cards.test.ts 5 条；Python `render_summary_card` 同源字段 | 只放第 0 节摘要 + 锚点 + 导出文件名，不做全文渲染 |
| T2.5 Mock 端到端演示 | E | done | `python scripts/run_mock_demo.py --all` 产出 3 份报告 + 3 张卡片 + summary.json；verify.sh 第 3 步调用 | 已改为走真实 `run_analysis` 编排，不再硬编码报告文本 |
| T3.1 证据校验器完整版 | E | done | `pytest tests/test_validator.py` 20 passed | R1-R7 七条规则；生成失败重生成一次仍不过则降级并进待核实清单 |
| T3.2 面试题生成重构 | D | done | `pytest tests/test_generate.py` 11 passed | 四类保底各 1 题、单条证据上限 4 题、8 题下限、recall 口径相关性过滤 |
| T3.3 匹配基线 | D | done | `pytest tests/test_matching.py` 10 passed | 四维 rubric 只给档位；门槛类（学历/年限）按事实判定，不当亮点 |
| T3.4 人工评审 5 组 | E | done（限制项见备注） | `docs/REVIEW_T3.4.md`：43 题逐题记录，严格通过 38 道 = 88.4%（要求 ≥70%） | 评审人是 Orchestrator（AI）不是真人面试官；本轮据此修掉 6 个真实缺陷，真人复核仍待补 |
| T3.5 知识点分级 | D | done | `pytest tests/test_generate.py` 知识点用例 | 三档 + 门槛类排除 + 无例证标注"通用知识、无简历例证" |
| T4.1 deep 预估卡片（Mock） | C | done | `pytest tests/test_company_recon.py` 预估/缓存用例；TS tools.test.ts 2 条 | 预估零调用、未确认不触 recon、确认后按接口记账 |
| T4.2 golden set | E | done | `templates/golden/golden_01..05_*.json`（5 组，覆盖 BD/DA/PM/运营/KA） | 期望要点写成可执行 check，不做全文比对 |
| T4.3 回归与修复 | E | done | `python scripts/run_golden_regression.py` → 5/5 = 100%（阈值 80%）；检查器已做反向验证 | 严重失败（证据造假/付费误调用/隐私泄露）一票否决该组 |
| T4.4 超时与降级实测 | A/B | done | `docs/PERFORMANCE.md`：basic 20 次实测 P50=9.3ms / P90=9.7ms；9 个降级场景全部实测通过 | 超时用 `MOCK_FORCE_TIMEOUT` 注入，走真实降级分支 |
| T4.5 验收报告 | E | done | `docs/ACCEPTANCE_REPORT.md`：A1-A7 全过，每项带复跑命令 | A3 标注为 AI 自评，局限单列一节，不藏 |

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

## Blockers（现象 | 复现步骤 | 已试方案 | 影响范围 | 状态）

- （无。出现 Blocker 时按 00 的 3 轮规则处理，不改阈值、不删测试）

## 已知缺口（完成时仍存在的 P1/P2，写清楚，不藏起来）

- P1｜A3 的人工评审是 AI 自评（Orchestrator），不是真人面试官。已发现并修复 6 个结构性缺陷，
  但"真人会不会觉得问题自然"无法由 AI 代证。补法：找 1-2 位做招聘/业务的人按 `docs/REVIEW_T3.4.md` 的表格重评一轮。
- P1｜性能只在 Mock 下实测（P50 9.3ms / P90 9.7ms）。Mock 没有网络往返与 LLM 推理，不能当 live 承诺。
  补法：接真实 key 后跑 `python scripts/measure_performance.py --runs 20` 重测并覆盖 `docs/PERFORMANCE.md`。
- P1｜SmartResume 真实解析未实测（本机无 GPU，且不满足上游 ≥8GB 内存 / ≥10GB 存储要求）。
  当前走 fallback 解析器，`SmartResumeBackend` 已按上游 README 口径写好但 `available()` 在 mock 下恒 False。
- P2｜Docker 镜像未实际构建：`starter/sidecar/Dockerfile` + `docker-compose.yml` 已补齐，但本机无 docker，构建可用性未验证。
- P2｜strong 档位在 5 组 golden 样例中从未触发：2027 届应届简历普遍不满足 JD 的 1-2 年年限门槛，属事实判定；
  但"强匹配"这一档目前没有样例覆盖，无法证明它可被触发。
- P2｜能力类（岗位认知）题目未按"简历是否已有证据"分流，加分项类已修，能力类仍是统一句式（REVIEW_T3.4 P2-1）。
- P2｜经历深挖三题句式模板化（主 bullet / 口径 / 复盘），换简历不变体，长期会被候选人摸到规律（REVIEW_T3.4 P2-3）。
- P2｜`companies` 缓存与代码版本未绑定：改了硬数据来源标注后，旧缓存仍会被读出来（本次实测踩到过），
  需要手动清 `starter/sidecar/.cache/company`。补法：缓存 key 加 schema/实现版本号。
