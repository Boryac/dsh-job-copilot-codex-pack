"""人岗匹配基线（Lane D，T3.3）。

设计立场（06 第 3 节）：
- 关键词重合度**只做硬性条件维度的基线**，不许直接当通过率；
- 最终档位 = 基线 + 语义近似 + 证据强度 三者共同决定；
- 输出档位，不输出百分比总分。`score` 字段只用于内部排序与测试，不写进报告正文。

语义近似用领域词表实现（deterministic），不是向量模型：mock 模式下必须可复现，
live 模式可替换为 LLM 判定而不改上层契约（`semantic_mode` 字段标注用了哪种）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..schemas import JdDecoded, ResumeStructured, Tier

FUNCTION_WORDS = (
    "以上", "相关", "优先", "具备", "较强", "良好", "能力", "经验", "负责", "进行",
    "能够", "熟悉", "掌握", "了解", "使用", "熟练", "独立", "完成", "以及", "或者",
    "我们", "希望", "要求", "工作", "岗位", "职位", "公司", "团队", "一定",
    # 单字虚词：不切开会把"商户的拓展"粘成一个长串，bigram 里全是噪声
    "的", "与", "或", "及", "和", "对", "为", "以", "并", "等", "把", "被", "在",
)

# bigram 里带这些字的组合基本是切分噪声（"地生"、"户的"），直接丢掉，避免稀释覆盖率
NOISE_CHARS = set("的与或及和为以后者把被在")

# 同义/近义扩展：只做"同一个事实的不同说法"，不做无依据的联想
SYNONYMS: dict[str, tuple[str, ...]] = {
    "商务拓展": ("bd", "拓展", "渠道", "签约"),
    "bd": ("商务拓展", "拓展"),
    "拓展": ("商务拓展", "签约", "渠道"),
    "签约": ("拓展", "商户", "供应商"),
    "商户": ("商家", "供应商", "客户"),
    "商家": ("商户", "供应商"),
    "供应商": ("商户", "商家", "酒店"),
    "酒旅": ("酒店", "ota", "旅行"),
    "餐饮": ("商户", "门店"),
    "数据分析": ("数据", "分析", "sql", "报表"),
    "数据": ("分析", "报表", "看板"),
    "excel": ("表格", "数据透视"),
    "sql": ("数据库", "查询"),
    "沟通": ("对接", "协调", "沟通"),
    "谈判": ("签约", "谈"),
    "抗压": ("目标", "考核"),
    "留存": ("复购", "活跃"),
    "复购": ("留存", "复签"),
    "增长": ("提升", "拉新", "gmv"),
    "实验": ("ab", "测试"),
    "大模型": ("llm", "prompt", "ai"),
    "prompt": ("提示词", "大模型"),
    "需求文档": ("prd", "需求"),
    "用户访谈": ("访谈", "调研"),
}

RELATED_GROUPS = [
    {"商户", "商家", "供应商", "客户", "门店"},
    {"签约", "拓展", "拉新", "渠道", "开发"},
    {"酒店", "酒旅", "ota", "旅行"},
    {"数据", "报表", "看板", "分析", "指标"},
    {"留存", "复购", "活跃", "粘性"},
    {"增长", "提升", "gmv", "roi", "转化"},
    {"沟通", "协调", "对接", "协作"},
    {"文档", "prd", "需求", "方案"},
]

CJK_RE = re.compile(r"[\u4e00-\u9fa5]+")
TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9+#.\-]*|\d+(?:\.\d+)?%?")

# 管理/带队类要求：字面能重合（"搭建……团队" vs "搭建留存看板"），事实层级却完全不同。
# 实习生做执行，不能被判成"具备团队管理证据"——那是把关键词重合当事实（06 第 3 节）。
LEADERSHIP_REQ_RE = re.compile(
    r"管理\s*\d*\s*人|团队管理|带领|带队|管理者|管理层|搭建.{0,8}团队|招聘.{0,6}培养"
)
LEADERSHIP_EVIDENCE_RE = re.compile(r"管理|带领|带队|组长|负责人|牵头|主导|招聘|绩效|主管")


def leadership_level_mismatch(jd_text: str, evidence_text: str) -> bool:
    """JD 要管理/带队，而证据里只有执行动作时返回 True。"""
    if not LEADERSHIP_REQ_RE.search(jd_text or ""):
        return False
    return not LEADERSHIP_EVIDENCE_RE.search(evidence_text or "")



def _split_terms(text: str) -> list[str]:
    text = text or ""
    terms: list[str] = []
    for run in CJK_RE.findall(text):
        segment = run
        for fw in FUNCTION_WORDS:
            segment = segment.replace(fw, "|")
        for part in segment.split("|"):
            part = part.strip().strip("的与或及和为以后者把被在")
            if len(part) < 2:
                continue
            if len(part) <= 4:
                terms.append(part)
            else:
                for i in range(len(part) - 1):
                    bigram = part[i : i + 2]
                    if NOISE_CHARS & set(bigram):
                        continue
                    terms.append(bigram)
                # 长串里也保留 2-3 字的核心片段（"本地生活" 这类固定搭配）
                if len(part) <= 6:
                    terms.append(part)
    for token in TOKEN_RE.findall(text):
        terms.append(token.lower())
    return terms


def terms(text: str) -> set[str]:
    return set(_split_terms(text))


def _resume_text(resume: ResumeStructured) -> str:
    parts: list[str] = []
    for exp in resume.experiences:
        parts.extend([exp.company or "", exp.role or "", " ".join(exp.bullets)])
    for proj in resume.projects:
        parts.extend([proj.name or "", " ".join(proj.bullets)])
    parts.extend(resume.skills)
    for edu in resume.education:
        parts.extend([edu.school or "", edu.major or "", edu.degree or ""])
    for item in resume.experiences + resume.projects:
        for m in item.metrics:
            parts.append(m.context)
    return " ".join(parts)


def _hit(term: str, haystack: str) -> bool:
    if not term:
        return False
    if term in haystack:
        return True
    for syn in SYNONYMS.get(term, ()):
        if syn and syn in haystack:
            return True
    return False


def keyword_coverage(jd_text: str, haystack: str) -> float:
    """关键词覆盖率：JD 术语在简历里命中的比例。纯代码、确定性。"""
    jd_terms = terms(jd_text)
    if not jd_terms:
        return 0.0
    hits = sum(1 for t in jd_terms if _hit(t, haystack))
    return round(hits / len(jd_terms), 4)


def semantic_overlap(jd_text: str, haystack: str) -> float:
    """领域词表近似：JD 里的概念在简历里是否有同组词覆盖。"""
    jd_terms = terms(jd_text)
    if not jd_terms:
        return 0.0
    covered = 0
    for group in RELATED_GROUPS:
        jd_hit = {t for t in jd_terms if any(g in t or t in g for g in group)}
        if not jd_hit:
            continue
        if any(g in haystack for g in group):
            covered += 1
    total_groups = sum(
        1 for group in RELATED_GROUPS if any(any(g in t or t in g for g in group) for t in jd_terms)
    )
    return round(covered / total_groups, 4) if total_groups else 0.0


DEGREE_RANK = {"博士": 5, "硕士": 4, "本科": 3, "学士": 3, "大专": 2, "专科": 2, "中专": 1, "高中": 1}
YEARS_RE = re.compile(r"(\d+)\s*年以上")
PERIOD_RE = re.compile(
    r"(\d{4})\s*[.\-/年]?\s*(\d{1,2})?\s*[-–—~至]\s*(?:(\d{4})\s*[.\-/年]?\s*(\d{1,2})?|至今|现在)"
)


def _months_from_period(period: str) -> int:
    m = PERIOD_RE.search(period or "")
    if not m:
        return 0
    y1, m1 = int(m.group(1)), int(m.group(2) or 1)
    if m.group(3):
        y2, m2 = int(m.group(3)), int(m.group(4) or 12)
    else:  # 至今
        y2, m2 = 2026, 11
    return max(0, (y2 - y1) * 12 + (m2 - m1))


def _resume_degree_rank(resume: ResumeStructured) -> tuple[int, str]:
    best_rank, label = 0, "未识别"
    for edu in resume.education:
        text = f"{edu.degree or ''} {edu.major or ''}"
        for word, rank in DEGREE_RANK.items():
            if word in text and rank > best_rank:
                best_rank, label = rank, word
    return best_rank, label


def threshold_verdict(text: str, resume: ResumeStructured) -> tuple[Tier, str] | None:
    """学历 / 年限这类门槛要求必须按简历事实判定，不能靠关键词重合度混成 strong。

    为什么单独处理：把"1 年以上经验"判成强项，等于用关键词相似度冒充事实，
    06 第 3 节明确禁止"把关键词重合度直接等同于通过率"。
    """
    degree_req = next((w for w in ("博士", "硕士", "本科", "大专", "专科") if w in text), None)
    if degree_req and ("学历" in text or "本科" in text):
        need = DEGREE_RANK[degree_req]
        have_rank, have_label = _resume_degree_rank(resume)
        if have_rank >= need:
            return "strong", f"学历门槛满足：JD 要求{degree_req}及以上，简历为{have_label}"
        return "gap", f"学历门槛不满足：JD 要求{degree_req}及以上，简历为{have_label}"

    years = YEARS_RE.search(text)
    if years:
        need_months = int(years.group(1)) * 12
        total = sum(_months_from_period(e.period or "") for e in resume.experiences)
        if total >= need_months:
            return "strong", f"年限门槛满足：累计 {total} 个月相关经历，JD 要求 {years.group(1)} 年"
        return (
            "gap",
            f"年限门槛不满足：简历累计 {total} 个月（按实习计），JD 要求 {years.group(1)} 年，需在面试中说明等价能力",
        )
    return None


@dataclass
class ItemMatch:
    jd_id: str
    jd_text: str
    best_exp_id: str | None = None
    coverage: float = 0.0
    semantic: float = 0.0
    evidence_strength: float = 0.0
    score: float = 0.0
    tier: Tier = "gap"
    gap_note: str = ""
    follow_up: str = ""


def _experience_blob(exp) -> str:
    return " ".join(
        [
            getattr(exp, "company", "") or getattr(exp, "name", "") or "",
            getattr(exp, "role", "") or "",
            " ".join(exp.bullets),
        ]
    )


def _experience_text(resume: ResumeStructured, exp_id: str | None) -> str:
    if not exp_id:
        return ""
    for exp in resume.experiences + resume.projects:
        if exp.id == exp_id:
            return _experience_blob(exp)
    return ""


def _best_experience(jd_text: str, resume: ResumeStructured) -> tuple[str | None, float]:
    best_id, best_score = None, 0.0
    for exp in resume.experiences + resume.projects:
        blob = _experience_blob(exp)
        cov = keyword_coverage(jd_text, blob)
        if cov > best_score:
            best_id, best_score = exp.id, cov
    return best_id, best_score


def _tier_for(coverage: float, semantic: float, strength: float) -> Tier:
    """档位 = 关键词基线 + 语义近似 + 证据强度（权重写在函数里，改动必须同步 06 第 3 节说明）。"""
    score = 0.40 * coverage + 0.35 * semantic + 0.25 * strength
    if score >= 0.55 and strength >= 0.6 and (coverage >= 0.25 or semantic >= 0.8):
        return "strong"
    if score >= 0.25:
        return "discussable"
    return "gap"


def match_item(jd_id: str, jd_text: str, resume: ResumeStructured, haystack: str) -> ItemMatch:
    coverage = keyword_coverage(jd_text, haystack)
    semantic = semantic_overlap(jd_text, haystack)
    exp_id, exp_cov = _best_experience(jd_text, resume)
    strength = 0.0
    if exp_id:
        has_metrics = bool(resume.metrics_map().get(exp_id, []))
        if exp_cov >= 0.15 and has_metrics:
            strength = 1.0
        elif exp_cov >= 0.10:
            strength = 0.6
        elif exp_cov > 0:
            strength = 0.3

    override = threshold_verdict(jd_text, resume)
    if override is not None:
        tier, note = override
        return ItemMatch(
            jd_id=jd_id,
            jd_text=jd_text,
            best_exp_id=None,  # 门槛类要求不属于"经历证据"，不借用经历 ID 冒充
            coverage=coverage,
            semantic=semantic,
            evidence_strength=0.0,
            score=round(0.40 * coverage + 0.35 * semantic, 4),
            tier=tier,
            gap_note=note,
            follow_up="面试官可能追问：你凭什么认为自己的经历等价于这条门槛要求？请准备可核对的证据。",
        )

    tier = _tier_for(coverage, semantic, strength)
    gap_note = ""
    # 层级错配：JD 要管人，证据只有执行动作。关键词/语义分再高也不许给 strong。
    if tier == "strong" and leadership_level_mismatch(jd_text, _experience_text(resume, exp_id)):
        tier = "discussable"
        gap_note = "岗位要求管理/带队职责，简历为实习执行角色，未见带队证据"
    if tier == "gap":
        gap_note = "简历中无对应证据" if (not exp_id or exp_cov < 0.1) else "有相关经历但缺少量化结果"
    elif tier == "discussable" and not gap_note:
        gap_note = "有相关经历，但证据不够直接，需要面试时补充说明"
    return ItemMatch(
        jd_id=jd_id,
        jd_text=jd_text,
        best_exp_id=exp_id if strength >= 0.3 else None,
        coverage=coverage,
        semantic=semantic,
        evidence_strength=strength,
        score=round(0.40 * coverage + 0.35 * semantic + 0.25 * strength, 4),
        tier=tier,
        gap_note=gap_note,
        follow_up=f"面试官可能追问：{jd_text[:18]}……你具体做过哪一步？",
    )


@dataclass
class MatchResult:
    dimensions: list[dict] = field(default_factory=list)
    verdict_tier: Tier = "gap"
    top_strength: str = ""
    top_gap: str = ""
    item_matches: list[ItemMatch] = field(default_factory=list)
    semantic_mode: str = "lexicon"


def _dimension(name: str, items: list[ItemMatch], tier_override: Tier | None = None) -> dict:
    if not items:
        return {
            "name": name,
            "tier": tier_override or "gap",
            "evidence_refs": [],
            "note": "JD 未给出该维度的要求，无对应证据",
            "rows": [],
        }
    tiers = [i.tier for i in items]
    if "strong" in tiers and "gap" not in tiers and tiers.count("strong") >= max(1, len(tiers) // 2):
        tier: Tier = "strong"
    elif tiers.count("gap") >= max(1, len(tiers) // 2 + len(tiers) % 2):
        tier = "gap"
    else:
        tier = "discussable"
    if tier_override:
        tier = tier_override

    exp_refs = [i.best_exp_id for i in items if i.best_exp_id]
    ordered_exp: list[str] = []
    for ref in exp_refs:
        if ref not in ordered_exp:
            ordered_exp.append(ref)
    refs = ordered_exp[:2] + [i.jd_id for i in items][:3]
    rows = [
        {
            "jd_ref": i.jd_id,
            "jd_text": i.jd_text,
            "exp_ref": i.best_exp_id or "无对应证据",
            "gap": i.gap_note or "无",
            "follow_up": i.follow_up,
            "tier": i.tier,
        }
        for i in items
    ]
    note = f"{len([i for i in items if i.tier == 'strong'])}/{len(items)} 条要求有直接量化证据"
    if not ordered_exp:
        note += "；无对应证据"
    return {"name": name, "tier": tier, "evidence_refs": refs, "note": note, "rows": rows}


def build_match(resume: ResumeStructured, jd: JdDecoded) -> MatchResult:
    haystack = _resume_text(resume)
    must = [match_item(i.id, i.text, resume, haystack) for i in jd.must_have]
    nice = [match_item(i.id, i.text, resume, haystack) for i in jd.nice_to_have]
    resp = [match_item(i.id, i.text, resume, haystack) for i in jd.responsibilities]

    dim_hard = _dimension("硬性条件", must)
    dim_duty = _dimension("职责匹配", resp)
    # 履历证据：看"有量化结果的经历"是否够支撑 JD
    evidence_items = [i for i in must + resp if i.best_exp_id]
    if evidence_items:
        with_metrics = [
            i for i in evidence_items
            if resume.metrics_map().get(i.best_exp_id or "", [])
        ]
        ratio = len(with_metrics) / len(evidence_items)
        exp_tier: Tier = "strong" if ratio >= 0.6 else ("discussable" if ratio >= 0.3 else "gap")
    else:
        ratio = 0.0
        exp_tier = "gap"
    dim_exp = _dimension("履历证据", evidence_items, tier_override=exp_tier)
    dim_exp["note"] = f"{len(evidence_items)} 条要求找到对应经历，其中 {round(ratio * 100)}% 带量化结果"
    if not any(str(r).startswith(("exp_", "proj_")) for r in dim_exp["evidence_refs"]):
        dim_exp["note"] += "；无对应证据"
    # 这一节的读者问题是"我的经历够不够硬"，不是再列一遍 JD：按经历去重，各留一条最强的证据行
    seen_exp: set[str] = set()
    deduped_rows: list[dict] = []
    for row in sorted(dim_exp["rows"], key=lambda r: r.get("tier") == "strong", reverse=True):
        exp_ref = row.get("exp_ref")
        if exp_ref in seen_exp or exp_ref == "无对应证据":
            continue
        seen_exp.add(exp_ref)
        deduped_rows.append(row)
    if deduped_rows:
        dim_exp["rows"] = deduped_rows[:3]
    dim_nice = _dimension("加分项", nice, tier_override="gap" if not nice else None)

    dims = [dim_hard, dim_duty, dim_exp, dim_nice]
    tiers = [d["tier"] for d in dims]
    hard_tier, duty_tier = dims[0]["tier"], dims[1]["tier"]
    # 判定口径：硬性条件与职责同时缺口才算 gap；加分项缺口不该把整体拖成 gap
    if hard_tier == "strong" and duty_tier in ("strong", "discussable") and tiers.count("strong") >= 3:
        verdict: Tier = "strong"
    elif hard_tier == "gap" and duty_tier == "gap":
        verdict = "gap"
    elif tiers.count("gap") >= 3:
        verdict = "gap"
    else:
        verdict = "discussable"

    all_items = must + nice + resp
    priority = {i.jd_id: 0 for i in must}
    priority.update({i.jd_id: 1 for i in resp})
    priority.update({i.jd_id: 2 for i in nice})
    # 亮点只认"有经历证据"的强项：学历满足这类门槛不算亮点，加分项也不该抢主位
    strong_items = sorted(
        [i for i in all_items if i.tier == "strong" and i.best_exp_id],
        key=lambda i: (priority.get(i.jd_id, 3), -i.score),
    )
    gap_items = sorted([i for i in all_items if i.tier == "gap"], key=lambda i: i.score)
    if strong_items:
        pick = strong_items[0]
        top_strength = f"{pick.jd_text}（{pick.jd_id} / {pick.best_exp_id}）"
    else:
        # 没有可支撑的强项时不许硬编一个"亮点"：报告里写"最大亮点：无…强项"自相矛盾
        top_strength = "无明显亮点（仅门槛类条件满足，需面试验证）"
    top_gap = f"{gap_items[0].jd_text}（{gap_items[0].jd_id}）" if gap_items else "无明显硬性缺口"

    return MatchResult(
        dimensions=dims,
        verdict_tier=verdict,
        top_strength=top_strength,
        top_gap=top_gap,
        item_matches=all_items,
    )
