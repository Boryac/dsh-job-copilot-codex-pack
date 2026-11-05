"""天眼查真实调用实证（basic 1 家 + deep 1 家，预估→确认→按明细记账）。

只认三件套：可复现命令（本文件）、原始产物（docs/proof/tianyancha-live.json）、结论加局限（docs/ENV_FEASIBILITY.md）。

纪律（写进代码，不靠自觉）：
- key 只从 `starter/.env` 或进程环境读，**任何输出只出现它的 sha256 前 12 位**；
- 硬数据来源必须是 `tianyancha_mcp`，出现 `mock://` 一律判失败（那是 Mock 串进了 live）；
- deep 必须先拿预估卡片、确认后才查，取消 = 零调用；
- 费用按 `TIANYANCHA_UNIT_COST_YUAN` 记账，超过 `TIANYANCHA_COST_CAP_YUAN` 立即抛错停手；
- 缺 key / 缺 MCP 地址时**不发请求**，直接落一份 status=not_run 的产物，不许写成"已验证"。

用法：
    python3 scripts/proof_tianyancha.py            # 有 key 就真跑；没有就落 not_run
    python3 scripts/proof_tianyancha.py --dry-run  # 只跑 Mock 隔离这一段（本地可执行的唯一部分）
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

PACK = Path(__file__).resolve().parent.parent
SIDECAR = PACK / "starter" / "sidecar"
ENV_FILE = PACK / "starter" / ".env"
OUT = PACK / "docs" / "proof" / "tianyancha-live.json"
COMPANY = "上海携程商务有限公司"  # 真实存在的 OTA 主体，basic/deep 都有公开工商与司法数据
MOCK_COMPANY = "云栖生活科技（福州）有限公司"  # mockdata.py 里的虚构主体，用来验缓存隔离
DEEP_FIELDS_CAP_NOTE = "deep 走股东穿透/实控人/司法风险，共 6 次调用"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(SIDECAR))


def load_env_file(path: Path) -> dict[str, str]:
    """只解析 KEY=VALUE；不打印任何值。"""
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip("'\"")
    return out


def redact(secret: str) -> str:
    if not secret:
        return "<empty>"
    return "sha256:" + hashlib.sha256(secret.encode("utf-8")).hexdigest()[:12] + f"（长度 {len(secret)}）"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="只跑 Mock 缓存隔离，不做任何真实调用")
    ap.add_argument("--json", default=str(OUT))
    ap.add_argument("--company", default=COMPANY)
    args = ap.parse_args()

    env = load_env_file(ENV_FILE)
    mcp_url = (env.get("TIANYANCHA_MCP_URL") or os.environ.get("TIANYANCHA_MCP_URL") or "").strip()
    api_key = (env.get("TIANYANCHA_API_KEY") or os.environ.get("TIANYANCHA_API_KEY") or "").strip()

    from app.config import LIVE, MOCK, Settings
    from app.recon.cache import CompanyCache
    from app.recon.service import company_recon, estimate_deep

    report: dict = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "company": args.company,
        "key_present": bool(api_key),
        "key_fingerprint": redact(api_key),
        "mcp_url_present": bool(mcp_url),
        "cap_yuan": float(os.environ.get("TIANYANCHA_COST_CAP_YUAN") or 5.0),
        "unit_cost_yuan": float(os.environ.get("TIANYANCHA_UNIT_COST_YUAN") or 0.0),
        "steps": [],
        "status": "not_run",
    }

    def step(name: str, ok: bool, detail: dict) -> None:
        report["steps"].append({"step": name, "ok": bool(ok), "detail": detail})
        print(f"  {'ok' if ok else 'NG'} {name}")

    # ---- 第一步：Mock 缓存隔离（无论有没有 key 都能跑） ----
    cache_dir = PACK / ".tmp" / "tyc-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    for p in list(cache_dir.rglob("*.json")):
        p.unlink()
    mock_settings = Settings(app_mode=MOCK, cache_dir=cache_dir)
    mock_res = company_recon(MOCK_COMPANY, mock_settings, depth="basic")
    cache = CompanyCache(cache_dir, mock_settings.company_cache_days)
    mock_files = sorted((cache_dir / "company").glob("*.json"))
    mock_hard = mock_res.hard_data.model_dump() if hasattr(mock_res.hard_data, "model_dump") else {}
    mock_sources = {v.get("source") for v in mock_hard.values() if isinstance(v, dict)}
    step(
        "mock 缓存落盘",
        bool(mock_files) and any(str(s).startswith("mock://") for s in mock_sources),
        {
            "cache_files": [p.name for p in mock_files],
            "sources": sorted(x for x in mock_sources if x),
            "data_mode": mock_res.data_mode,
            "quota_calls": mock_res.quota_consumed.tianyancha_calls,
        },
    )

    if args.dry_run:
        report["status"] = "dry_run_mock_only"
        report["note"] = "只跑了 Mock 隔离段；live 段未执行（dry-run）。"
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("== dry-run：未发起任何真实调用")
        return 0

    if not (mcp_url and api_key):
        report["status"] = "not_run"
        report["missing"] = [
            x for x, ok in (("TIANYANCHA_MCP_URL", bool(mcp_url)), ("TIANYANCHA_API_KEY", bool(api_key))) if not ok
        ]
        report["note"] = "缺 key 或 MCP 地址，未发起任何真实调用；本项按「未实证」记录。"
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"== 未实证：缺少 {report['missing']}，未发请求 -> {args.json}")
        return 2

    live_settings = Settings(app_mode=LIVE, tianyancha_mcp_url=mcp_url, tianyancha_api_key=api_key,
                             cache_dir=cache_dir)

    # ---- 第二步：live basic 1 家，且必须不读 mock 缓存 ----
    try:
        t0 = time.perf_counter()
        basic = company_recon(args.company, live_settings, depth="basic")
        basic_seconds = time.perf_counter() - t0
        basic_hard = basic.hard_data.model_dump() if hasattr(basic.hard_data, "model_dump") else {}
        sources = {v.get("source") for v in basic_hard.values() if isinstance(v, dict)}
        bad = [s for s in sources if str(s).startswith("mock://")]
        step(
            "live basic 来源校验",
            not bad and "tianyancha_mcp" in {str(s) for s in sources},
            {
                "cache_hit": basic.cache.hit,
                "data_mode": basic.data_mode,
                "sources": sorted(str(s) for s in sources if s),
                "seconds": round(basic_seconds, 2),
                "quota": basic.quota_consumed.model_dump(),
                "degradations": basic.degradations,
            },
        )
        report["basic"] = basic.model_dump()
    except Exception as exc:
        step("live basic 来源校验", False, {"error": f"{type(exc).__name__}: {exc}"})
        report["basic_error"] = f"{type(exc).__name__}: {exc}"

    # ---- 第三步：deep 预估 → 确认 → 记账 ----
    try:
        est = estimate_deep(args.company, live_settings, resolved_name=args.company)
        est_calls = int(est.estimate.get("calls") or 0)
        step(
            "deep 预估（零调用）",
            est.quota_consumed.tianyancha_calls == 0 and est_calls > 0,
            {"estimated_calls": est_calls, "cost_yuan": est.estimate.get("cost_yuan"),
             "quota_calls": est.quota_consumed.tianyancha_calls},
        )
        t1 = time.perf_counter()
        deep = company_recon(args.company, live_settings, depth="deep", confirmed_deep=True)
        deep_seconds = time.perf_counter() - t1
        detail = deep.quota_consumed.tianyancha_detail
        step(
            "deep 确认后按明细记账",
            len(detail) > 0 and all(d.calls > 0 for d in detail),
            {"seconds": round(deep_seconds, 2), "calls": deep.quota_consumed.tianyancha_calls,
             "cost": round(sum(d.cost for d in detail), 4),
             "detail": [d.model_dump() for d in detail]},
        )
        report["deep"] = deep.model_dump()
    except Exception as exc:
        step("deep 预估（零调用）", False, {"error": f"{type(exc).__name__}: {exc}"})
        report["deep_error"] = f"{type(exc).__name__}: {exc}"

    ok = all(s["ok"] for s in report["steps"])
    report["status"] = "proven" if ok else "failed"
    Path(args.json).parent.mkdir(parents=True, exist_ok=True)
    Path(args.json).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"== status={report['status']} -> {args.json}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
