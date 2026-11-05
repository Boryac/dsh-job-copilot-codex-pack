"""docs/PROOF.md 的机械守门（verify.sh 第 3.9 步）。

守的是什么：
1. 五项必须都在，状态只能是「已证」或「未实证」，没有第三种；
2. 写「已证」的项，证据文件必须真的存在且非空——空文件不算证据；
3. 写「未实证」的项，必须写清还缺什么，且不许同时出现「已完成 / 已验证 / 已构建」这类自相矛盾的话；
4. 每项都要有「复现命令」和「关键日志」两行，缺一件就是证据不完整；
5. 「真人复核」只有在存在 `docs/review-pack/signed-*.md` 签字件时才允许是「已证」。

退出码：0 通过；1 有违规（逐条打印）。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

PACK = Path(__file__).resolve().parent.parent
PROOF = PACK / "docs" / "PROOF.md"
REVIEW_SIGNED_GLOB = "docs/review-pack/signed-*.md"

REQUIRED_ITEMS = {
    "docker": ("docker", "镜像"),
    "smartresume": ("smartresume",),
    "tianyancha": ("天眼查",),
    "live_perf": ("live", "性能"),
    "human_review": ("真人复核", "人工评审"),
}

CLAIM_WORDS = ("已完成", "已验证", "已构建", "已通过验收")


def split_row(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def main() -> int:
    problems: list[str] = []
    if not PROOF.exists():
        print(f"MISSING: {PROOF.relative_to(PACK)}（没有证明文件就等于没证）")
        return 1

    text = PROOF.read_text(encoding="utf-8")
    rows: list[list[str]] = []
    for line in text.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = split_row(line)
        if len(cells) >= 4 and cells[1] in ("已证", "未实证"):
            rows.append(cells)

    if not rows:
        problems.append("PROOF.md 里找不到状态表（需要 `| 项 | 状态 | 证据文件 | 仍缺/局限 |` 格式的行）")
        print("\n".join(problems))
        return 1

    seen: dict[str, list[str]] = {}
    for cells in rows:
        item, status, evidence, gap = cells[0], cells[1], cells[2], cells[3]
        low = item.lower()
        for key, kws in REQUIRED_ITEMS.items():
            if all(kw in low for kw in kws) and key not in seen:
                seen[key] = cells

        if status == "未实证":
            if not gap or gap in ("—", "-"):
                problems.append(f"[{item}] 状态=未实证 但没写「仍缺什么」")
            for w in CLAIM_WORDS:
                if w in " ".join(cells):
                    problems.append(f"[{item}] 状态=未实证 却出现「{w}」，自相矛盾")
        elif status == "已证":
            if not gap or gap in ("—", "-"):
                problems.append(f"[{item}] 状态=已证 但没写「局限」——已证也必须交代边界")
            files = [f for f in re.split(r"[,，、\s]+", evidence) if f]
            if not files:
                problems.append(f"[{item}] 状态=已证 但没列证据文件")
            for f in files:
                p = PACK / f.strip("`")
                if not p.exists():
                    problems.append(f"[{item}] 证据文件不存在：{f}")
                elif p.stat().st_size == 0:
                    problems.append(f"[{item}] 证据文件是空文件：{f}")

    for key, kws in REQUIRED_ITEMS.items():
        if key not in seen:
            problems.append(f"缺少必证项：{'/'.join(kws)}")

    # 真人复核的特殊守门：没有签字件不许写已证
    hr = seen.get("human_review")
    if hr and hr[1] == "已证":
        signed = sorted(PACK.glob(REVIEW_SIGNED_GLOB))
        if not signed:
            problems.append("[真人复核] 写了已证，但 docs/review-pack/signed-*.md 不存在——没有签字件不算复核过")

    # 三件套：每项都要有「复现命令」与「关键日志」
    sections = re.split(r"^## ", text, flags=re.M)[1:]
    if len(sections) < len(REQUIRED_ITEMS):
        problems.append(f"PROOF.md 分节数 {len(sections)} 少于必证项数 {len(REQUIRED_ITEMS)}")
    for sec in sections:
        title = sec.splitlines()[0].strip() if sec.splitlines() else "?"
        if "状态" not in sec:
            continue
        if "复现命令" not in sec:
            problems.append(f"[{title}] 缺「复现命令」")
        if "关键日志" not in sec:
            problems.append(f"[{title}] 缺「关键日志」")

    if problems:
        print("== PROOF 守门失败：")
        for p in problems:
            print(f"  NG {p}")
        return 1

    print(f"== PROOF 守门通过（{len(rows)} 项，状态词合法，证据文件齐全，三件套完整）")
    for key in REQUIRED_ITEMS:
        cells = seen[key]
        print(f"  {cells[1]:4s} {cells[0][:38]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
