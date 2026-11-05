"""测试公共夹具：路径、Settings、样例简历/JD、PDF/DOCX 构造器。

约定：测试只读 templates/samples 下的虚构样例，不写入任何真实简历或密钥。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SIDECAR_DIR = Path(__file__).resolve().parents[1]
PACK_DIR = SIDECAR_DIR.parents[1]
SAMPLES = PACK_DIR / "templates" / "samples"

sys.path.insert(0, str(SIDECAR_DIR))

from app.config import Settings  # noqa: E402


@pytest.fixture()
def settings(tmp_path) -> Settings:
    return Settings(cache_dir=tmp_path / "cache")


@pytest.fixture(scope="session")
def bd_resume_path() -> Path:
    return SAMPLES / "resume-bd.txt"


@pytest.fixture(scope="session")
def bd_jd_text() -> str:
    return (SAMPLES / "jd-bd.txt").read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def da_resume_path() -> Path:
    return SAMPLES / "resume-da.txt"


@pytest.fixture(scope="session")
def da_jd_text() -> str:
    return (SAMPLES / "jd-da.txt").read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def bd_jd_path() -> Path:
    return SAMPLES / "jd-bd.txt"


@pytest.fixture()
def bd_analysis(settings, bd_resume_path, bd_jd_text):
    """跑一遍完整 Mock 流程，供报告/校验器测试复用。"""
    from app.orchestrator.service import run_analysis

    return run_analysis(bd_resume_path, bd_jd_text, "云栖生活", settings)


def make_docx(path: Path, paragraphs: list[str]) -> Path:
    """生成一个带中文段落的 DOCX，用于验证 DOCX 文本提取路径。"""
    import docx

    document = docx.Document()
    for text in paragraphs:
        document.add_paragraph(text)
    document.save(str(path))
    return path


def make_text_pdf(path: Path, lines: list[str]) -> Path:
    """生成带文字层的 PDF（不是扫描件），用于验证 PDF 文本提取路径。"""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfgen import canvas

    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    c = canvas.Canvas(str(path), pagesize=A4)
    y = 800
    for line in lines:
        c.setFont("STSong-Light", 10)
        c.drawString(50, y, line)
        y -= 14
    c.save()
    return path


def make_blank_pdf(path: Path) -> Path:
    """生成无文字层的 PDF，模拟扫描件（用于验证 is_scanned 降级）。"""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path), pagesize=A4)
    c.rect(50, 500, 200, 100, fill=1)
    c.save()
    return path
