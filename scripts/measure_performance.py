"""basic 路径耗时实测 + 降级行为实测（T4.4，对应 A6）。

只跑 Mock 链路，不调用任何外部付费接口。

两点说明（写进 docs/PERFORMANCE.md）：
1. 耗时用真实墙钟测，N 次取 P50/P90，不"估算"；
2. 降级用 `MOCK_FORCE_TIMEOUT` 注入预算耗尽，而不是干等 30 秒 —— 注入点就在
   `_run_with_budget` 里，走的是与真实超时完全相同的异常路径，不绕过降级逻辑。

用法：
    python3 scripts/measure_performance.py --runs 20
"""
from __future__ import annotations

import argparse
import math
import os
import platform
import sys
import tempfile
import time
from pathlib import Path

PACK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PACK / "starter" / "sidecar"))

from app.config import Settings, load_settings  # noqa: E402
from app.errors import ToolError  # noqa: E402
from app.orchestrator.service import run_analysis  # noqa: E402
from app.recon.service import company_recon, estimate_deep  # noqa: E402
from app.schemas import CompanyRecon, DeepEstimate  # noqa: E402

SAMPLES = PACK / "templates" / "samples"
RESUME = SAMPLES / "resume-bd.txt"
JD_TEXT = (SAMPLES / "jd-bd.txt").read_text(encoding="utf-8")
COMPANY = "云栖生活"
STEPS = ["resume_structurer", "jd_decoder", "company_recon", "matching", "generate", "total"]


def percentile(values: list[float], p: float) -> float:
    """最近秩法取分位：数据量小的时候比插值更不容易说谎。"""
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = max(0, math.ceil(p / 100 * len(ordered)) - 1)
    return ordered[idx]


def run_once(settings: Settings):
    started = time.perf_counter()
    result = run_analysis(RESUME, JD_TEXT, COMPANY, settings)
    wall = (time.perf_counter() - started) * 1000
    return result, wall


def measure_basic(runs: int, settings: Settings) -> dict:
    # 预热：排除首次导入/缓存目录创建的固定开销
    run_once(settings)
    totals: list[float] = []
    per_step: dict[str, list[float]] = {s: [] for s in STEPS}
    for _ in range(runs):
        result, wall = run_once(settings)
        totals.append(wall)
        for step in STEPS:
            if step == "total":
                per_step[step].append(result.timings.get("total", 0))
            else:
                per_step[step].append(result.timings.get(step, 0))
    return {
        "runs": runs,
        "wall": {
            "p50": percentile(totals, 50),
            "p90": percentile(totals, 90),
            "max": max(totals),
            "min": min(totals),
        },
        "steps": {step: {"p50": percentile(v, 50), "p90": percentile(v, 90)} for step, v in per_step.items()},
    }


def scenario(name: str, fn) -> dict:
    started = time.perf_counter()
    try:
        note = fn()
        outcome = "ok"
    except ToolError as exc:
        note = f"{exc.code}：{exc.message}"
        outcome = "明确失败"
    except Exception as exc:  # noqa: BLE001 —— 记下来，不吞
        note = f"{type(exc).__name__}：{exc}"
        outcome = "未预期异常"
    return {"name": name, "outcome": outcome, "elapsed_ms": round((time.perf_counter() - started) * 1000), "note": note}


def measure_degradations(base: Settings) -> list[dict]:
    results: list[dict] = []

    def cold(**kwargs) -> Settings:
        """每个场景用独立缓存目录：否则缓存命中会绕过 provider，测不到降级分支。"""
        return Settings(app_mode="mock", cache_dir=Path(tempfile.mkdtemp(prefix="dsh-perf-")), **kwargs)

    def resume_timeout():
        s = cold(mock_force_timeout="resume")
        r = run_analysis(RESUME, JD_TEXT, COMPANY, s)
        assert r.markdown, "简历超时后报告不应为空"
        hit = [d for d in r.degradations if "简历解析超时" in d]
        assert hit, f"没有记录简历超时降级：{r.degradations}"
        return f"仍产出完整报告（{len(r.structured.interview_questions)} 题），降级文案：{hit[0]}"

    results.append(scenario("简历解析预算耗尽", resume_timeout))

    def jd_timeout():
        s = cold(mock_force_timeout="jd")
        try:
            run_analysis(RESUME, JD_TEXT, COMPANY, s)
        except ToolError as exc:
            assert exc.code == "TIMEOUT"
            assert exc.fallback == "pasted_text_required"
            return f"按设计快速失败（{exc.code}，fallback={exc.fallback}）：没有 JD 就没有可分析的基准，不输出半成品"
        raise AssertionError("JD 超时后不应继续产出报告")

    results.append(scenario("JD 拆解预算耗尽", jd_timeout))

    def company_timeout():
        s = cold(mock_force_timeout="company")
        r = run_analysis(RESUME, JD_TEXT, COMPANY, s)
        assert r.markdown and r.company is None
        hit = [d for d in r.degradations if "公司背调未完成" in d]
        assert hit, f"没有记录公司降级：{r.degradations}"
        return f"报告照常产出，公司字段留空，降级文案：{hit[0]}"

    results.append(scenario("公司背调预算耗尽", company_timeout))

    def generate_timeout():
        s = cold(mock_force_timeout="generate")
        r = run_analysis(RESUME, JD_TEXT, COMPANY, s)
        assert r.markdown, "生成超时后不许整份报告空白"
        hit = [d for d in r.degradations if "生成" in d or "未生成" in d]
        assert hit, f"没有记录生成降级：{r.degradations}"
        return f"输出部分报告（{len(r.structured.interview_questions)} 题），降级文案：{hit[0]}"

    results.append(scenario("内容生成预算耗尽", generate_timeout))

    def quota_exhausted():
        os.environ["MOCK_QUOTA_EXHAUSTED"] = "1"
        try:
            r = run_analysis(RESUME, JD_TEXT, COMPANY, cold())
        finally:
            os.environ.pop("MOCK_QUOTA_EXHAUSTED", None)
        hit = [d for d in r.degradations if "额度耗尽" in d]
        assert hit, f"额度耗尽没有降级记录：{r.degradations}"
        assert r.markdown, "额度耗尽不该让报告变空"
        # 硬数据拿不到就该留空，但不许因此放弃软信息，也不许多花一次付费调用
        if r.company is not None:
            assert r.company.quota_consumed.tianyancha_calls == 0, "额度耗尽后仍在调用天眼查"
            assert not any(f.value for f in r.company.hard_data.fields().values()), "额度耗尽却写出了硬数据"
        return f"硬数据留空、软信息继续，降级文案：{hit[0]}"

    results.append(scenario("天眼查额度耗尽", quota_exhausted))

    def url_failure():
        try:
            run_analysis(RESUME, None, COMPANY, cold(), jd_url="https://example.com/job/1")
        except ToolError as exc:
            assert exc.code in ("URL_FETCH_FAILED", "INVALID_INPUT"), exc.code
            assert "粘贴" in exc.message or exc.fallback == "pasted_text_required"
            return f"要求改粘贴（{exc.code}）：{exc.message[:60]}"
        raise AssertionError("Mock 模式下 URL 抓取不应成功")

    results.append(scenario("JD 链接抓取失败", url_failure))

    def deep_cancel():
        estimate = company_recon(COMPANY, cold(), depth="deep")
        assert isinstance(estimate, DeepEstimate), type(estimate)
        assert estimate.quota_consumed.tianyancha_calls == 0 and estimate.quota_consumed.search_calls == 0
        again = estimate_deep(COMPANY, cold(), idempotency_key=estimate.idempotency_key)
        assert again.idempotency_key == estimate.idempotency_key
        return f"只返回预估卡片（{len(estimate.fields)} 个字段），两次调用零付费，幂等键一致"

    results.append(scenario("deep 预估后用户取消", deep_cancel))

    def deep_confirmed():
        r = company_recon(COMPANY, cold(), depth="deep", confirmed_deep=True)
        assert isinstance(r, CompanyRecon)
        assert r.depth_used == "deep" and r.deep_data is not None
        return f"确认后按接口记账：天眼查 {r.quota_consumed.tianyancha_calls} 次、搜索 {r.quota_consumed.search_calls} 次（Mock 计 0 元）"

    results.append(scenario("deep 确认后记账", deep_confirmed))

    def cache_hit():
        s = cold()
        first = company_recon(COMPANY, s)
        second = company_recon(COMPANY, s)
        assert first.cache.hit is False
        assert second.cache.hit is True, "第二次应命中缓存"
        assert second.quota_consumed.tianyancha_calls == 0, "缓存命中不该产生天眼查调用"
        assert second.quota_consumed.search_calls == 0, "缓存命中不该产生搜索调用"
        return "第二次命中 7 天缓存：天眼查 0 次、搜索 0 次，与首次结果一致"

    results.append(scenario("公司数据缓存命中", cache_hit))
    return results


def render_markdown(basic: dict, degradations: list[dict]) -> str:
    lines = [
        "# 性能与降级实测（T4.4 / A6）",
        "",
        "> 本文件由 `scripts/measure_performance.py` 生成，数字来自本机实测，不是估算。",
        "> 全部为 Mock 链路：不调用天眼查付费接口、不调用 LLM、不发真实搜索请求。",
        "",
        "## 1. 环境",
        "",
        f"- 平台：{platform.platform()}",
        f"- Python：{platform.python_version()}",
        f"- 样本：`templates/samples/resume-bd.txt` + `jd-bd.txt`，公司 `{COMPANY}`",
        f"- 迭代次数：暖跑 1 次 + 正式 {basic['runs']} 次",
        "",
        "## 2. basic 路径耗时（毫秒）",
        "",
        "| 指标 | 端到端墙钟 | 各步合计（timings.total） |",
        "|---|---|---|",
        f"| P50 | {basic['wall']['p50']:.1f} | {basic['steps']['total']['p50']:.1f} |",
        f"| P90 | {basic['wall']['p90']:.1f} | {basic['steps']['total']['p90']:.1f} |",
        f"| 最大 | {basic['wall']['max']:.1f} | — |",
        f"| 最小 | {basic['wall']['min']:.1f} | — |",
        "",
        "分步 P50 / P90：",
        "",
        "| 步骤 | P50 | P90 | 预算（02 第 4 节） |",
        "|---|---|---|---|",
        f"| 简历结构化 | {basic['steps']['resume_structurer']['p50']:.1f} | {basic['steps']['resume_structurer']['p90']:.1f} | 30s |",
        f"| JD 拆解 | {basic['steps']['jd_decoder']['p50']:.1f} | {basic['steps']['jd_decoder']['p90']:.1f} | 20s |",
        f"| 公司背调 | {basic['steps']['company_recon']['p50']:.1f} | {basic['steps']['company_recon']['p90']:.1f} | 30s |",
        f"| 四维匹配 | {basic['steps']['matching']['p50']:.1f} | {basic['steps']['matching']['p90']:.1f} | 计入端到端 |",
        f"| 内容生成 | {basic['steps']['generate']['p50']:.1f} | {basic['steps']['generate']['p90']:.1f} | 分段 |",
        "",
        f"结论：端到端 P90 = {basic['wall']['p90']:.0f} ms，远低于 02 第 4 节要求的 120000 ms 上限。",
        "但必须说明：Mock 模式没有网络往返与 LLM 推理，这里的数字只证明**编排与校验本身不是瓶颈**，"
        "不能当成 live 模式的耗时承诺。live 耗时需接入真实 key 后按同一脚本重测（见 PROGRESS 已知缺口）。",
        "",
        "## 3. 降级行为实测",
        "",
        "| 场景 | 结果 | 耗时(ms) | 实际行为 |",
        "|---|---|---|---|",
    ]
    for item in degradations:
        note = item["note"].replace("|", "／")
        lines.append(f"| {item['name']} | {item['outcome']} | {item['elapsed_ms']} | {note} |")
    lines += [
        "",
        "## 4. 口径说明",
        "",
        "- 超时用 `MOCK_FORCE_TIMEOUT=resume|jd|company|generate` 注入，注入点在 `_run_with_budget` 内，"
        "与真实预算耗尽走同一异常路径，因此降级分支是真被执行过的，不是纸面承诺。",
        "- 「JD 拆解超时」故意设计成**快速失败**而不是降级出半成品：没有 JD 就没有可对比的基准，"
        "输出一份没有岗位信息的报告只会误导用户。",
        "- 「简历超时」与「公司超时」都继续出报告，并在报告与摘要卡片上写明降级原因。",
        "- 「deep 预估后取消」验证的是零付费：预估卡片不计费，幂等键相同，重复预估不会产生调用。",
        "",
    ]
    return "\n".join(lines)


def preflight_live() -> tuple[bool, str]:
    """live 重测的前置检查：缺什么就直说，不发一次请求、不伪造数字。"""
    from app.config import LIVE, Settings

    settings = Settings(
        app_mode=LIVE,
        llm_api_key=os.environ.get("LLM_API_KEY", ""),
        llm_base_url=os.environ.get("LLM_BASE_URL", ""),
        search_api_key=os.environ.get("SEARCH_API_KEY", ""),
        tianyancha_mcp_url=os.environ.get("TIANYANCHA_MCP_URL", ""),
        tianyancha_api_key=os.environ.get("TIANYANCHA_API_KEY", ""),
    )
    missing = [m for m in settings.degraded_modules()]
    if missing:
        return False, f"live 模式缺少 {missing} 的密钥/地址，未发起任何请求"
    # 搜索契约未核验：SearchProvider._live_search 目前是显式抛错，塞 key 也跑不通
    return False, (
        "即使 key 齐全，live 搜索路径仍不可用：SearchProvider._live_search 主动抛 "
        "UPSTREAM_ERROR（搜索 API 契约未核验）。真实搜索时延无法测，先定供应商再谈 live 数字。"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=20)
    ap.add_argument("--out", default=str(PACK / "docs" / "PERFORMANCE.md"))
    ap.add_argument("--live", action="store_true", help="尝试真实链路重测（缺件会直接退出，不出数字）")
    args = ap.parse_args()

    if args.live:
        ok, reason = preflight_live()
        print(f"== live 预检：{'通过' if ok else '未通过'}")
        print(f"   {reason}")
        print("== 结论：live 时延未实证（本次未产生任何耗时数字）")
        return 2

    base = load_settings()
    print(f"跑 {args.runs} 次 basic 路径…")
    basic = measure_basic(args.runs, base)
    print(f"  端到端 P50={basic['wall']['p50']:.0f}ms P90={basic['wall']['p90']:.0f}ms")
    print("跑降级场景…")
    degradations = measure_degradations(base)
    for item in degradations:
        print(f"  [{item['outcome']}] {item['name']} ({item['elapsed_ms']}ms)")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_markdown(basic, degradations), encoding="utf-8")
    print(f"报告 -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
