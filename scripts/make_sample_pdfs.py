"""把 templates/samples/*.txt 渲染成 PDF，用于 SmartResume 实证。

为什么要 PDF：上游对 txt 只把整段当成 1 个"文本行"，无法用行号索引回填 jobDescription，
bullet 必然为空；PDF 才走它正常的逐行抽取路径。PDF 也是真实简历的形态。

用法（需要 reportlab，装在 .tmp/sr-venv 里即可，不进 requirements）：
    .tmp/sr-venv/Scripts/python.exe scripts/make_sample_pdfs.py --out .tmp/resumes-pdf
"""
from __future__ import annotations

import argparse
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas

PACK = Path(__file__).resolve().parent.parent
SAMPLES = PACK / "templates" / "samples"
DEFAULT = ["resume-bd.txt", "resume-da.txt", "resume-pm.txt"]


def render(txt: Path, out: Path) -> Path:
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    c = canvas.Canvas(str(out), pagesize=A4)
    width, height = A4
    c.setFont("STSong-Light", 10)
    y = height - 56
    for raw in txt.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        # 按字符数硬折行，避免中文长行画出页面
        while len(line) > 46:
            c.drawString(56, y, line[:46])
            line = line[46:]
            y -= 15
            if y < 56:
                c.showPage()
                c.setFont("STSong-Light", 10)
                y = height - 56
        c.drawString(56, y, line)
        y -= 15
        if y < 56:
            c.showPage()
            c.setFont("STSong-Light", 10)
            y = height - 56
    c.save()
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=".tmp/resumes-pdf")
    ap.add_argument("--samples", nargs="*", default=DEFAULT)
    args = ap.parse_args()
    out_dir = PACK / args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in args.samples:
        src = SAMPLES / name
        if not src.exists():
            print(f"跳过（不存在）：{src}")
            continue
        dst = render(src, out_dir / (src.stem + ".pdf"))
        print(f"{src.name} -> {dst}  ({dst.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
