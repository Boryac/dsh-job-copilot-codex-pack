"""失败模式测试（06 第 6 节清单）：每条失败路径都必须有明确降级，不许静默失败。"""
from __future__ import annotations

import pytest

from app.config import Settings
from app.errors import ToolError
from app.orchestrator.service import run_analysis
from conftest import make_blank_pdf, make_docx


def test_scanned_pdf_has_no_experiences_and_says_why(settings, tmp_path, bd_jd_text):
    path = make_blank_pdf(tmp_path / "scan.pdf")
    with pytest.raises(ToolError) as exc:
        run_analysis(path, bd_jd_text, "云栖生活", settings)
    assert exc.value.code == "PARSE_FAILED"
    assert "文本版简历" in exc.value.message


def test_image_resume_requires_ocr(settings, tmp_path, bd_jd_text):
    path = tmp_path / "resume.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n")
    with pytest.raises(ToolError):
        run_analysis(path, bd_jd_text, "云栖生活", settings)


def test_ambiguous_company_still_produces_report(settings, bd_resume_path, bd_jd_text):
    result = run_analysis(bd_resume_path, bd_jd_text, "星河数据", settings)
    assert result.company.company_resolved.name is None
    assert "公司主体未唯一确定" in result.markdown
    assert any("公司主体" in item for item in result.structured.to_verify)
    assert result.structured.verdict.tier in ("strong", "discussable", "gap")


def test_quota_exhausted_degrades_to_search_only(settings, bd_resume_path, bd_jd_text, monkeypatch):
    monkeypatch.setenv("MOCK_QUOTA_EXHAUSTED", "1")
    result = run_analysis(bd_resume_path, bd_jd_text, "云栖生活", settings)
    assert any("额度耗尽" in d for d in result.structured.degradations + result.structured.to_verify)
    assert "未获取" in result.markdown
    assert result.company.hard_data.founded_at.verified is False


def test_company_timeout_degrades_but_report_survives(bd_resume_path, bd_jd_text, tmp_path):
    slow = Settings(cache_dir=tmp_path / "cache", mock_delay_ms=400)
    object.__setattr__(slow, "timeouts_ms", {**slow.timeouts_ms, "company_recon": 60})
    result = run_analysis(bd_resume_path, bd_jd_text, "云栖生活", slow)
    assert result.company is None
    assert any("TIMEOUT" in d for d in result.degradations)
    assert "未生成" in result.markdown
    assert result.structured.interview_questions  # 其它段落照常输出


def test_generate_timeout_returns_partial_report(bd_resume_path, bd_jd_text, tmp_path, monkeypatch):
    import time

    import app.orchestrator.service as service_module

    def slow_generate(*_args, **_kwargs):
        time.sleep(0.5)
        raise AssertionError("不应执行到这里")

    monkeypatch.setattr(service_module, "generate", slow_generate)
    slow = Settings(cache_dir=tmp_path / "cache")
    object.__setattr__(slow, "timeouts_ms", {**slow.timeouts_ms, "generate": 50})
    result = run_analysis(bd_resume_path, bd_jd_text, "云栖生活", slow)
    assert result.structured.interview_questions == []
    assert any("生成步骤超时" in d for d in result.structured.degradations)
    assert "## 第 8 节" in result.markdown  # 报告结构仍完整，只是某几节未生成


def test_cancel_deep_means_zero_calls(settings, bd_resume_path, bd_jd_text):
    result = run_analysis(bd_resume_path, bd_jd_text, "云栖生活", settings, depth="deep", confirmed_deep=False)
    assert result.company.depth_used == "basic"
    assert result.company.quota_consumed.tianyancha_calls == 2  # 只有 basic 的两次
    assert any("确认" in d for d in result.degradations)


def test_docx_table_resume_is_parsed(settings, tmp_path, bd_jd_text):
    """表格型经历：按行拼接后仍要能切出经历。"""
    import docx

    path = tmp_path / "table.docx"
    document = docx.Document()
    document.add_paragraph("周某")
    document.add_paragraph("求职意向：商务拓展")
    document.add_paragraph("工作经历")
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "2025.01-2025.06  某科技  商务实习生"
    table.cell(1, 0).text = "- 负责 20 家渠道商签约，转化率提升 15%"
    document.save(str(path))
    result = run_analysis(path, bd_jd_text, "云栖生活", settings)
    assert result.structured.resume_meta.experience_count >= 1


def test_mixed_language_jd_is_handled(settings, bd_resume_path):
    jd = (
        "岗位名称：BD Manager\n工作地点：上海\n\n岗位职责：\n1. 负责渠道拓展与商户签约；\n"
        "任职要求：\n1. 本科及以上学历；\n2. 熟悉 Excel，能独立做数据分析。"
    )
    result = run_analysis(bd_resume_path, jd, "云栖生活", settings)
    assert result.structured.jd.must_have


def test_jd_too_short_is_rejected(settings, bd_resume_path):
    with pytest.raises(ToolError):
        run_analysis(bd_resume_path, "招人", "云栖生活", settings)


def test_no_jd_at_all_is_rejected(settings, bd_resume_path):
    with pytest.raises(ToolError) as exc:
        run_analysis(bd_resume_path, None, "云栖生活", settings)
    assert exc.value.code == "INVALID_INPUT"
