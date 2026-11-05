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


def test_smartresume_hardware_requirements_are_recorded_and_measured():
    """硬件要求要写在代码里可查；2026-11-05 真跑过之后必须带实测数字，而不是空口『已验证』。"""
    from app.parsers.resume import SmartResumeBackend

    req = SmartResumeBackend.HARDWARE_MIN
    assert req["ram_gb"] >= 8
    assert req["disk_gb"] >= 10
    assert "CUDA" in req["gpu"]
    assert req["verified"] is True, "本地模型已实测（docs/proof/smartresume-cpu.json）"
    measured = req["measured"]
    assert measured["model"].startswith("Qwen3-0.6B")
    # 实测值必须能被解析成数字区间，防止写着"很快"这种不可核对的词
    low, high = measured["cpu_seconds_per_resume"].split("–")
    assert float(low) > 0 and float(high) >= float(low)
    assert float(measured["peak_rss_mb"].split("–")[1]) > 3000


def test_normalize_maps_real_upstream_payload():
    """映射必须按上游真实返回（驼峰 + 嵌套 period）写，不能按猜的 snake_case。

    这条用 2026-11-05 实跑抓到的结构做样本：曾经因为映射猜错，
    experiences 整段为空且校验不过，最终静默降级成 fallback，报告却看不出来。
    """
    from app.parsers.resume import SmartResumeBackend

    raw = {
        "basicInfo": {"name": "林舟", "currentLocation": "福州", "personalEmail": "a@example.com"},
        "workExperience": [
            {
                "companyName": "云途旅行（OTA）",
                "position": "商务拓展实习生",
                "employmentPeriod": {"startDate": "2025.07", "endDate": "2025.09"},
                "jobDescription": "2025.07-2025.09 云途旅行（OTA） 商务拓展实习生\n"
                "- 负责华东区 32 家酒店供应商的签约与上线，季度 GMV 提升 18%\n"
                "- 搭建商家分层运营 SOP，商家复购率从 21% 提升到 29%",
            }
        ],
        "education": [
            {
                "school": "福州外语外贸学院",
                "major": "人工智能",
                "degreeLevel": "本科",
                "period": {"startDate": "2023.09", "endDate": "2027.06"},
                "department": "",
                "educationDescription": "主修课程：概率统计",
            }
        ],
    }
    out = SmartResumeBackend._normalize(raw)

    assert out["parsing_mode"] == "smartresume"
    assert out["basic_info"]["name"] == "林舟"
    assert out["basic_info"]["location"] == "福州"
    assert out["education"][0]["degree"] == "本科"
    assert out["education"][0]["period"] == "2023.09-2027.06"
    exp = out["experiences"][0]
    assert exp["company"] == "云途旅行（OTA）"
    assert exp["role"] == "商务拓展实习生"
    assert exp["period"] == "2025.07-2025.09"
    # 头行（时间+公司+岗位）不许混进 bullet 当证据
    assert len(exp["bullets"]) == 2, exp["bullets"]
    assert not exp["bullets"][0].startswith("2025.07")
    assert [m["value"] for m in exp["metrics"]][:2] == ["32家", "18%"]


def test_normalize_flags_upstream_limits():
    """上游只支持 3 类抽取、文本输入无 bullet 回填——这两点必须写进 parsing_notes 让人看得见。"""
    from app.parsers.resume import SmartResumeBackend

    raw = {
        "basicInfo": {"name": "张三"},
        "workExperience": [{"companyName": "A", "position": "B", "jobDescription": ""}],
    }
    out = SmartResumeBackend._normalize(raw)
    joined = " ".join(out["parsing_notes"])
    assert "projects" in joined and "skills" in joined
    assert "jobDescription" in joined


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


def test_empty_smartresume_result_degrades_instead_of_claiming_success(settings, bd_resume_path, monkeypatch):
    """上游返回空壳时必须降级，不能把"什么都没抽到"标成 smartresume 成功。

    真实踩坑：GPU 上缺 accelerate，模型没加载，上游返回空 dict，
    映射后是合法但全空的结构，parsing_mode 仍为 smartresume。
    """
    import app.parsers.resume as resume_module

    monkeypatch.setattr(resume_module.SmartResumeBackend, "available", lambda self: True)
    monkeypatch.setattr(
        resume_module.SmartResumeBackend,
        "parse",
        lambda self, path, resume_id, extract_types: {
            "schema_version": "1.0",
            "parsing_mode": "smartresume",
            "basic_info": {"name": None, "title": None, "location": None, "links": []},
            "education": [],
            "experiences": [],
            "projects": [],
            "skills": [],
            "parsing_notes": [],
            "data_mode": "live",
        },
    )
    resume = resume_module.parse_resume(bd_resume_path, settings, resume_id="empty")
    assert resume.parsing_mode == "fallback"
    assert resume.experiences, "降级后必须真的从原文解析出经历"
    assert any("空结构" in n for n in resume.parsing_notes), resume.parsing_notes
