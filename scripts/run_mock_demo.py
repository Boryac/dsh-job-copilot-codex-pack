"""Mock 端到端演示（T2.5）：走真实编排链路，不调用任何外部付费服务。

与旧版的区别：不再手写报告文本。这里调的是 `orchestrator.service.run_analysis`，
也就是 DSH 插件 / HTTP 接口背后同一条链路：解析 -> 拆 JD -> 公司背调 -> 四维匹配
-> 自我介绍 -> 面试题 -> 8 节报告 -> 校验 -> Markdown 导出。

用法：
    python3 scripts/run_mock_demo.py                  # 单组（BD）
    python3 scripts/run_mock_demo.py --all            # 三组职业方向各跑一次
    python3 scripts/run_mock_demo.py --depth deep --confirmed-deep
    python3 scripts/run_mock_demo.py --out-dir .tmp/demo
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PACK_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PACK_DIR / "starter" / "sidecar"))

from app.config import load_settings  # noqa: E402
from app.orchestrator.service import run_analysis  # noqa: E402

SAMPLES = PACK_DIR / "templates" / "samples"

# 每组对应一个职业方向，验证生成逻辑不是只对 BD 有效（A4 的通用性证据）。
CASES = {
    "bd": ("resume-bd.txt", "jd-bd.txt", "云栖生活"),
    "da": ("resume-da.txt", "jd-da.txt", "星河数据"),
    "pm": ("resume-pm.txt", "jd-pm.txt", "未知示例公司"),
}


def run_case(name: str, out_dir: Path, depth: str, confirmed_deep: bool) -> dict:
    resume_file, jd_file, company = CASES[name]
    resume_path = SAMPLES / resume_file
    jd_text = (SAMPLES / jd_file).read_text(encoding="utf-8")

    settings = load_settings()
    result = run_analysis(
        resume_path=resume_path,
        jd_text=jd_text,
        company_name=company,
        settings=settings,
        depth=depth,
        confirmed_deep=confirmed_deep,
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / result.filename
    report_path.write_text(result.markdown, encoding="utf-8")

    card_path = out_dir / f"card-{name}.json"
    card_path.write_text(json.dumps(result.card, ensure_ascii=False, indent=2), encoding="utf-8")

    card = result.card
    print(f"[{name}] 简历={resume_file} JD={jd_file} 公司={company}")
    print(f"      档位={card['verdict_tier']} 解析方式={card.get('parsing_mode')} 报告={report_path.name}")
    print(f"      亮点={card['top_strength'][:60]}")
    print(f"      缺口={card['top_gap'][:60]}")
    print(f"      片段耗时={result.timings}")
    if result.degradations:
        print(f"      降级={result.degradations}")
    if result.validation_warnings:
        print(f"      校验提醒={result.validation_warnings}")
    return {
        "case": name,
        "report_filename": result.filename,
        "verdict_tier": card["verdict_tier"],
        "questions": len(result.structured.interview_questions),
        "anchors": len(result.structured.self_intro.anchors),
        "timings": result.timings,
        "degradations": result.degradations,
        "validation_warnings": result.validation_warnings,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", choices=sorted(CASES), default="bd", help="跑哪一组样例")
    ap.add_argument("--all", action="store_true", help="三组样例都跑")
    ap.add_argument("--depth", choices=["basic", "deep"], default="basic")
    ap.add_argument("--confirmed-deep", action="store_true", help="deep 路径必须先确认，否则不会真跑")
    ap.add_argument("--out-dir", default=str(PACK_DIR / ".tmp" / "demo"))
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    names = sorted(CASES) if args.all else [args.case]
    summary = [run_case(name, out_dir, args.depth, args.confirmed_deep) for name in names]

    summary_path = out_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nmock demo ok -> {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
