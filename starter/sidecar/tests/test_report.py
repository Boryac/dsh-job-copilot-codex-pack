"""报告渲染测试：8 节齐全且顺序正确、分区正确、免责句在场、无 PII。"""
from __future__ import annotations

import re

from app.orchestrator.report import DISCLAIMER, REQUIRED_SECTIONS, build_filename, render_report, sanitize_filename_part


def test_all_sections_present_in_order(bd_analysis):
    markdown = bd_analysis.markdown
    positions = [markdown.find(title) for title in REQUIRED_SECTIONS]
    assert all(pos >= 0 for pos in positions), [
        title for title, pos in zip(REQUIRED_SECTIONS, positions) if pos < 0
    ]
    assert positions == sorted(positions), "8 节顺序必须与报告规范一致"
    assert len(REQUIRED_SECTIONS) == 9  # 第 0 节 + 8 节


def test_report_has_no_extra_sections(bd_analysis):
    found = re.findall(r"^## 第 (\d+) 节", bd_analysis.markdown, flags=re.M)
    assert found == [str(i) for i in range(0, 9)]


def test_disclaimer_is_verbatim(bd_analysis):
    assert DISCLAIMER in bd_analysis.markdown


def test_hard_and_soft_are_separated(bd_analysis):
    markdown = bd_analysis.markdown
    assert "### 硬数据（verified）" in markdown
    assert "### 产品线矩阵" in markdown
    assert "### 风险与关注点" in markdown
    assert "推断（inferred）" in markdown


def test_no_pii_in_report(bd_analysis):
    markdown = bd_analysis.markdown
    assert not re.search(r"1[3-9]\d{9}", markdown)
    assert "@example.com" not in markdown


def test_match_table_rows_carry_both_ids(bd_analysis):
    rows = [line for line in bd_analysis.markdown.splitlines() if line.startswith("| 硬性条件") or line.startswith("| 职责匹配")]
    assert rows
    for row in rows:
        assert re.search(r"jd_\d{2}", row)
        assert re.search(r"exp_\d{2}|无对应证据", row)


def test_interview_section_lists_evidence(bd_analysis):
    markdown = bd_analysis.markdown
    section = markdown.split("## 第 5 节")[1].split("## 第 6 节")[0]
    assert section.count("evidence_ref") >= 8
    assert "STAR 回答骨架" in section


def test_sources_table_and_to_verify_present(bd_analysis):
    markdown = bd_analysis.markdown
    section8 = markdown.split("## 第 8 节")[1]
    assert "| 数据项 | 来源 | 置信度 | 抓取时间 |" in section8
    assert "待核实清单" in section8


def test_filename_sanitizes_unsafe_chars(bd_analysis):
    name = build_filename(bd_analysis.structured)
    assert name.startswith("report-") and name.endswith(".md")
    assert not re.search(r'[\\/:*?"<>|]', name)
    assert bd_analysis.analysis_id[:8] in name


def test_filename_part_truncates_and_replaces():
    assert sanitize_filename_part("a/b:c*d?e") == "a-b-c-d-e"
    assert len(sanitize_filename_part("长" * 100)) <= 40


def test_summary_card_has_required_fields(bd_analysis):
    card = bd_analysis.card
    for key in ("analysis_id", "verdict_tier", "headline", "top_strength", "top_gap", "recommended_action",
                "report_filename", "sections", "data_mode"):
        assert key in card
    assert card["verdict_tier"] in ("strong", "discussable", "gap")
    assert len(card["sections"]) == 9


def test_render_is_stable(bd_analysis):
    again = render_report(bd_analysis.structured)
    assert again == bd_analysis.markdown


def test_mock_data_mode_is_declared(bd_analysis):
    assert bd_analysis.structured.data_mode == "mock"
    assert "数据模式：mock" in bd_analysis.markdown


def test_filename_falls_back_to_user_input_when_ambiguous(bd_analysis, settings):
    """消歧失败时用用户输入的名字命名，不要把 company 这种占位词丢给用户。"""
    from app.recon.service import company_recon

    bd_analysis.structured.company = company_recon("星河数据", settings)
    name = build_filename(bd_analysis.structured)
    assert "星河数据" in name
    assert "company" not in name
