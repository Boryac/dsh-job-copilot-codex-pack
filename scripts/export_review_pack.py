"""导出「真人复核包」：把题面、evidence_ref、证据原文与报告节选摊开，交给真人按 rubric 打分。

边界（必须守住）：
- 本脚本只导出材料 + 空白复核清单，**不替真人打分**，也不写"已人工评审通过"；
- 复核包用脱敏虚构样例（templates/samples），不含任何真实简历、电话、邮箱；
- 每题都带 evidence_ref 与该 ID 的原文，方便真人核对"题面是否真的被证据支撑"。

用法：
    python3 scripts/export_review_pack.py
    python3 scripts/export_review_pack.py --case golden_06_bd_strong --case golden_07_gap
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path

PACK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PACK / "starter" / "sidecar"))

from app.config import Settings  # noqa: E402
from app.orchestrator.service import run_analysis  # noqa: E402

GOLDEN_DIR = PACK / "templates" / "golden"
OUT_DIR = PACK / "docs" / "review-pack"
DEFAULT_CASES = ("golden_06_bd_strong", "golden_07_gap")
SECTION_EXCERPTS = (0, 3, 5, 8)


def _evidence_source(result, ref: str) -> tuple[str, str]:
    """返回 (类型, 原文)。类型只有 exp / proj / jd 三种，找不到就如实说找不到。"""
    resume = result.resume
    for exp in resume.experiences:
        if exp.id == ref:
            body = "\n".join(f"  - {b}" for b in exp.bullets)
            return "工作经历", f"{exp.company or ''} / {exp.role or ''} / {exp.period or ''}\n{body}"
    for proj in resume.projects:
        if proj.id == ref:
            body = "\n".join(f"  - {b}" for b in proj.bullets)
            return "项目经历", f"{proj.name or ''}\n{body}"
    jd = result.structured.jd
    for item in jd.must_have + jd.nice_to_have + jd.responsibilities:
        if item.id == ref:
            return "JD 要求", item.text
    return "未找到", "（该 ID 在简历与 JD 中都不存在，属严重问题）"


def _report_section(markdown: str, number: int) -> str:
    key = f"## 第 {number} 节"
    start = markdown.find(key)
    if start == -1:
        return f"（报告缺少{key}）"
    nxt = markdown.find("\n## ", start + len(key))
    return markdown[start : nxt if nxt != -1 else len(markdown)].rstrip()


def _build_pack(case: dict, result) -> str:
    report = result.structured
    verdict = report.verdict
    lines: list[str] = [
        f"# 真人复核包：{case['case_id']}",
        "",
        "> 本文件由 `scripts/export_review_pack.py` 自动导出。**AI 没有、也不能代替真人完成评审**：",
        "> 下面的复核清单全部留空，请由招聘/业务侧同事按 `09_TESTING_ACCEPTANCE.md` 第 3 节 rubric 填写。",
        "> 样例为脱敏虚构简历与 JD，不含真实个人信息。",
        "",
        "## 1. 复核对象",
        "",
        "| 项 | 内容 |",
        "|---|---|",
        f"| 用例 | `{case['case_id']}` |",
        f"| 方向 | {case.get('direction', '')} |",
        f"| 简历（虚构） | `{case['resume_file']}` |",
        f"| JD（虚构） | `{case['jd_file']}` |",
        f"| 公司输入 | {case['company_name_input']} |",
        f"| 系统档位 | **{verdict.tier}** |",
        f"| 一句话 headline | {verdict.headline} |",
        f"| 最大亮点 | {verdict.top_strength} |",
        f"| 最大缺口 | {verdict.top_gap} |",
        f"| 面试题数量 | {len(report.interview_questions)} 道（要求 ≥8） |",
        "",
        f"导出时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "## 2. 四维匹配（只看档位，不看百分比）",
        "",
        "| 维度 | 档位 | 证据引用 | 说明 |",
        "|---|---|---|---|",
    ]
    for dim in report.match.dimensions:
        refs = "、".join(dim.evidence_refs) if dim.evidence_refs else "—"
        lines.append(f"| {dim.name} | {dim.tier} | {refs} | {dim.note} |")

    lines += [
        "",
        "## 3. 逐题材料（题面 + evidence_ref + 证据原文）",
        "",
        "复核时请重点看：题面是否真的被 evidence_ref 的原文支撑，而不是拿 ID 凑数。",
        "",
    ]
    for q in report.interview_questions:
        kind, source = _evidence_source(result, q.evidence_ref)
        lines += [
            f"### {q.id}｜{q.category}｜`{q.evidence_ref}`",
            "",
            f"- **题面**：{q.question}",
            f"- **考察点**：{q.focus}",
            f"- **追问**：{q.follow_up or '（无）'}",
            f"- **坑**：{q.pitfall or '（无）'}",
            f"- **证据类型**：{kind}",
            "",
            "评估点（STAR，供核对是否与原文一致）：",
            "",
            f"> 情境：{q.star_answer.situation}",
            f"> 任务：{q.star_answer.task}",
            f"> 行动：{q.star_answer.action}",
            f"> 结果：{q.star_answer.result}",
            "",
            "证据原文：",
            "",
            "```text",
            source,
            "```",
            "",
        ]

    lines += ["## 4. 报告节选", ""]
    for number in SECTION_EXCERPTS:
        lines += [f"### 第 {number} 节原文", "", "```markdown", _report_section(result.markdown, number), "```", ""]

    lines += [
        "## 5. 复核清单（请真人填写，AI 不得代填）",
        "",
        "判定口径（09 第 3 节）：相关性、证据真实性、可追问性**三项全通过**才算这道题通过。",
        "",
        "复核人：____________　背景（招聘/业务/其他）：____________　日期：____________",
        "",
        "| 题号 | 证据引用 | 相关性 | 证据真实性 | 可追问性 | 判定（通过/不通过） | 问题描述 |",
        "|---|---|---|---|---|---|---|",
    ]
    for q in report.interview_questions:
        lines.append(f"| {q.id} | `{q.evidence_ref}` | ☐ | ☐ | ☐ |  |  |")
    lines += [
        "",
        "### 汇总",
        "",
        "| 项 | 结果 |",
        "|---|---|",
        f"| 题目总数 | {len(report.interview_questions)} |",
        "| 通过题数 |  |",
        "| 通过率 |  |（v1 要求 ≥ 70%） |",
        "| 是否存在证据造假（题面与原文不符 / ID 不存在） |  |",
        "| 是否认可当前档位 |  |",
        "| 复核人签名 |  |",
        "",
        "### 复核人意见（自由填写）",
        "",
        "```text",
        "（请写：哪些题不自然、哪些证据撑不住题面、档位是否该调整、要不要改措辞）",
        "```",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", action="append", default=None, help="golden case_id，可重复")
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    args = ap.parse_args()

    wanted = args.case or list(DEFAULT_CASES)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    all_cases = {json.loads(p.read_text(encoding="utf-8"))["case_id"]: p for p in GOLDEN_DIR.glob("*.json")}
    missing = [c for c in wanted if c not in all_cases]
    if missing:
        print(f"找不到 golden case：{missing}")
        return 1

    written: list[dict] = []
    for case_id in wanted:
        case = json.loads(all_cases[case_id].read_text(encoding="utf-8"))
        settings = Settings(app_mode="mock", cache_dir=Path(tempfile.mkdtemp(prefix="review-pack-")))
        result = run_analysis(
            PACK / case["resume_file"],
            (PACK / case["jd_file"]).read_text(encoding="utf-8"),
            case["company_name_input"],
            settings,
        )
        text = _build_pack(case, result)
        path = out_dir / f"{case_id}.md"
        path.write_text(text, encoding="utf-8")
        written.append(
            {
                "case_id": case_id,
                "tier": result.structured.verdict.tier,
                "questions": [
                    {"id": q.id, "ref": q.evidence_ref} for q in result.structured.interview_questions
                ],
                "file": path.relative_to(PACK).as_posix(),
            }
        )
        print(f"导出 {case_id}：档位={result.structured.verdict.tier}，题数={len(result.structured.interview_questions)} -> {path}")

    index = [
        "# 真人复核包（索引）",
        "",
        "> **这不是一份已完成的评审记录。** AI 没有、也不能代替真人完成评审：只负责把材料摊开并留出填写位；",
        "> 判定必须由真人按 `09_TESTING_ACCEPTANCE.md` 第 3 节 rubic 亲自完成。",
        "> 在真人回填之前，`docs/REVIEW_T3.4.md` 的结论只能算 AI 自评，不能算人工评审。",
        "",
        "## 包内文件",
        "",
        "| 用例 | 档位 | 题数 | 文件 |",
        "|---|---|---|---|",
    ]
    for item in written:
        index.append(
            f"| `{item['case_id']}` | {item['tier']} | {len(item['questions'])} | [{item['file']}]({Path(item['file']).name}) |"
        )

    total = sum(len(item["questions"]) for item in written)
    index += [
        "",
        "## 复核清单（合并版：两组合成一张表，可直接打印）",
        "",
        "判定口径：相关性、证据真实性、可追问性三项全通过，该题才算通过。",
        "",
        "| 用例 | 题号 | 证据引用 | 相关性 | 证据真实性 | 可追问性 | 判定（通过/不通过） | 问题描述 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for item in written:
        for q in item["questions"]:
            index.append(
                f"| {item['case_id']} | {q['id']} | `{q['ref']}` | ☐ | ☐ | ☐ |  |  |"
            )
    index += [
        "",
        f"合计 **{total}** 题（" + " + ".join(f"{item['case_id']} {len(item['questions'])} 题" for item in written) + "）。",
        "",
        "| 汇总 | 结果 |",
        "|---|---|",
        f"| 题目总数 | {total} |",
        "| 通过题数 |  |",
        "| 通过率 |  |（v1 要求 ≥ 70%） |",
        "| 是否发现证据造假 |  |",
        "| 是否认可两组档位（strong / gap） |  |",
        "| 复核人 / 日期 |  |",
        "",
        "> 这份合并表只是把两份包里的清单并到一处，便于一次打完；判定仍必须由真人填写。",
    ]
    index += [
        "",
        "## 复核怎么做（给真人，约 40 分钟）",
        "",
        "1. 先读第 2 节四维表：判断档位是否与你的直觉一致，不一致先记下来；",
        "2. 逐题读第 3 节：题面 → evidence_ref → 证据原文，问自己三个问题：",
        "   - **相关性**：这道题是不是这个岗位真会问的？",
        "   - **证据真实性**：题面里的数字/动作，能不能在证据原文里找到？",
        "   - **可追问性**：如果你继续追问一层，候选人有没有可能露馅？",
        "3. 在第 5 节表格里逐题打勾并写问题描述（只写总分不算评审完成）；",
        "4. 填汇总：通过率（要求 ≥70%）、是否发现证据造假、是否认可档位；",
        "5. 回填后把本文件与两份复核表一起更新到 `PROGRESS.md` 的已知缺口 1。",
        "",
        "## 复核人建议来源",
        "",
        "- 做过校园招聘/社招初筛的 HR（看题面自然度）；",
        "- 用人部门面试官（看考察点是否对准岗位）；",
        "- 至少 1 人，2 人以上更好（记录分歧点）。",
        "",
        "## 生成命令",
        "",
        "```bash",
        "python3 scripts/export_review_pack.py --case golden_06_bd_strong --case golden_07_gap",
        "# 想额外复核常见档位（discussable）时：",
        "python3 scripts/export_review_pack.py --case golden_01_bd",
        "```",
        "",
    ]
    index_path = PACK / "docs" / "HUMAN_REVIEW_PACK.md"
    index_path.write_text("\n".join(index), encoding="utf-8")
    print(f"索引 -> {index_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
