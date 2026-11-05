"""文本提取层：PDF / DOCX / 纯文本 / 图片。

设计取舍（08 第 5 节选项 1）：
- 不做本地 OCR，图片简历直接标注"需 OCR，当前环境未启用"，不假装解析成功。
- PDF 只要抽不到足够文本（< 40 字），就判定为扫描件并给出 note，交给上层决定降级。
- 任何第三方解析库缺失都只降级，不抛裸异常给用户。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

MIN_TEXT_CHARS = 40
SUPPORTED_SUFFIXES = {".pdf", ".docx", ".doc", ".txt", ".md", ".png", ".jpg", ".jpeg", ".webp"}


@dataclass
class ExtractionResult:
    text: str
    source_type: str
    pages: int = 0
    notes: list[str] = field(default_factory=list)
    is_scanned: bool = False


def _read_text_file(path: Path) -> ExtractionResult:
    for encoding in ("utf-8", "utf-8-sig", "gb18030"):
        try:
            return ExtractionResult(text=path.read_text(encoding=encoding), source_type="text", pages=1)
        except UnicodeDecodeError:
            continue
    return ExtractionResult(text="", source_type="text", notes=["文本编码无法识别（已尝试 utf-8 / gb18030）"])


def _read_pdf(path: Path) -> ExtractionResult:
    try:
        from pypdf import PdfReader
    except ImportError:
        return ExtractionResult(
            text="", source_type="pdf", notes=["缺少 pypdf 依赖，PDF 文本未能提取（降级为 fallback）"]
        )
    try:
        reader = PdfReader(str(path))
        chunks: list[str] = []
        for page in reader.pages:
            chunks.append(page.extract_text() or "")
        text = "\n".join(chunks)
    except Exception as exc:  # 加密、损坏、非标准 PDF 都归到这里
        return ExtractionResult(
            text="", source_type="pdf", notes=[f"PDF 解析失败：{type(exc).__name__}（需用户提供文本版简历）"]
        )
    notes: list[str] = []
    is_scanned = len(text.strip()) < MIN_TEXT_CHARS
    if is_scanned:
        notes.append("PDF 可提取文本过少，疑似扫描件；未启用 OCR，相关字段标记为待核实")
    return ExtractionResult(text=text, source_type="pdf", pages=len(reader.pages), notes=notes, is_scanned=is_scanned)


def _read_docx(path: Path) -> ExtractionResult:
    try:
        import docx  # python-docx
    except ImportError:
        return ExtractionResult(
            text="", source_type="docx", notes=["缺少 python-docx 依赖，DOCX 文本未能提取（降级为 fallback）"]
        )
    try:
        document = docx.Document(str(path))
    except Exception as exc:
        return ExtractionResult(
            text="", source_type="docx", notes=[f"DOCX 解析失败：{type(exc).__name__}"]
        )
    parts: list[str] = [p.text for p in document.paragraphs]
    for table in document.tables:  # 表格型经历：按行拼接，保留单元格边界
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells]
            if any(cells):
                parts.append("  ".join(cells))
    return ExtractionResult(text="\n".join(parts), source_type="docx", pages=1)


def _read_image(path: Path) -> ExtractionResult:
    return ExtractionResult(
        text="",
        source_type="image",
        notes=["图片简历需要 OCR，当前环境未启用 OCR；请在解析方式上标注为 fallback，并建议用户提供 PDF/DOCX 版本"],
        is_scanned=True,
    )


def extract_text(path: str | Path) -> ExtractionResult:
    p = Path(path)
    if not p.exists():
        return ExtractionResult(text="", source_type="unknown", notes=[f"文件不存在：{p.name}"])
    suffix = p.suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        return ExtractionResult(text="", source_type=suffix.lstrip(".") or "unknown",
                                notes=[f"不支持的文件类型：{suffix}"])
    if suffix in {".txt", ".md"}:
        return _read_text_file(p)
    if suffix == ".pdf":
        return _read_pdf(p)
    if suffix in {".docx", ".doc"}:
        if suffix == ".doc":
            return ExtractionResult(text="", source_type="doc", notes=["旧版 .doc 不支持，请另存为 .docx"])
        return _read_docx(p)
    return _read_image(p)
