"""证据绑定生成：面试题、自我介绍、知识点，全部挂在证据 ID 上。

核心做法（06 第 1 节）：
- 生成时**只给已生成的 ID 列表**，不给模型自由编 ID 的机会；
- 生成后逐条走校验（ID 存在性 + 与证据的相关性），不合格重生成一次，仍不合格则降级标注；
- 所有数字、公司、岗位一律从结构化简历里**原文引用**，模板不产出任何新数字。
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from ..schemas import JdDecoded, ResumeStructured
from .matching import MatchResult, terms, threshold_verdict

ROLE_KNOWLEDGE = {
    "bd": ["商户分层运营", "GMV 拆解", "漏斗与转化", "商家生命周期", "竞品打法", "签约到上线的交付周期"],
    "数据分析": ["SQL 窗口函数", "AB 实验设计", "指标体系搭建", "归因分析", "留存曲线"],
    "产品": ["需求优先级", "PRD 结构", "用户访谈提纲", "Prompt 设计", "指标口径对齐"],
}

ROLE_TRIGGERS = {
    "bd": ("商务拓展", "商户", "签约", "渠道", "BD", "bd"),
    "数据分析": ("数据分析", "SQL", "sql", "指标", "报表", "AB 实验", "分析师"),
    "产品": ("产品经理", "需求文档", "PRD", "用户访谈", "Prompt", "产品方案"),
}

CATEGORY_ORDER = ("动机", "经历深挖", "岗位认知", "协作与稳定性")
# 相关性用"证据被题目覆盖的比例"（recall），不是"题目有多少词命中证据"：
# 后者会让"针对短要求的长问句"被判无关，反而把合法题目筛掉。
RELEVANCE_THRESHOLD = 0.15
MIN_QUESTIONS_OUTPUT = 8


@dataclass
class GenResult:
    self_intro: dict
    questions: list[dict]
    knowledge: list[dict]
    action_plan: dict
    to_verify: list[str] = field(default_factory=list)
    degradations: list[str] = field(default_factory=list)


def _short(text: str, limit: int = 40) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


LEADING_VERBS = ("具备较强的", "具备良好的", "具备", "熟练使用", "熟练", "掌握", "熟悉", "有较强的", "有")


def _term_from_jd(text: str) -> str:
    """把一条 JD 要求压缩成一个可背诵的知识点名词，而不是整句话。"""
    head = re.split(r"[，,；;。]", (text or "").strip())[0]
    for lead in LEADING_VERBS:
        if head.startswith(lead):
            head = head[len(lead):]
            break
    return _short(head.strip(), 14)


def _is_threshold(text: str) -> bool:
    """门槛类要求（学历/年限/届别）不是"知识点"，不该混进知识点清单。"""
    return bool(re.search(r"以上学历|年以上|届别|应届|专业不限", text or ""))


def _short_threshold_note(note: str) -> str:
    """把门槛判定说明压成一句人话，用于题面。

    直接把内部 note 原样塞进问句（含"需在面试中说明等价能力""按实习计"这类内部口径），
    题面读起来像系统日志，不像面试官会说的话。
    """
    note = note or ""
    months = re.search(r"累计\s*(\d+)\s*个月", note)
    if months:
        return f"简历累计约 {months.group(1)} 个月实习"
    degree = re.search(r"简历为([^，,）)]+)", note)
    if degree:
        return f"简历为{degree.group(1).strip()}"
    return note[:18]


def _relevant(question: str, evidence_text: str) -> float:
    """题目覆盖了多少证据内容（recall）。用于"这道题是否真的针对这条证据"。"""
    e_terms = terms(evidence_text)
    if not e_terms:
        return 0.0
    q_text = question or ""
    hits = sum(1 for t in e_terms if t in q_text)
    return hits / len(e_terms)


def _build_self_intro(resume: ResumeStructured, jd: JdDecoded, match: MatchResult) -> tuple[dict, list[str]]:
    to_verify: list[str] = []
    with_metrics = [e for e in resume.experiences if e.metrics]
    anchors = [e.id for e in with_metrics]
    if len(anchors) < 3:
        anchors += [p.id for p in resume.projects if p.metrics]
    degraded = False
    note = None
    if len(anchors) < 3:
        degraded = True
        note = "简历中可量化的成果不足 3 条，自我介绍已改为基于已有经历的通用表述，未补充任何新数字。"
        to_verify.append("自我介绍锚点不足 3 条：请补充可量化的经历或确认是否接受通用表述")
        anchors = anchors + [e.id for e in resume.experiences if e.id not in anchors][: 3 - len(anchors)]

    top = with_metrics[:2]
    role = resume.basic_info.title or (jd.role_summary.split("。")[0] if jd.role_summary else "目标岗位")

    def _pitch(exp_index: int, include_second: bool) -> str:
        if not top:
            return f"我是{role}方向的候选人，目前简历里可用的量化成果较少，下面只讲能够核实的部分。"
        first = top[0]
        sentence = f"我做过{first.role or '相关岗位'}，{_short(first.bullets[0] if first.bullets else '', 46)}"
        if include_second and len(top) > 1:
            second = top[1]
            sentence += f"；另一段是{second.company or '上一段实习'}，{_short(second.bullets[0] if second.bullets else '', 40)}"
        return sentence + "。"

    s30 = _pitch(0, False)
    s60 = _pitch(0, True) + f"我理解这个岗位最看重的是{_short(match.top_strength, 28)}，这正好是我做过的部分。"
    s120 = (
        _pitch(0, True)
        + f"教育背景方面，{resume.education[0].school if resume.education else '简历未提供'}，"
        + f"专业是{resume.education[0].major if resume.education and resume.education[0].major else '未提供'}。"
        + f"针对这个岗位，我的强项是{_short(match.top_strength, 34)}；需要补的是{_short(match.top_gap, 30)}，"
        + "我准备了具体的补齐计划，可以在面试里展开。"
    )
    return (
        {"30s": s30, "60s": s60, "120s": s120, "anchors": anchors[:4], "degraded": degraded, "note": note},
        to_verify,
    )


def _star_from_bullets(exp_bullets: list[str], exp_company: str, exp_role: str) -> dict:
    bullets = [b for b in exp_bullets if b]
    action = bullets[0] if bullets else "简历未给出具体动作"
    result = bullets[1] if len(bullets) > 1 else action
    return {
        "situation": f"在{exp_company or '该公司'}担任{exp_role or '该岗位'}期间",
        "task": f"需要完成的事项：{_short(action, 30)}",
        "action": _short(action, 60),
        "result": _short(result, 60),
    }


# 经历深挖的句式变体（v1 补缺口）：原来三条题目对任何简历都是同一套骨架，
# 换个人还是"最难的一步是什么 / 口径是什么 / 会先改哪一步"，长期一定会被候选人摸到规律。
# 现在按证据内容取变体：同一份简历三轮问法不同，不同简历之间也不会撞成同一串。
DIG_MAIN_VARIANTS = (
    {
        "question": "你在{company}做{role}时，{lead}。当时最难的一步是什么，你怎么解决的？",
        "follow_up": "如果重做一次，你会先改哪一步？当时这个目标是你自己定的还是上级给的？",
    },
    {
        "question": "{company}这段{role}，{lead}。这件事是你主导还是配合？具体哪几步是你自己做的？",
        "follow_up": "当时有没有别人也能做这一步？为什么最后是你来做？",
    },
    {
        "question": "简历里写{company}期间{lead}。如果只给你三分钟讲清这件事，你会按什么顺序讲？",
        "follow_up": "三分钟里你会先讲结果还是先讲过程？为什么这样排序？",
    },
)

DIG_METRIC_VARIANTS = (
    {
        "question": "{company}里，{lead}，这个结果是怎么衡量出来的？口径是什么？",
        "follow_up": "这个指标是你自己算的还是别人给的？样本多大？",
    },
    {
        "question": "{company}期间{lead}，这个数字的统计口径和样本范围是什么？谁认这个结果？",
        "follow_up": "口径中途改过吗？改了之后结论还成立吗？",
    },
    {
        "question": "关于{lead}，如果面试官当场追问数据怎么算的，你能拆出分子和分母吗？",
        "follow_up": "分子分母分别取自哪张表？取数时间点是什么时候？",
    },
)

DIG_REVIEW_VARIANTS = (
    {
        "question": "回看{company}，{lead}，如果再做一次，你会先改哪一步？为什么？",
        "follow_up": "当时有没有别的方法？为什么没选？",
    },
    {
        "question": "如果现在让你复盘{company}这段，{lead}，你觉得当时最该提前判断的是什么？",
        "follow_up": "这个判断当时有什么信号？你漏掉了哪个？",
    },
    {
        "question": "{company}这段里{lead}，假设预算和人力砍半，你会砍掉哪部分、保住哪部分？",
        "follow_up": "保留下来的那部分，你会用什么指标证明它值得保？",
    },
)


def _variant(variants: tuple[dict, ...], seed: str, offset: int = 0) -> dict:
    """按证据内容稳定取变体：同一份简历每次跑结果一致，不同简历不会永远撞同一条。

    用完整摘要取模，不要只取前 8 位：实测前 8 位在中文公司名这批样本上取模严重偏置
    （10 条里 9 条落在同一变体），变体会名存实亡。
    """
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()
    return variants[(int(digest, 16) + offset) % len(variants)]


def _dig_items(exp) -> list[dict]:
    """一条经历出三道深挖题：主成果 / 数据口径 / 复盘，各自带变体。"""
    company = exp.company or "这家公司"
    role = exp.role or "这个岗位"
    items: list[dict] = []

    main = _variant(DIG_MAIN_VARIANTS, f"{exp.id}|{company}|{role}|main")
    items.append(
        {
            "category": "经历深挖",
            "question": main["question"].format(company=company, role=role, lead=_short(exp.bullets[0], 40)),
            "focus": "验证动作细节与个人贡献，区分'参与'和'主导'",
            "evidence_ref": exp.id,
            "star_answer": _star_from_bullets(exp.bullets, company if exp.company else "", exp.role or ""),
            "follow_up": main["follow_up"],
            "pitfall": "不要把团队成果说成个人成果，面试官会追问具体分工和你的决策点。",
        }
    )
    if len(exp.bullets) > 1:
        metric = _variant(DIG_METRIC_VARIANTS, f"{exp.id}|{exp.bullets[1]}|metric")
        items.append(
            {
                "category": "经历深挖",
                "question": metric["question"].format(company=company, lead=_short(exp.bullets[1], 40)),
                "focus": "验证数据口径意识，防止数字是拍脑袋的",
                "evidence_ref": exp.id,
                "star_answer": _star_from_bullets(exp.bullets[1:], company if exp.company else "", exp.role or ""),
                "follow_up": metric["follow_up"],
                "pitfall": "说不清口径会被判定为包装数据，宁可说'这部分是团队口径，我负责其中 X 环节'。",
            }
        )
    review = _variant(DIG_REVIEW_VARIANTS, f"{exp.id}|{exp.bullets[-1]}|review")
    items.append(
        {
            "category": "经历深挖",
            "question": review["question"].format(company=company, lead=_short(exp.bullets[-1], 36)),
            "focus": "复盘能力与自我认知，看是否真做过",
            "evidence_ref": exp.id,
            "star_answer": _star_from_bullets(list(reversed(exp.bullets)), company if exp.company else "", exp.role or ""),
            "follow_up": review["follow_up"],
            "pitfall": "不要只说'会更细心'，要给具体的判断依据和改法。",
        }
    )
    return items


def _question_pool(
    resume: ResumeStructured, jd: JdDecoded, match: MatchResult
) -> list[dict]:
    """先造一个候选池，再按校验结果挑选，保证最终 ≥8 道且全部有真实 evidence_ref。"""
    pool: list[dict] = []
    exp_by_id = {e.id: e for e in resume.experiences}
    proj_by_id = {p.id: p for p in resume.projects}
    jd_by_id = {i.id: i.text for i in jd.must_have + jd.nice_to_have}
    jd_by_id.update({i.id: i.text for i in jd.responsibilities})

    ordered_exps = sorted(resume.experiences, key=lambda e: len(e.metrics), reverse=True)

    # 经历深挖：每条经历出 1-3 题，题面必须引用该经历的具体事实；句式按证据取变体
    for exp in ordered_exps:
        if not exp.bullets:
            continue
        pool.extend(_dig_items(exp))

    # 动机：结合岗位与最相关经历
    if ordered_exps:
        exp = ordered_exps[0]
        pool.append(
            {
                "category": "动机",
                "question": f"你之前在{exp.company or '上一段实习'}做{exp.role or '相关岗位'}，"
                f"为什么现在想做{_short(jd.role_summary.split('。')[0], 24)}？",
                "focus": "动机是否与岗位真实内容一致，而不是泛泛说'想挑战自己'",
                "evidence_ref": exp.id,
                "star_answer": _star_from_bullets(exp.bullets, exp.company or "", exp.role or ""),
                "follow_up": "如果这个岗位前三个月主要是跑商户、做基础执行，你还能接受吗？",
                "pitfall": "不要说'想学东西'，要说清你已有的能力在这个岗位上能换来什么结果。",
            }
        )

    # 门槛类要求（学历/年限）必须按事实分两种问法：
    #   已满足 -> 不出"请回应质疑"的伪问题（简历明明达标，问了反而显得没读简历）；
    #   不满足 -> 出差距回应题，追问方向按学历/年限分开，不许张冠李戴。
    for item in jd.must_have:
        if _is_threshold(item.text):
            verdict = threshold_verdict(item.text, resume)
            tier, note = verdict if verdict is not None else ("discussable", "")
            if tier == "strong":
                pool.insert(
                    0,
                    {
                        "category": "动机",
                        "question": f"JD 要求「{_short(item.text, 34)}」，这一条你已经满足（{_short_threshold_note(note)}）；"
                        "入职后你打算用哪个具体结果证明自己对这条要求不只是达标？",
                        "focus": "门槛达标之后如何建立可信度，而不是复述条件",
                        "evidence_ref": item.id,
                        "star_answer": {
                            "situation": f"门槛条件已满足：{_short_threshold_note(note)}",
                            "task": "把「达标」变成「可验证的产出」",
                            "action": "挑一段最相关的经历（见简历 exp 编号），说清可迁移的动作",
                            "result": "给出入职 30/60 天内可检查的小目标",
                        },
                        "follow_up": "同批候选人里有人经验比你多，你打算靠什么建立自己的可信度？",
                        "pitfall": "不要停在「我符合要求」，面试官要听你凭什么做得比同批人好。",
                    },
                )
            else:
                is_years = "年限" in note
                follow = (
                    "如果我们这轮只招满足年限要求的人，你觉得你还差什么、打算怎么补？"
                    if is_years
                    else "同批候选人里有人学历更匹配，你希望我们看重你哪一点？"
                )
                pool.insert(
                    0,
                    {
                        "category": "动机",
                        "question": f"JD 要求「{_short(item.text, 34)}」，按简历事实你目前不满足（{_short_threshold_note(note)}），"
                        "你会怎么回应面试官的质疑？",
                        "focus": "面对硬门槛时的诚实度与说服逻辑，不许否认事实",
                        "evidence_ref": item.id,
                        "star_answer": {
                            "situation": f"JD 写明「{_short(item.text, 24)}」，简历事实：{_short_threshold_note(note)}",
                            "task": "承认差距，同时用已有经历证明等价能力",
                            "action": "不否认门槛 → 举一段最接近的经历（见简历 exp 编号）→ 说明上手速度",
                            "result": "给出可验证的短期承诺，例如入职 4 周内独立完成一次完整交付",
                        },
                        "follow_up": follow,
                        "pitfall": "不要说'我学习能力强'这种空话，也不要把实习包装成正式工作年限。",
                    },
                )
        else:
            # 能力类要求也要先看简历：已有对应证据时问"怎么讲成这条能力"，
            # 没有证据才问"你理解这条要求在实际工作里是什么样"。一律问同一句式等于没读简历。
            matched = next((m for m in match.item_matches if m.jd_id == item.id), None)
            covered_exp = matched.best_exp_id if matched else None
            if covered_exp:
                exp = exp_by_id.get(covered_exp) or proj_by_id.get(covered_exp)
                lead = exp.bullets[0] if exp is not None and exp.bullets else ""
                pool.append(
                    {
                        "category": "岗位认知",
                        "question": f"JD 要求「{_short(item.text, 36)}」，你简历里的「{_short(lead, 26)}」"
                        "其实能对上；面试时你会从哪一步讲起，让对方相信这不是套话？",
                        "focus": "把已有证据映射成岗位能力，而不是复述简历原句",
                        "evidence_ref": covered_exp,
                        "star_answer": {
                            "situation": f"JD 要求：{_short(item.text, 28)}",
                            "task": "用一段做过的事证明这条能力",
                            "action": "先点明对应关系 → 再讲具体动作 → 最后落到可核对的结果",
                            "result": "结果只用简历里已有的数字，不新增",
                        },
                        "follow_up": "如果对方追问这条能力里最弱的一环，你会承认哪一点？",
                        "pitfall": "不要背方法论，也不要为了贴要求把别人的活说成自己的。",
                    }
                )
            else:
                pool.append(
                    {
                        "category": "岗位认知",
                        "question": f"JD 里写到「{_short(item.text, 40)}」，你理解这个要求在实际工作里具体是什么样？",
                        "focus": "是否真的读懂岗位，而不是背 JD",
                        "evidence_ref": item.id,
                        "star_answer": {
                            "situation": "结合 JD 要求与自己做过的相近工作",
                            "task": f"说明「{_short(item.text, 26)}」在实际场景中的做法",
                            "action": "给出一个自己经历过的具体场景，说明判断标准与推进方式",
                            "result": "落到可衡量的结果上，没有相关结果就说明会怎么补",
                        },
                        "follow_up": "如果让你用一件具体的交付物证明这一点，你会拿什么？",
                        "pitfall": "不要空谈方法论，面试官要听你做过什么、怎么判断优先级。",
                    }
                )

    for item in jd.nice_to_have[:1]:
        # 加分项也要先看简历：已经有对应证据时，问"你有没有替代"等于没读简历。
        matched = next((m for m in match.item_matches if m.jd_id == item.id), None)
        covered_exp = matched.best_exp_id if matched else None
        if covered_exp:
            exp = exp_by_id.get(covered_exp) or proj_by_id.get(covered_exp)
            lead = exp.bullets[0] if exp is not None and exp.bullets else ""
            pool.append(
                {
                    "category": "岗位认知",
                    "question": f"JD 把「{_short(item.text, 36)}」列为加分项，你简历里的"
                    f"「{_short(lead, 26)}」其实能对上；面试时你会怎么把它讲成这块加分项的对应案例？",
                    "focus": "把已有经历映射到加分项，而不是重复简历原句",
                    "evidence_ref": covered_exp,
                    "star_answer": {
                        "situation": f"加分项要求：{_short(item.text, 28)}",
                        "task": "把已经做过的事讲成对方听得懂的价值",
                        "action": "先复述要求 → 再给一段具体动作 → 最后落到可核对的结果",
                        "result": "结果用简历里已有的数字，不要新增",
                    },
                    "follow_up": "这段经历和加分项之间还差什么，你打算怎么补？",
                    "pitfall": "不要为了贴加分项硬编经历，面试官会顺着细节问下去。",
                }
            )
            continue
        pool.append(
            {
                "category": "岗位认知",
                "question": f"JD 里把「{_short(item.text, 36)}」列为加分项，你有没有相近的经历可以替代？",
                "focus": "加分项缺口的替代论证能力",
                "evidence_ref": item.id,
                "star_answer": {
                    "situation": "加分项不是硬性要求，但要能给出替代证据",
                    "task": "说明自己缺什么、有什么相近的",
                    "action": "举一段结构相似的经历，说清可迁移的部分",
                    "result": "给出补齐时间表，不夸大已有经验",
                },
                "follow_up": "如果没有这块经历，你打算在上岗后多长时间内补齐，用什么证明补上了？",
                "pitfall": "不要声称自己有实际上没有的资源，面试官一问名单就露馅。",
            }
        )

    # 协作与稳定性：优先引用协同/维护类职责；JD 没写这类词时，用第一条职责做"跨部门配合"追问，
    # 否则这一类会整类缺失（四类覆盖是硬要求）
    collab = [i for i in jd.responsibilities if any(k in i.text for k in ("协同", "维护", "配合", "推进", "推动"))]
    # 同一套"合作方不配合怎么推进"的问法最多出一道：换一条 JD 职责再问一遍，本质是灌水题。
    for item in (collab or jd.responsibilities[:1])[:1]:
        pool.append(
            {
                "category": "协作与稳定性",
                "question": f"岗位职责里提到「{_short(item.text, 36)}」，如果合作方不配合，你会怎么推进？",
                "focus": "跨团队协作方式与情绪稳定性",
                "evidence_ref": item.id,
                "star_answer": {
                    "situation": "描述一次真实的跨团队协作场景（来自简历经历）",
                    "task": "说明你需要在什么约束下推动对方",
                    "action": "说清你用了什么抓手：目标对齐、数据说服、还是升级机制",
                    "result": "给出最终推进结果，失败的经历也可以讲，但要讲清复盘",
                },
                "follow_up": "有没有推不动的时候？那次你最后怎么处理的？",
                "pitfall": "不要把所有冲突都归因于对方，面试官在看你自己的复盘能力。",
            }
        )

    # 保底：用简历里剩下的经历/项目补足
    for proj in resume.projects:
        if not proj.bullets:
            continue
        pool.append(
            {
                "category": "经历深挖",
                "question": f"你做的{proj.name or '这个项目'}，{_short(proj.bullets[0], 36)}，"
                "这个项目里你具体负责哪一块？",
                "focus": "项目真实性与个人贡献边界",
                "evidence_ref": proj.id,
                "star_answer": _star_from_bullets(proj.bullets, "项目", proj.name or ""),
                "follow_up": "这个项目上线了吗？有多少人真的在用？",
                "pitfall": "项目没上线就说没上线，硬说上线会被追问细节问穿。",
            }
        )

    for item in jd.responsibilities:
        pool.append(
            {
                "category": "岗位认知",
                "question": f"如果让你接手「{_short(item.text, 34)}」，你前两周会怎么安排？",
                "focus": "岗位理解与落地能力",
                "evidence_ref": item.id,
                "star_answer": {
                    "situation": "假设已入职，面对这条职责",
                    "task": "拆出前两周的可交付动作",
                    "action": "先摸清现状（数据/商户/协作方），再定一个小目标验证",
                    "result": "给出一个可检查的短期结果",
                },
                "follow_up": "这两周你怎么判断自己做得对不对？",
                "pitfall": "不要给空泛的'先熟悉业务'，要说清熟悉哪些、怎么验证。",
            }
        )
    return pool


def _select_questions(pool: list[dict], resume: ResumeStructured, jd: JdDecoded) -> tuple[list[dict], list[str]]:
    valid_ids = resume.evidence_ids() | jd.all_ids()
    text_by_id: dict[str, str] = {}
    for exp in resume.experiences:
        text_by_id[exp.id] = f"{exp.company or ''} {exp.role or ''} {' '.join(exp.bullets)}"
    for proj in resume.projects:
        text_by_id[proj.id] = f"{proj.name or ''} {' '.join(proj.bullets)}"
    for item in jd.must_have + jd.nice_to_have + jd.responsibilities:
        text_by_id[item.id] = item.text

    # 第一道关：ID 必须真实存在，且题面与该证据有实际词面联系（防止"通用题套 ID"）
    candidates = [
        q
        for q in pool
        if q.get("evidence_ref") in valid_ids
        and _relevant(q["question"], text_by_id.get(q["evidence_ref"], "")) >= RELEVANCE_THRESHOLD
    ]

    used_refs: dict[str, int] = {}
    chosen: list[dict] = []

    def take(q: dict) -> bool:
        ref = q["evidence_ref"]
        # 单条证据最多出 4 道题：JD 很薄时，深挖唯一的真实经历比编通用题更诚实
        if used_refs.get(ref, 0) >= 4:
            return False
        used_refs[ref] = used_refs.get(ref, 0) + 1
        chosen.append(q)
        return True

    # 四类各保底 1 题，避免某一类被高频类挤掉（动机题最容易掉）
    for cat in CATEGORY_ORDER:
        for q in candidates:
            if q["category"] == cat and q not in chosen:
                if take(q):
                    break

    # 轮转补齐到 10 题
    remaining = [q for q in candidates if q not in chosen]
    while len(chosen) < 10 and remaining:
        progressed = False
        for cat in CATEGORY_ORDER:
            for q in list(remaining):
                if q["category"] == cat and take(q):
                    remaining.remove(q)
                    progressed = True
                    break
            if len(chosen) >= 10:
                break
        if not progressed:
            break

    # 输出顺序固定：动机 -> 经历深挖 -> 岗位认知 -> 协作与稳定性，每类最多 3 题
    result: list[dict] = []
    for cat in CATEGORY_ORDER:
        result.extend([q for q in chosen if q["category"] == cat][:3])

    # 某一类证据太少时会出现"总数不足 8"：把已经通过校验的候选题补进来，
    # 宁可同一类多一两道，也不许为了凑数编通用题
    if len(result) < MIN_QUESTIONS_OUTPUT:
        for q in chosen:
            if q not in result:
                result.append(q)
            if len(result) >= MIN_QUESTIONS_OUTPUT:
                break

    degradations: list[str] = []
    if len(result) < MIN_QUESTIONS_OUTPUT:
        degradations.append(
            f"可用证据只能支撑 {len(result)} 道题（要求 ≥8），已按实际证据输出，未编造题目"
        )
    for idx, q in enumerate(result, start=1):
        q["id"] = f"q_{idx:02d}"
    return result, degradations


def _knowledge(resume: ResumeStructured, jd: JdDecoded, match: MatchResult) -> list[dict]:
    items: list[dict] = []
    counter = 0
    haystack = " ".join(
        [" ".join(e.bullets) for e in resume.experiences]
        + [" ".join(p.bullets) for p in resume.projects]
        + resume.skills
    )
    example_for: dict[str, str] = {}
    for exp in resume.experiences + resume.projects:
        blob = " ".join(exp.bullets)
        example_for[exp.id] = blob

    def _guess_ref(term: str) -> str | None:
        for ref, blob in example_for.items():
            if _relevant(term, blob) >= 0.2:
                return ref
        return None

    must_ids = {i.id for i in jd.must_have}
    nice_ids = {i.id for i in jd.nice_to_have}
    # 门槛类要求（学历/年限）不是知识点，归到"差距回应"题里，避免知识点清单注水
    gap_must = [
        m
        for m in match.item_matches
        if m.tier == "gap" and m.jd_id in must_ids and not _is_threshold(m.jd_text)
    ]
    for m in gap_must[:4]:
        counter += 1
        ref = _guess_ref(m.jd_text)
        definition = f"JD 明确要求：{m.jd_text}。你需要能说清具体做法、衡量口径和自己的例子。"
        if ref is None:
            definition += "通用知识、无简历例证，回答时不要假装来自简历。"
        items.append(
            {
                "id": f"k_{counter:02d}",
                "level": "must",
                "term": _term_from_jd(m.jd_text),
                "definition": definition,
                "resume_example_ref": ref,
                "likely_follow_up": m.follow_up,
            }
        )
    for m in [x for x in match.item_matches if x.jd_id in nice_ids][:3]:
        counter += 1
        ref = _guess_ref(m.jd_text)
        definition = f"加分项：{m.jd_text}。有则强化，没有则准备「如何快速补」的说法。"
        if ref is None:
            definition += "通用知识、无简历例证，回答时不要假装来自简历。"
        items.append(
            {
                "id": f"k_{counter:02d}",
                "level": "bonus",
                "term": _term_from_jd(m.jd_text),
                "definition": definition,
                "resume_example_ref": ref,
                "likely_follow_up": m.follow_up,
            }
        )

    blob = f"{jd.role_summary} {' '.join(i.text for i in jd.must_have)} {' '.join(i.text for i in jd.responsibilities)}"
    # 只选一个角色词表：按触发词命中数取最高，避免"数据分析"混进产品岗
    best_key, best_hits = None, 0
    for key, triggers in ROLE_TRIGGERS.items():
        hits = sum(blob.count(t) for t in triggers)
        if hits > best_hits:
            best_key, best_hits = key, hits
    picked: list[str] = ROLE_KNOWLEDGE.get(best_key, [])[:4] if best_key else []
    for term in picked:
        counter += 1
        ref = _guess_ref(term)
        definition = (
            f"{term}：面试高频概念，需要能用自己的话解释并给出场景。"
            if ref
            else f"{term}：面试高频概念。通用知识、无简历例证，回答时不要假装来自简历。"
        )
        items.append(
            {
                "id": f"k_{counter:02d}",
                "level": "frequent",
                "term": term,
                "definition": definition,
                "resume_example_ref": ref,
                "likely_follow_up": f"如果让你在我们业务里用一次{term}，你会从哪一步开始？",
            }
        )
    return items


def _action_plan(
    resume: ResumeStructured, jd: JdDecoded, match: MatchResult, company: dict | None
) -> dict:
    gap_rows = [r for d in match.dimensions for r in d.get("rows", []) if r.get("tier") in ("gap", "discussable")]
    exp_line = resume.experiences[0] if resume.experiences else None
    before_apply: list[str] = []
    for row in gap_rows[:3]:
        if row["exp_ref"] != "无对应证据":
            before_apply.append(
                f"在 {row['exp_ref']} 的 bullet 里补上可核对的量化结果（周期、样本量、口径），对应 {row['jd_ref']}：{_short(row['jd_text'], 24)}"
            )
        else:
            before_apply.append(
                f"{row['jd_ref']}「{_short(row['jd_text'], 22)}」在简历里没有对应证据，投递前想清楚替代说法，不要硬编经历"
            )
    if exp_line and exp_line.bullets:
        before_apply.append(
            f"把 {exp_line.id} 第一条 bullet 从「{_short(exp_line.bullets[0], 26)}」改成「动作 + 对象 + 结果」三段式，保留原有数字"
        )
    if len(before_apply) < 3:
        before_apply.append("把简历里的技能清单按 JD 顺序重排，删掉与本岗位无关的条目，避免稀释重点")

    must_terms = [k["term"] for k in []]
    before_interview = [
        "按 must → bonus → frequent 的顺序补：先补 JD 硬性缺口，再看加分项，最后扫高频题",
        f"针对最大缺口准备三段式回答：承认缺口（{_short(match.top_gap, 28)}）+ 已有相近经验 + 补齐计划",
        "把自我介绍 30s 版背到能自然说出，60s 版留作追问时展开",
    ]

    company_name = (company or {}).get("resolved_name") or "这家公司"
    news = (company or {}).get("news") or []
    questions_to_ask = [
        f"这个岗位未来 6 个月的考核指标具体是哪几个？权重怎么分？（针对 {company_name}）",
        f"团队现在最大的增长卡点在哪：商户数量、还是单店产出？（结合公开信息：{_short(news[0]['title'], 24) if news else '公开渠道未检索到近期动态'}）",
        "我入职后前三个月，你希望我先交付哪一件具体的事？",
    ]

    defense: list[str] = []
    for d in match.dimensions:
        if d["tier"] == "gap":
            defense.append(
                f"{d['name']}是明显缺口：先承认（不否认事实），再讲已有相近经验（{'、'.join(d['evidence_refs'][:2]) or '无'}），最后给出 4 周补齐计划"
            )
    if not defense:
        defense.append("没有硬性缺口，重点防止把'熟悉'说成'精通'，回答时给出边界")

    return {
        "before_apply": before_apply[:5],
        "before_interview": before_interview,
        "in_interview_defense": defense,
        "questions_to_ask": questions_to_ask,
        "after_interview": [
            "24 小时内发感谢邮件，补一条面试中没讲清的证据",
            "把面试官追问的问题记下来，更新到知识清单",
            "5 个工作日后无反馈再跟进一次，不重复投递",
        ],
    }


def generate(
    resume: ResumeStructured,
    jd: JdDecoded,
    match: MatchResult,
    company_ctx: dict | None = None,
) -> GenResult:
    to_verify: list[str] = []
    degradations: list[str] = []

    self_intro, intro_verify = _build_self_intro(resume, jd, match)
    to_verify.extend(intro_verify)

    pool = _question_pool(resume, jd, match)
    questions, q_degradations = _select_questions(pool, resume, jd)
    degradations.extend(q_degradations)

    knowledge = _knowledge(resume, jd, match)
    if not knowledge:
        degradations.append("知识点清单为空：JD 要求过少或全部已有证据覆盖")

    plan = _action_plan(resume, jd, match, company_ctx)

    if resume.parsing_mode == "fallback":
        to_verify.append("简历使用 fallback 解析（未启用 SmartResume），字段准确性需人工复核")
    for note in resume.parsing_notes:
        if "待核实" in note or "未识别" in note or "OCR" in note:
            to_verify.append(f"解析提示：{note}")

    return GenResult(
        self_intro=self_intro,
        questions=questions,
        knowledge=knowledge,
        action_plan=plan,
        to_verify=to_verify,
        degradations=degradations,
    )
