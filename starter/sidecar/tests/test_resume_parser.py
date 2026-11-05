"""简历解析测试（T1.3）：契约字段、ID 连续性、PII 不落库、失败模式降级。"""
from __future__ import annotations

import pytest

from app.errors import ToolError
from app.parsers.resume import FallbackResumeParser, parse_resume
from app.parsers.text_extract import extract_text
from conftest import make_blank_pdf, make_docx, make_text_pdf


def test_txt_resume_parses_core_fields(settings, bd_resume_path):
    resume = parse_resume(bd_resume_path, settings, resume_id="bd")
    assert resume.parsing_mode == "fallback"
    assert resume.basic_info.title == "商务拓展 / BD"
    assert resume.basic_info.location == "福州"
    assert [e.id for e in resume.experiences] == ["exp_01", "exp_02"]
    assert resume.experiences[0].company == "云途旅行（OTA）"
    assert resume.experiences[0].period == "2025.07-2025.09"
    assert any(m.value == "18%" for m in resume.experiences[0].metrics)


def test_pii_never_enters_structured_output(settings, bd_resume_path):
    """电话/邮箱结构上没有字段可以放，这里再加一道断言，防止以后偷偷加字段。"""
    resume = parse_resume(bd_resume_path, settings, resume_id="bd")
    dumped = resume.model_dump_json()
    assert "138-0000-0000" not in dumped
    assert "@example.com" not in dumped


def test_metrics_come_from_original_bullets(settings, bd_resume_path):
    resume = parse_resume(bd_resume_path, settings, resume_id="bd")
    bullets = " ".join(b for e in resume.experiences for b in e.bullets)
    for metric in (m for e in resume.experiences for m in e.metrics):
        assert metric.value.replace(" ", "") in bullets.replace(" ", "")


def test_docx_resume_is_supported(settings, tmp_path, bd_resume_path):
    paragraphs = bd_resume_path.read_text(encoding="utf-8").splitlines()
    path = make_docx(tmp_path / "resume.docx", paragraphs)
    resume = parse_resume(path, settings, resume_id="docx")
    assert [e.id for e in resume.experiences] == ["exp_01", "exp_02"]


def test_text_layer_pdf_is_supported(settings, tmp_path, bd_resume_path):
    lines = bd_resume_path.read_text(encoding="utf-8").splitlines()
    path = make_text_pdf(tmp_path / "resume.pdf", lines)
    resume = parse_resume(path, settings, resume_id="pdf")
    assert len(resume.experiences) >= 1


def test_scanned_pdf_is_flagged_and_not_fabricated(settings, tmp_path):
    path = make_blank_pdf(tmp_path / "scan.pdf")
    extraction = extract_text(path)
    assert extraction.is_scanned is True
    resume = parse_resume(path, settings, resume_id="scan")
    assert resume.experiences == []
    assert any("扫描件" in n or "OCR" in n for n in resume.parsing_notes)


def test_image_resume_requires_ocr_without_pretending(settings, tmp_path):
    path = tmp_path / "resume.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n")
    resume = parse_resume(path, settings, resume_id="img")
    assert resume.experiences == []
    assert any("OCR" in n for n in resume.parsing_notes)


def test_missing_file_returns_empty_structure_not_exception(settings):
    resume = parse_resume("does-not-exist.txt", settings, resume_id="none")
    assert resume.experiences == []
    assert any("不存在" in n for n in resume.parsing_notes)


def test_mixed_language_resume_keeps_english_tokens(settings, tmp_path):
    path = tmp_path / "mixed.txt"
    path.write_text(
        "Li Ming\n求职意向：Data Analyst\n\n工作经历\n2024.01-2024.06  ABC Tech  Data Intern\n"
        "- Built 3 dashboards with SQL and Python, reduced reporting time by 40%\n",
        encoding="utf-8",
    )
    resume = parse_resume(path, settings, resume_id="mixed")
    assert resume.experiences[0].company == "ABC Tech"
    assert any("40%" in m.value for m in resume.experiences[0].metrics)


def test_empty_resume_does_not_raise(settings, tmp_path):
    path = tmp_path / "empty.txt"
    path.write_text("", encoding="utf-8")
    resume = parse_resume(path, settings, resume_id="empty")
    assert resume.experiences == []


def test_fallback_parser_keeps_ids_continuous(bd_resume_path):
    extraction = extract_text(bd_resume_path)
    data = FallbackResumeParser().parse(extraction)
    ids = [e["id"] for e in data["experiences"]]
    assert ids == [f"exp_{i:02d}" for i in range(1, len(ids) + 1)]


def test_smartresume_backend_unavailable_in_mock(settings):
    from app.parsers.resume import SmartResumeBackend

    assert SmartResumeBackend(settings).available() is False


def test_parse_failure_raises_contract_error(settings, tmp_path, monkeypatch):
    """结构不合契约时必须抛 PARSE_FAILED，不许把坏结构传上去。"""
    import app.parsers.resume as resume_module

    class Boom(FallbackResumeParser):
        def parse(self, extraction, resume_id=""):
            return {"schema_version": "1.0"}  # 缺必填字段

    monkeypatch.setattr(resume_module, "FallbackResumeParser", Boom)
    path = tmp_path / "x.txt"
    path.write_text("工作经历\n2024.01-2024.06 A  B\n- 做了点事\n", encoding="utf-8")
    with pytest.raises(ToolError) as exc:
        resume_module.parse_resume(path, settings, resume_id="x")
    assert exc.value.code == "PARSE_FAILED"


# ------------------------------------------------- SmartResume 可行性（v1 补缺口）
def test_fallback_path_declares_mode_and_reason(settings, bd_resume_path):
    """走 fallback 就要说清楚：不许把规则解析写成模型解析。"""
    from app.parsers.resume import parse_resume

    resume = parse_resume(bd_resume_path, settings, resume_id="t")
    assert resume.parsing_mode == "fallback"
    assert resume.data_mode == "mock"
    assert any("Mock" in n or "fallback" in n for n in resume.parsing_notes), resume.parsing_notes


def test_smartresume_unavailable_reason_is_explicit(settings):
    from app.parsers.resume import SmartResumeBackend

    backend = SmartResumeBackend(settings)
    assert backend.available() is False
    assert "Mock" in backend.unavailable_reason()


def test_smartresume_hardware_requirements_are_recorded_and_unverified():
    """GPU/内存/存储要求要写在代码里可查，且明确标注『未实测』。"""
    from app.parsers.resume import SmartResumeBackend

    req = SmartResumeBackend.HARDWARE_MIN
    assert req["ram_gb"] >= 8
    assert req["disk_gb"] >= 10
    assert "CUDA" in req["gpu"]
    assert req["verified"] is False, "本地模型没实测，不该标成已验证"


def test_docx_fallback_keeps_experiences_and_metrics(settings, tmp_path):
    """重点验证 fallback 解析路径：DOCX 也要能出经历与量化成果，不能只出个空壳。"""
    from conftest import make_docx
    from app.parsers.resume import parse_resume

    path = make_docx(
        tmp_path / "r.docx",
        [
            "林舟（虚构样例）",
            "求职意向：商务拓展 / BD",
            "教育背景",
            "2023.09-2027.06  福州外语外贸学院  人工智能  本科",
            "工作经历",
            "2025.07-2025.09  云途旅行（OTA）  商务拓展实习生",
            "- 负责华东区 32 家酒店供应商的签约与上线，季度 GMV 提升 18%",
            "- 搭建商家分层运营 SOP，商家复购率从 21% 提升到 29%",
        ],
    )
    resume = parse_resume(path, settings, resume_id="docx")
    assert resume.parsing_mode == "fallback"
    assert resume.experiences, "DOCX 解析没有出经历"
    metrics = resume.metrics_map()
    assert metrics.get(resume.experiences[0].id), "DOCX 解析丢了量化成果"
