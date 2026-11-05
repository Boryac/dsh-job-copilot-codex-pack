"""匹配基线测试（T3.3）：门槛类要求按事实判定、四维档位、证据引用完整性。"""
from __future__ import annotations

from app.orchestrator.matching import (
    build_match,
    keyword_coverage,
    leadership_level_mismatch,
    match_item,
    threshold_verdict,
)
from app.parsers.jd import decode_jd
from app.parsers.resume import parse_resume


def _match(settings, resume_path, jd_text):
    resume = parse_resume(resume_path, settings, resume_id="t")
    jd = decode_jd(jd_text, settings)
    return resume, jd, build_match(resume, jd)


def test_four_dimensions_always_present(settings, bd_resume_path, bd_jd_text):
    _, _, match = _match(settings, bd_resume_path, bd_jd_text)
    assert [d["name"] for d in match.dimensions] == ["硬性条件", "职责匹配", "履历证据", "加分项"]
    assert all(d["tier"] in ("strong", "discussable", "gap") for d in match.dimensions)


def test_education_threshold_is_judged_by_facts(settings, bd_resume_path, bd_jd_text):
    resume, jd, match = _match(settings, bd_resume_path, bd_jd_text)
    edu_item = next(i for i in jd.must_have if "学历" in i.text)
    verdict = threshold_verdict(edu_item.text, resume)
    assert verdict is not None
    assert verdict[0] == "strong"  # 简历是本科，JD 要求本科及以上


def test_years_threshold_is_gap_for_intern(settings, bd_resume_path, bd_jd_text):
    resume, jd, match = _match(settings, bd_resume_path, bd_jd_text)
    years_item = next(i for i in jd.must_have if "年以上" in i.text)
    matched = next(i for i in match.item_matches if i.jd_id == years_item.id)
    assert matched.tier == "gap"
    assert "个月" in matched.gap_note  # 必须给出真实累计月数，而不是含糊过去


def test_threshold_items_do_not_borrow_experience_ids(settings, bd_resume_path, bd_jd_text):
    resume, jd, match = _match(settings, bd_resume_path, bd_jd_text)
    for item in match.item_matches:
        if threshold_verdict(item.jd_text, resume) is not None:
            assert item.best_exp_id is None


def test_keyword_coverage_is_deterministic(bd_resume_path, settings):
    from app.orchestrator.matching import _resume_text

    resume = parse_resume(bd_resume_path, settings, resume_id="t")
    haystack = _resume_text(resume)
    a = keyword_coverage("负责商户拓展与签约", haystack)
    b = keyword_coverage("负责商户拓展与签约", haystack)
    assert a == b
    assert 0.0 <= a <= 1.0


def test_unrelated_resume_is_gap(settings, da_resume_path, bd_jd_text):
    _, _, match = _match(settings, da_resume_path, bd_jd_text)
    assert match.verdict_tier == "gap"


def test_matching_resume_is_not_gap(settings, da_resume_path, da_jd_text):
    _, _, match = _match(settings, da_resume_path, da_jd_text)
    assert match.verdict_tier in ("discussable", "strong")


def test_every_row_has_both_sides_or_gap_note(settings, bd_resume_path, bd_jd_text):
    _, _, match = _match(settings, bd_resume_path, bd_jd_text)
    for dim in match.dimensions:
        refs = dim["evidence_refs"]
        has_exp = any(r.startswith(("exp_", "proj_")) for r in refs)
        has_jd = any(r.startswith("jd_") for r in refs)
        if not (has_exp and has_jd):
            assert "无对应证据" in dim["note"]
        for row in dim["rows"]:
            assert row["jd_ref"].startswith("jd_")


def test_top_strength_has_evidence_reference(settings, bd_resume_path, bd_jd_text):
    _, _, match = _match(settings, bd_resume_path, bd_jd_text)
    if "无明显亮点" not in match.top_strength:
        assert "exp_" in match.top_strength or "proj_" in match.top_strength


def test_semantic_mode_is_declared(settings, bd_resume_path, bd_jd_text):
    _, _, match = _match(settings, bd_resume_path, bd_jd_text)
    assert match.semantic_mode == "lexicon"  # mock 下用确定性词表，不假装是向量模型


# ------------------------------------------------- 管理层级守卫（v1 补缺口）
def test_leadership_requirement_is_not_strong_for_intern(settings, da_resume_path):
    """实习生不能因为"搭建""团队"这类词重合，就被判成具备管理 10 人团队的证据。"""
    resume = parse_resume(da_resume_path, settings, resume_id="t")
    from app.orchestrator.matching import _resume_text

    item = match_item(
        "jd_99",
        "搭建并管理 10 人以上数据分析团队，负责招聘、培养与绩效",
        resume,
        _resume_text(resume),
    )
    assert item.tier != "strong", f"实习生被判成管理岗强项：{item.tier}"
    assert "管理" in item.gap_note and "未见带队证据" in item.gap_note


def test_leadership_guard_keeps_real_leadership_evidence():
    """真带过团队的经历不该被一刀切压掉。"""
    assert leadership_level_mismatch("带领 5 人团队完成交付", "担任组长，带领 5 人完成交付") is False
    assert leadership_level_mismatch("负责日常运营", "任何内容") is False
    assert leadership_level_mismatch("搭建并管理 10 人团队", "负责 40 张报表") is True


def test_leadership_guard_does_not_touch_non_leadership_items(settings, bd_resume_path):
    resume = parse_resume(bd_resume_path, settings, resume_id="t")
    from app.orchestrator.matching import _resume_text

    item = match_item("jd_98", "负责本地生活商户的拓展与签约", resume, _resume_text(resume))
    assert item.tier == "strong"
    assert "未见带队证据" not in item.gap_note


# ------------------------------------------------- 管理层级守卫（v1 补缺口）
def test_leadership_requirement_is_not_strong_for_intern(settings, da_resume_path):
    """实习生不能因为"搭建""团队"这类词重合，就被判成具备管理 10 人团队的证据。"""
    resume = parse_resume(da_resume_path, settings, resume_id="t")
    from app.orchestrator.matching import _resume_text

    item = match_item(
        "jd_99",
        "搭建并管理 10 人以上数据分析团队，负责招聘、培养与绩效",
        resume,
        _resume_text(resume),
    )
    assert item.tier != "strong", f"实习生被判成管理岗强项：{item.tier}"
    assert "管理" in item.gap_note and "未见带队证据" in item.gap_note


def test_leadership_guard_keeps_real_leadership_evidence():
    """真带过团队的经历不该被一刀切压掉。"""
    assert leadership_level_mismatch("带领 5 人团队完成交付", "担任组长，带领 5 人完成交付") is False
    assert leadership_level_mismatch("负责日常运营", "任何内容") is False
    assert leadership_level_mismatch("搭建并管理 10 人团队", "负责 40 张报表") is True


def test_leadership_guard_does_not_touch_non_leadership_items(settings, bd_resume_path):
    resume = parse_resume(bd_resume_path, settings, resume_id="t")
    from app.orchestrator.matching import _resume_text

    item = match_item("jd_98", "负责本地生活商户的拓展与签约", resume, _resume_text(resume))
    assert item.tier == "strong"
    assert "未见带队证据" not in item.gap_note
