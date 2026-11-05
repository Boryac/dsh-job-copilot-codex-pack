"""公司消歧（05 第 2 节）：排序理由必须写清楚，定不到就标 needs_user_confirm。"""
from __future__ import annotations

import difflib

from ..mockdata import normalize_company_name
from ..schemas import Disambiguation, DisambiguationCandidate

# 名称差小于这个值就认为"不能唯一确定"，宁可让用户确认，也不随机挑一个
TIE_THRESHOLD = 0.08
MIN_CHOSEN_SCORE = 0.45


def _scope_overlap(business_scope: str, role_keywords: list[str]) -> float:
    if not business_scope or not role_keywords:
        return 0.0
    hits = sum(1 for kw in role_keywords if kw and kw in business_scope)
    return min(hits / max(len(role_keywords), 1), 1.0)


def score_candidates(
    company_input: str,
    candidates: list[dict],
    role_keywords: list[str] | None = None,
) -> list[DisambiguationCandidate]:
    role_keywords = role_keywords or []
    target = normalize_company_name(company_input)
    scored: list[DisambiguationCandidate] = []
    for cand in candidates:
        name = cand.get("name", "")
        cand_norm = normalize_company_name(name)
        ratio = difflib.SequenceMatcher(None, target, cand_norm).ratio()
        # 用户输入常常是工商全称的前缀（"云栖生活" vs "云栖生活科技（福州）"）：
        # 前缀命中比逐字符相似度更能反映真实消歧依据，给一个下限而不是继续压低阈值。
        if target and target in cand_norm:
            ratio = max(ratio, 0.85)
        overlap = _scope_overlap(cand.get("business_scope", ""), role_keywords)
        score = round(0.75 * ratio + 0.25 * overlap, 4)
        reason = f"名称相似度 {ratio:.2f}"
        if overlap:
            reason += f"；经营范围与岗位关键词重合 {overlap:.2f}"
        if cand.get("region"):
            reason += f"；注册地 {cand['region']}"
        scored.append(
            DisambiguationCandidate(
                name=name,
                unified_credit_code=cand.get("unified_credit_code"),
                region=cand.get("region"),
                legal_representative=cand.get("legal_representative"),
                match_reason=reason,
                score=score,
            )
        )
    return sorted(scored, key=lambda c: c.score or 0.0, reverse=True)


def disambiguate(
    company_input: str,
    candidates: list[dict],
    role_keywords: list[str] | None = None,
) -> tuple[DisambiguationCandidate | None, Disambiguation]:
    scored = score_candidates(company_input, candidates, role_keywords)
    if not scored:
        return None, Disambiguation(candidates=[], chosen_reason="未检索到任何候选工商主体", needs_user_confirm=True)

    top = scored[0]
    if len(scored) == 1:
        if (top.score or 0) < MIN_CHOSEN_SCORE:
            return None, Disambiguation(
                candidates=scored,
                chosen_reason=f"仅 1 个候选但名称相似度过低（{top.score:.2f}），需用户确认",
                needs_user_confirm=True,
            )
        return top, Disambiguation(candidates=scored, chosen_reason=top.match_reason, needs_user_confirm=False)

    second = scored[1]
    gap = (top.score or 0) - (second.score or 0)
    if gap < TIE_THRESHOLD or (top.score or 0) < MIN_CHOSEN_SCORE:
        reason = (
            f"前两名得分接近（{top.score:.2f} vs {second.score:.2f}），"
            "无法唯一确定工商主体，已列出候选等待用户确认"
        )
        return None, Disambiguation(candidates=scored[:3], chosen_reason=reason, needs_user_confirm=True)

    return top, Disambiguation(
        candidates=scored[:3],
        chosen_reason=f"{top.match_reason}；领先第二名 {gap:.2f}",
        needs_user_confirm=False,
    )
