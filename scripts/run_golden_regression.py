"""golden set 回归（T4.3）：逐组跑真实编排链路，按 golden case 的要点判定通过/不通过。

判定原则（对齐验收标准）：
- 只判"必须出现什么 / 绝不允许什么"，不做全文精确匹配；
- 规则检查打底，人工复核兜底；LLM 评审只能做辅助筛查，不作为唯一判定；
- 通过率 = 通过组数 / 总组数，要求 ≥ 80%，且不允许出现证据造假、付费误调用、隐私泄露这类严重失败
  （严重失败直接让该组不通过，与要点是否命中无关）。

用法：
    python3 scripts/run_golden_regression.py
    python3 scripts/run_golden_regression.py --json .tmp/golden-report.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PACK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PACK / "starter" / "sidecar"))

from app.config import load_settings  # noqa: E402
from app.orchestrator.service import run_analysis  # noqa: E402

GOLDEN_DIR = PACK / "templates" / "golden"
PASS_RATE_MIN = 0.8
# v1 补缺口：三档必须都有 golden 覆盖，否则"档位能区分"只是口头结论。
TIER_COVERAGE_REQUIRED = {"strong", "discussable", "gap"}
PHONE_RE = re.compile(r"1[3-9]\d{9}")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")


class CaseResult:
    def __init__(self, case_id: str, direction: str, expected_tier: str = ""):
        self.case_id = case_id
        self.direction = direction
        self.expected_tier = expected_tier
        self.checks: list[dict] = []
        self.severe: list[str] = []

    @property
    def passed(self) -> bool:
        return not self.severe and all(c["ok"] for c in self.checks)


def _questions_text(report) -> str:
    return " ".join(q.question + q.focus + q.follow_up for q in report.interview_questions)


def _report_text(result) -> str:
    return result.markdown


def _run_check(check: dict, result) -> tuple[bool, str]:
    kind = check.get("type")
    report = result.structured
    markdown = _report_text(result)

    if kind == "tier_equals":
        ok = report.verdict.tier == check["value"]
        return ok, f"档位={report.verdict.tier}（期望 {check['value']}）"

    if kind == "min_questions":
        n = len(report.interview_questions)
        return n >= check["value"], f"面试题 {n} 道（>={check['value']}）"

    if kind == "min_anchors":
        n = len(report.self_intro.anchors)
        return n >= check["value"], f"锚点 {n} 条（>={check['value']}）"

    if kind == "dimensions_present":
        names = {d.name for d in report.match.dimensions}
        missing = [v for v in check["values"] if v not in names]
        return not missing, f"四维缺失 {missing}" if missing else "四维齐全"

    if kind == "question_mentions":
        text = _questions_text(report)
        hit = [v for v in check["values"] if v in text]
        return bool(hit), f"命中关键词 {hit}" if hit else f"面试题未提及 {check['values']}"

    if kind == "question_ref_prefixes":
        refs = [q.evidence_ref for q in report.interview_questions]
        hit = [r for r in refs if any(r.startswith(p) for p in check["values"])]
        return bool(hit), f"命中 {hit[:3]}" if hit else f"没有以 {check['values']} 开头的 evidence_ref"

    if kind == "report_contains":
        missing = [v for v in check["values"] if v not in markdown]
        return not missing, f"报告缺少 {missing}" if missing else "关键小节齐全"

    if kind == "company_resolved_contains":
        name = result.company.company_resolved.name if result.company else None
        ok = bool(name and check["value"] in name)
        return ok, f"公司主体={name}"

    if kind == "company_unresolved":
        name = result.company.company_resolved.name if result.company else None
        confirm = (
            result.company.company_resolved.disambiguation.needs_user_confirm if result.company else False
        )
        ok = name is None
        return ok, f"公司主体={name}，需确认={confirm}"

    if kind == "no_pii":
        leaked = PHONE_RE.findall(markdown) + EMAIL_RE.findall(markdown)
        return not leaked, f"泄露 {leaked}" if leaked else "无手机号/邮箱"

    if kind == "mock_sources_only":
        urls = result.company.soft_profile.source_urls if result.company else []
        bad = [u for u in urls if not u.startswith("mock://")]
        return not bad, f"非 mock 来源 {bad}" if bad else f"{len(urls)} 条来源均为 mock://"

    if kind == "hard_data_no_inferred":
        fields = result.company.hard_data.fields() if result.company else {}
        bad = [k for k, f in fields.items() if "inferred" in f.model_dump()]
        return not bad, f"硬数据被标成推断 {bad}" if bad else "硬数据无 inferred"

    if kind == "questions_not_contain":
        text = _questions_text(report)
        hit = [v for v in check["values"] if v in text]
        return not hit, f"题面出现禁用表述 {hit}" if hit else "题面无禁用表述"

    if kind == "report_not_contains":
        hit = [v for v in check["values"] if v in markdown]
        return not hit, f"出现禁用内容 {hit}" if hit else "未出现禁用内容"

    raise ValueError(f"未知的 check 类型：{kind}")


def _severe_failures(result, resume) -> list[str]:
    """严重失败：与要点无关，一票否决该组。"""
    problems: list[str] = []
    exp_ids = resume.evidence_ids()
    jd_ids = result.jd.all_ids()
    for q in result.structured.interview_questions:
        if q.evidence_ref not in exp_ids and q.evidence_ref not in jd_ids:
            problems.append(f"题目 {q.id} 的 evidence_ref={q.evidence_ref} 不存在（证据造假）")
    if result.company is not None:
        quota = result.company.quota_consumed
        if result.company.depth_used == "basic" and quota.tianyancha_calls > 2:
            problems.append(f"basic 路径出现 {quota.tianyancha_calls} 次天眼查调用（疑似付费误调用）")
    if PHONE_RE.search(result.markdown) or EMAIL_RE.search(result.markdown):
        problems.append("报告正文出现手机号或邮箱（隐私泄露）")
    return problems


def run_case(path: Path, settings) -> CaseResult:
    case = json.loads(path.read_text(encoding="utf-8"))
    outcome = CaseResult(case["case_id"], case.get("direction", ""), case.get("expected_tier", ""))
    result = run_analysis(
        resume_path=PACK / case["resume_file"],
        jd_text=(PACK / case["jd_file"]).read_text(encoding="utf-8"),
        company_name=case["company_name_input"],
        settings=settings,
    )
    outcome.severe = _severe_failures(result, result.resume)

    for point in case["expected_points"] + case.get("forbidden", []):
        ok, detail = _run_check(point["check"], result)
        outcome.checks.append(
            {"id": point["id"], "desc": point["desc"], "kind": "must" if point in case["expected_points"] else "forbidden", "ok": ok, "detail": detail}
        )
    return outcome


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=str(PACK / ".tmp" / "golden-report.json"))
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    settings = load_settings()
    cases = sorted(GOLDEN_DIR.glob("*.json"))
    if not cases:
        print(f"没有找到 golden case：{GOLDEN_DIR}")
        return 1

    outcomes = [run_case(path, settings) for path in cases]
    passed = [o for o in outcomes if o.passed]
    rate = len(passed) / len(outcomes)
    covered = {o.expected_tier for o in outcomes}
    missing_tiers = sorted(TIER_COVERAGE_REQUIRED - covered)

    for outcome in outcomes:
        flag = "PASS" if outcome.passed else "FAIL"
        print(f"[{flag}] {outcome.case_id} {outcome.direction}")
        for problem in outcome.severe:
            print(f"      严重失败：{problem}")
        for check in outcome.checks:
            if args.verbose or not check["ok"]:
                mark = "ok" if check["ok"] else "NG"
                print(f"      {mark} {check['id']}[{check['kind']}] {check['desc']} → {check['detail']}")

    print(f"\n通过 {len(passed)}/{len(outcomes)} = {rate:.0%}（要求 >= {PASS_RATE_MIN:.0%}）")
    print(f"档位覆盖：{sorted(covered)}（要求 {sorted(TIER_COVERAGE_REQUIRED)}）")
    report = {
        "pass_rate": round(rate, 4),
        "threshold": PASS_RATE_MIN,
        "passed": rate >= PASS_RATE_MIN and not missing_tiers,
        "total_cases": len(outcomes),
        "tier_coverage": sorted(covered),
        "tier_coverage_missing": missing_tiers,
        "cases": [
            {
                "case_id": o.case_id,
                "direction": o.direction,
                "expected_tier": o.expected_tier,
                "passed": o.passed,
                "severe": o.severe,
                "checks": o.checks,
            }
            for o in outcomes
        ],
    }
    out = Path(args.json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"明细 -> {out}")
    if missing_tiers:
        print(f"档位覆盖不全：缺少 {missing_tiers} 的 golden 用例（三档必须都有样例）")
        return 3
    return 0 if rate >= PASS_RATE_MIN else 2


if __name__ == "__main__":
    raise SystemExit(main())
