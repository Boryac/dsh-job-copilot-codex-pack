"""报告渲染：严格按报告规范的 8 节顺序输出 Markdown（摘要卡片 + 第 1 至 8 节）。

硬性约束：
- 节名与顺序不许自创；缺失的节写"未生成 + 原因"，不许静默删除。
- 硬数据与软信息分区呈现；末尾必须有来源表 + 待核实清单 + 固定免责句。
- 导出默认不含电话/邮箱：渲染前做一次 PII 清洗（结构里本来就没有这两个字段）。
"""
from __future__ import annotations

import re

from ..schemas import ReportStructured

SECTION_TITLES = (
    "第 0 节：执行摘要",
    "第 1 节：公司背调",
    "第 2 节：岗位拆解",
    "第 3 节：人岗匹配（证据表）",
    "第 4 节：自我介绍",
    "第 5 节：针对性 HR 面试题",
    "第 6 节：背靠知识点",
    "第 7 节：应对方案",
    "第 8 节：数据来源与置信度 + 待核实清单",
)

DISCLAIMER = "本报告由 AI 生成，需人工核实证据；匹配结论不是通过率预测。"

PHONE_RE = re.compile(r"1[3-9]\d[\d\-\s]{7,11}")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
UNSAFE_FILENAME_RE = re.compile(r"[\\/:*?\"<>|\s]+")

TIER_LABEL = {"strong": "strong（有直接量化证据）", "discussable": "discussable（有相关证据，需补充说明）", "gap": "gap（无对应证据）"}
LEVEL_LABEL = {"must": "must（必须补）", "bonus": "bonus（加分）", "frequent": "frequent（面试高频）"}
REQUIRED_SECTIONS = SECTION_TITLES


def sanitize_filename_part(text: str) -> str:
    cleaned = UNSAFE_FILENAME_RE.sub("-", (text or "").strip())
    cleaned = re.sub(r"-{2,}", "-", cleaned).strip("-")
    return cleaned[:40] or "unknown"


def build_filename(report: ReportStructured) -> str:
    # 消歧失败（多个同名主体或查不到）时，用用户输入的名称命名，别把 "company" 丢给用户；
    # 但只有当 resolved.name 真的存在时才用全称，避免文件名冒充"已确认主体"。
    company = ""
    if report.company is not None:
        company = report.company.company_resolved.name or report.company.company_input or ""
    company = company or "待确认公司"
    role = ""
    if report.jd and report.jd.role_summary:
        role = report.jd.role_summary.split("。")[0].split(" / ")[0]
    elif report.resume_meta:
        role = report.resume_meta.parsing_mode
    return f"report-{sanitize_filename_part(company)}-{sanitize_filename_part(role)}-{report.analysis_id[:8]}.md"


def _scrub_pii(text: str) -> str:
    text = EMAIL_RE.sub("[邮箱已隐去]", text)
    return PHONE_RE.sub("[电话已隐去]", text)


def _kv_field(field) -> str:
    if field is None or field.value in (None, ""):
        source = field.source if field is not None else "not_fetched"
        return f"未获取（source: {source}）"
    return f"{field.value}"


def _section_1(report: ReportStructured) -> list[str]:
    lines = ["## 第 1 节：公司背调", ""]
    company = report.company
    if company is None:
        lines += ["未生成：本次分析未取得公司背调结果（原因见第 8 节待核实清单）。", ""]
        return lines

    resolved = company.company_resolved.name
    if not resolved:
        lines += [
            "**公司主体未唯一确定**：硬数据留空，以下内容仅为候选信息，不能当结论使用。",
            "",
            "候选主体：",
        ]
        for cand in company.company_resolved.disambiguation.candidates:
            lines.append(f"- {cand.name}（匹配理由：{cand.match_reason}）")
        lines.append("")
    else:
        lines += [f"公司全称：{resolved}（depth: {company.depth_used}，数据模式: {company.data_mode}）", ""]

    lines += ["### 硬数据（verified）", "", "| 字段 | 值 | 来源 |", "|---|---|---|"]
    labels = {
        "founded_at": "成立时间",
        "registered_capital": "注册资本",
        "legal_representative": "法定代表人",
        "business_scope": "经营范围",
        "registered_address": "注册地址",
        "status": "企业状态",
    }
    for key, label in labels.items():
        field = company.hard_data.fields().get(key)
        if field is None:
            continue
        verified = "verified" if field.verified else "unverified"
        lines.append(f"| {label} | {_kv_field(field)} | {field.source}（{verified}） |")
    lines.append("")

    soft = company.soft_profile
    lines += ["### 产品线矩阵", ""]
    if soft.products:
        for p in soft.products:
            lines.append(
                f"- {p.name}｜目标用户：{p.users or '未披露'}｜收入模式：{p.revenue_model or '未披露'}"
                f"｜与本岗位关系：{p.relation_to_role or '未说明'}｜来源：{', '.join(p.source_urls) or '未提供'}"
            )
    else:
        lines.append("- 公开渠道未检索到（不等于不存在，建议面试时直接问）")
    lines.append("")

    lines += ["### 动态（时间倒序）", ""]
    if soft.news:
        for n in soft.news:
            lines.append(f"- {n.date or '日期未标注'}｜{n.title}｜{n.url}")
    else:
        lines.append("- 新闻：公开渠道未检索到")
    if soft.financing:
        for f in soft.financing:
            lines.append(f"- 融资：{f.round or '轮次未披露'}｜{f.date or '日期未披露'}｜{f.amount or '金额未披露'}")
    else:
        lines.append("- 融资：公开渠道未检索到")
    if soft.hiring_signals:
        for s in soft.hiring_signals:
            lines.append(f"- 招聘信号：{s}")
    else:
        lines.append("- 招聘信号：公开渠道未检索到")
    lines.append("")

    lines += ["### 风险与关注点", ""]
    hard_labels = {
        "founded_at": "成立时间",
        "registered_capital": "注册资本",
        "legal_representative": "法定代表人",
        "business_scope": "经营范围",
        "registered_address": "注册地址",
        "status": "企业状态",
    }
    verified_bits = [
        f"{hard_labels.get(k, k)}={_kv_field(v)}"
        for k, v in company.hard_data.fields().items()
        if v.verified and v.value not in (None, "")
    ]
    lines.append("- 已验证：" + ("；".join(verified_bits) if verified_bits else "无可用的已验证数据"))
    inferred_items = company.degradations or []
    lines.append(
        "- 推断（inferred）："
        + (
            "；".join(inferred_items)
            if inferred_items
            else f"软信息整体为推断，需回到来源链接复核（共 {len(soft.source_urls)} 条来源）"
        )
    )
    unverified = [f"{hard_labels.get(k, k)}未获取" for k, v in company.hard_data.fields().items() if not v.verified]
    if company.data_mode == "mock":
        unverified.append("公司数据为 Mock 虚构样本，不可用于真实投递决策")
    if company.company_resolved.disambiguation.needs_user_confirm:
        unverified.append("公司主体未唯一确定，需人工确认工商全称")
    lines.append("- 待核实：" + ("；".join(unverified) if unverified else "无"))
    lines.append("")

    why = "推断：这家公司此时招这个岗位，通常与业务扩张或补编制有关"
    if soft.news:
        why += f"（公开动态：{soft.news[0].title}）"
    else:
        why += "（公开渠道未检索到近期动态，此判断为推断，需面试确认）"
    lines += [f"**为什么在这个时间招这个岗位**：{why}。", ""]
    return lines


def _section_2(report: ReportStructured) -> list[str]:
    lines = ["## 第 2 节：岗位拆解", ""]
    jd = report.jd
    if jd is None:
        lines += ["未生成：本次分析未取得 JD 拆解结果。", ""]
        return lines
    lines += [f"- 角色一句话：{jd.role_summary}", ""]
    lines.append("- 核心职责（带 jd ID）：")
    for r in jd.responsibilities:
        lines.append(f"  - {r.id}：{r.text}")
    lines.append("- must_have（带 jd ID）：")
    for m in jd.must_have:
        lines.append(f"  - {m.id}：{m.text}")
    lines.append("- nice_to_have（带 jd ID）：")
    for m in jd.nice_to_have or []:
        lines.append(f"  - {m.id}：{m.text}")
    if not jd.nice_to_have:
        lines.append("  - JD 未给出加分项")
    lines.append("")
    lines.append("- 隐性优先级（带证据句子 ID + inferred）：")
    for h in jd.hidden_priorities or []:
        lines.append(f"  - {h.text}（证据：{', '.join(h.evidence_sentence_ids) or '无'}；inferred）")
    if not jd.hidden_priorities:
        lines.append("  - 未识别到明确的隐性优先级")
    lines.append("- red_flags（带证据 + inferred）：")
    for r in jd.red_flags or []:
        lines.append(f"  - {r.text}（证据：{', '.join(r.evidence_sentence_ids) or '无'}；inferred）")
    if not jd.red_flags:
        lines.append("  - 未识别到明显风险信号")
    lines.append("")
    caps = [m.text for m in jd.must_have[:3]]
    lines.append("- 能力模型小结（这个岗位真正考的 3 项能力）：")
    for idx, cap in enumerate(caps, start=1):
        lines.append(f"  {idx}. {cap}")
    if not caps:
        lines.append("  - JD 未给出足够信息，无法归纳能力模型")
    lines.append("")
    return lines


def _section_3(report: ReportStructured) -> list[str]:
    lines = ["## 第 3 节：人岗匹配（证据表）", ""]
    lines.append("四维固定，只给档位不给百分比；每行必须同时有 jd ID 与 exp ID，缺一方写「无对应证据」。")
    lines.append("")
    lines.append("| 维度 | 档位 | JD 要求（jd ID） | 简历证据（exp ID） | 差距 | 可能追问 |")
    lines.append("|---|---|---|---|---|---|")
    for dim in report.match.dimensions:
        if not dim.rows:
            lines.append(f"| {dim.name} | {dim.tier} | 无 | 无对应证据 | {dim.note} | — |")
            continue
        for row in dim.rows:
            jd_ref = row.get("jd_ref", "")
            jd_text = (row.get("jd_text") or "")[:24]
            exp_ref = row.get("exp_ref", "无对应证据")
            gap = (row.get("gap") or "无")[:28]
            follow = (row.get("follow_up") or "—")[:30]
            lines.append(f"| {dim.name} | {dim.tier} | {jd_ref} {jd_text} | {exp_ref} | {gap} | {follow} |")
    lines.append("")
    for dim in report.match.dimensions:
        lines.append(f"- {dim.name}：{TIER_LABEL.get(dim.tier, dim.tier)}；{dim.note}")
    lines.append("")
    return lines


def _section_4(report: ReportStructured) -> list[str]:
    intro = report.self_intro
    lines = ["## 第 4 节：自我介绍", "", "### 30 秒版", "", intro.s30, "", "### 60 秒版", "", intro.s60, "",
             "### 120 秒版", "", intro.s120, "", "### 锚点清单（至少 3 条，带 exp ID）", ""]
    for anchor in intro.anchors:
        lines.append(f"- {anchor}")
    if intro.degraded:
        lines.append("")
        lines.append(f"> 注意：{intro.note}")
    lines.append("")
    return lines


def _section_5(report: ReportStructured) -> list[str]:
    lines = ["## 第 5 节：针对性 HR 面试题", "", f"共 {len(report.interview_questions)} 道（要求 ≥8）。", ""]
    if not report.interview_questions:
        lines += ["未生成：没有可用证据支撑面试题。", ""]
        return lines
    for q in report.interview_questions:
        lines += [
            f"### {q.id}｜{q.category}",
            "",
            f"- 问题：{q.question}",
            f"- 考察点：{q.focus}",
            f"- evidence_ref：{q.evidence_ref}（{q.evidence_status}）",
            "- STAR 回答骨架：",
            f"  - Situation：{q.star_answer.situation}",
            f"  - Task：{q.star_answer.task}",
            f"  - Action：{q.star_answer.action}",
            f"  - Result：{q.star_answer.result}",
            f"- 追问预判：{q.follow_up}",
            f"- 避坑点：{q.pitfall}",
            f"- knowledge_refs：{', '.join(q.knowledge_refs) or '无'}",
            "",
        ]
    return lines


def _section_6(report: ReportStructured) -> list[str]:
    lines = ["## 第 6 节：背靠知识点（按缺口分级）", ""]
    if not report.knowledge:
        lines += ["未生成：本岗位未识别出需要补的知识点。", ""]
        return lines
    for level in ("must", "bonus", "frequent"):
        group = [k for k in report.knowledge if k.level == level]
        if not group:
            continue
        lines += [f"### {LEVEL_LABEL[level]}", ""]
        for k in group:
            example = k.resume_example_ref or "通用知识、无简历例证"
            lines.append(f"- {k.id}｜{k.term}｜定义：{k.definition}｜简历例子：{example}｜可能追问：{k.likely_follow_up}")
        lines.append("")
    return lines


def _section_7(report: ReportStructured) -> list[str]:
    plan = report.action_plan
    lines = ["## 第 7 节：应对方案", ""]
    groups = [
        ("投递前（改简历，具体到 bullet 级）", plan.before_apply),
        ("面试前（补知识顺序 must → bonus → frequent）", plan.before_interview),
        ("面试中（薄弱项防守话术：承认缺口 + 已有相关经验 + 补齐计划）", plan.in_interview_defense),
        ("反问 HR 的 3 个问题", plan.questions_to_ask),
        ("面试后跟进清单", plan.after_interview),
    ]
    for title, items in groups:
        lines += [f"### {title}", ""]
        for item in items:
            lines.append(f"- {item}")
        if not items:
            lines.append("- 未生成")
        lines.append("")
    return lines


def _section_8(report: ReportStructured) -> list[str]:
    lines = ["## 第 8 节：数据来源与置信度 + 待核实清单", "", "### 来源表", "",
             "| 数据项 | 来源 | 置信度 | 抓取时间 |", "|---|---|---|---|"]
    for s in report.sources_and_confidence:
        lines.append(f"| {s.item} | {s.source} | {s.confidence} | {s.fetched_at or '未标注'} |")
    if not report.sources_and_confidence:
        lines.append("| 无 | 无 | unverified | - |")
    lines += ["", "### 待核实清单", ""]
    if report.to_verify:
        for item in report.to_verify:
            lines.append(f"- {item}")
    else:
        lines.append("- 无")
    if report.degradations:
        lines += ["", "### 降级与未生成说明", ""]
        for item in report.degradations:
            lines.append(f"- {item}")
    lines += ["", "### 免责", "", DISCLAIMER, ""]
    return lines


def render_report(report: ReportStructured) -> str:
    header = [
        "# 作战包报告",
        "",
        f"- 生成时间：{report.generated_at}",
        f"- 公司：{report.company.company_resolved.name if report.company and report.company.company_resolved.name else '待确认'}",
        f"- 简历版本：{report.resume_meta.resume_hash[:8] if report.resume_meta else '未知'}",
        f"- depth：{report.company.depth_used if report.company else 'basic'}",
        f"- 数据模式：{report.data_mode}",
        f"- analysis_id：{report.analysis_id}",
        "",
    ]
    body: list[str] = []
    verdict = report.verdict
    body += [
        "## 第 0 节：执行摘要",
        "",
        f"- 结论档位：{verdict.tier}",
        f"- 一句话 headline：{verdict.headline}",
        f"- 最大亮点（带证据 ID）：{verdict.top_strength}",
        f"- 最大缺口（带 JD ID）：{verdict.top_gap}",
        f"- 建议动作：{_recommended_action(report)}",
        "",
    ]
    body += _section_1(report)
    body += _section_2(report)
    body += _section_3(report)
    body += _section_4(report)
    body += _section_5(report)
    body += _section_6(report)
    body += _section_7(report)
    body += _section_8(report)
    return _scrub_pii("\n".join(header + body))


def _recommended_action(report: ReportStructured) -> str:
    tier = report.verdict.tier
    if tier == "strong":
        return "投：硬性条件与职责都有直接证据，重点准备经历深挖"
    if tier == "discussable":
        return "补齐后再投：先按第 7 节改 3 条 bullet，再准备最大缺口的防守话术"
    return "慎投：存在硬性缺口，建议先补经历或改投相近岗位"


def render_summary_card(report: ReportStructured, filename: str) -> dict:
    """DSH 摘要卡片：只含第 0 节 + 各节锚点 + 导出文件名（04 第 2 节）。"""
    anchors = [
        {"title": title, "anchor": "#" + title.replace(" ", "-")} for title in SECTION_TITLES
    ]
    return {
        "analysis_id": report.analysis_id,
        "verdict_tier": report.verdict.tier,
        "headline": report.verdict.headline,
        "top_strength": report.verdict.top_strength,
        "top_gap": report.verdict.top_gap,
        "recommended_action": _recommended_action(report),
        "company_name": report.company.company_resolved.name if report.company else None,
        "depth": report.company.depth_used if report.company else "basic",
        "parsing_mode": report.resume_meta.parsing_mode if report.resume_meta else None,
        "generated_at": report.generated_at,
        "report_filename": filename,
        "sections": anchors,
        "degradations": report.degradations,
        "data_mode": report.data_mode,
    }
