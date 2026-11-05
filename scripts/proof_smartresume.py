"""SmartResume 真实后端实证：模型哈希已核对后，跑 3 份脱敏简历并与 fallback 对照。

只认三件套：
  1) 可复现命令（本文件 + docs/PROOF.md 里的调用行）
  2) 原始产物（本脚本写出的 JSON：逐份结构化结果、耗时、内存峰值、哈希前置条件）
  3) 结论 + 局限（docs/PROOF.md 的 SmartResume 段）

运行前提：
  - 用装了 smartresume / torch / transformers 的解释器（.tmp/sr-venv）
  - 模型已由 scripts/fetch_smartresume_model.py 下载并核对哈希
本脚本会在临时工作目录写 configs/config.yaml，让上游走 use_direct_models（本地权重、无 API 调用）。

用法：
    .tmp/sr-venv/Scripts/python.exe scripts/proof_smartresume.py \
        --model-dir .tmp/models/llm/Qwen3-0.6B \
        --out docs/proof/smartresume-cpu.json --device cpu
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path

import psutil

PACK = Path(__file__).resolve().parent.parent
SIDECAR = PACK / "starter" / "sidecar"
PDF_DIR = PACK / ".tmp" / "resumes-pdf"
DEFAULT_RESUMES = ["resume-bd.pdf", "resume-da.pdf", "resume-pm.pdf"]
# 上游 0.1.1 的 get_prompts() 只有这三个键；写 projects/skills 会 KeyError，
# 所以实证只请求它真的支持的抽取类型（这一点本身就是实证结论之一）。
EXTRACT_TYPES = ["basic_info", "education", "work_experience"]

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(SIDECAR))


def _rss_mb() -> float:
    return psutil.Process(os.getpid()).memory_info().rss / 2**20


class PeakRSS:
    """后台采样进程 RSS，避免只看结束时刻（模型驻留后不会释放，峰值更有意义）。"""

    def __init__(self, interval: float = 0.2) -> None:
        self.interval = interval
        self.peak = 0.0
        self._stop = threading.Event()
        self._t: threading.Thread | None = None

    def __enter__(self):
        self.peak = _rss_mb()
        self._t = threading.Thread(target=self._run, daemon=True)
        self._t.start()
        return self

    def _run(self) -> None:
        while not self._stop.is_set():
            self.peak = max(self.peak, _rss_mb())
            self._stop.wait(self.interval)

    def __exit__(self, *exc):
        self._stop.set()
        if self._t:
            self._t.join(timeout=2)
        return False


def write_upstream_config(workdir: Path, model_dir: Path, max_tokens: int) -> Path:
    """上游 config 从 CWD 的 configs/config.yaml 读；不走 API，直接加载本地权重。"""
    cfg_dir = workdir / "configs"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    cfg = {
        "model": {
            "name": "qwen3-0.6b-local",
            # api_url/api_key 在 use_direct_models 下不参与推理，但上游 __init__ 仍会构造 OpenAI 客户端，
            # 所以给占位值；真实网络请求不会发生（direct 分支优先命中）。
            "api_url": "http://127.0.0.1:9/v1",
            "api_key": "not-used-direct-model",
            "max_tokens": max_tokens,
            "temperature": 0.0,
            "top_p": 1.0,
            "seed": 0,
        },
        "use_direct_models": True,
        "direct_model_name": str(model_dir),
        "processing": {"use_pdf_raw_text": True, "page_limit": 10, "use_force_json": False},
        "ocr": {"enabled": False, "use_cuda": False},
        "layout_detection": {"enabled": False},
        "model_download": {"source": "modelscope", "models_dir": {"llm": str(model_dir.parent), "layout": ""}},
    }
    p = cfg_dir / "config.yaml"
    p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def collect_text(obj, out: list[str]) -> None:
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            collect_text(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            collect_text(v, out)


def score(doc: dict, gt: dict) -> dict:
    blob: list[str] = []
    collect_text(doc, blob)
    joined = "\n".join(blob)
    must = gt.get("must_contain", [])
    anchors = gt.get("anchors", [])
    hit = [s for s in must if s in joined]
    a_hit = [s for s in anchors if s in joined]
    total = len(must) + len(anchors)
    return {
        "must_contain_total": len(must),
        "must_contain_hit": hit,
        "must_contain_miss": [s for s in must if s not in joined],
        "anchors_total": len(anchors),
        "anchors_hit": a_hit,
        "anchors_miss": [s for s in anchors if s not in joined],
        "recall": round((len(hit) + len(a_hit)) / total, 4) if total else None,
        "experiences": len(doc.get("experiences") or []),
        "projects": len(doc.get("projects") or []),
        "skills": len(doc.get("skills") or []),
        "bullets": sum(len(e.get("bullets") or []) for e in (doc.get("experiences") or [])),
        "metrics": sum(len(e.get("metrics") or []) for e in (doc.get("experiences") or [])),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-dir", required=True)
    ap.add_argument("--out", default="docs/proof/smartresume-cpu.json")
    ap.add_argument("--device", default="cpu", choices=["cpu", "cuda"])
    ap.add_argument("--max-tokens", type=int, default=1024)
    ap.add_argument("--resumes", nargs="*", default=DEFAULT_RESUMES)
    ap.add_argument("--ground-truth", default="docs/proof/smartresume-ground-truth.json")
    args = ap.parse_args()

    model_dir = Path(args.model_dir).resolve()
    if not (model_dir / "model.safetensors").exists():
        print(f"模型不完整：{model_dir} 缺少 model.safetensors，先跑 scripts/fetch_smartresume_model.py")
        return 2

    if args.device == "cuda":
        os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")

    workdir = PACK / ".tmp" / f"sr-run-{args.device}"
    workdir.mkdir(parents=True, exist_ok=True)
    cfg_path = write_upstream_config(workdir, model_dir, args.max_tokens)
    os.chdir(workdir)  # 上游 config 按相对路径读 configs/config.yaml
    print(f"== 工作目录 {workdir}\n== 上游配置 {cfg_path}")

    gt_all = {}
    gt_path = PACK / args.ground_truth
    if gt_path.exists():
        gt_all = json.loads(gt_path.read_text(encoding="utf-8"))

    # 延迟导入：必须在 chdir 与 config 落盘之后，上游 import 时就会读 config
    from app.config import LIVE, Settings  # noqa: E402
    from app.parsers.resume import FallbackResumeParser, SmartResumeBackend, extract_text, parse_resume  # noqa: E402

    import torch  # noqa: E402

    settings = Settings(app_mode=LIVE)
    backend = SmartResumeBackend(settings)
    reason = backend.unavailable_reason()
    print(f"== SmartResume 可用性：{'可用' if backend.available() else '不可用：' + reason}")

    env = {
        "python": sys.version.split()[0],
        "torch": torch.__version__,
        "cuda_available": bool(torch.cuda.is_available()),
        "device": args.device,
        "max_tokens": args.max_tokens,
        "extract_types": EXTRACT_TYPES,
        "model_dir": str(model_dir),
        "cpu": (psutil.cpu_count(logical=True),),
        "ram_gb": round(psutil.virtual_memory().total / 2**30, 1),
    }
    if torch.cuda.is_available():
        env["gpu"] = torch.cuda.get_device_name(0)

    records = []
    for name in args.resumes:
        path = (PDF_DIR / name) if name.lower().endswith(".pdf") else (PACK / "templates" / "samples" / name)
        if not path.exists():
            print(f"跳过（不存在）：{path}")
            continue
        print(f"\n== {name}")
        rid = path.stem
        gt_key = name.replace(".pdf", ".txt")

        # 1) 真实后端
        t0 = time.perf_counter()
        err = ""
        data = None
        with PeakRSS() as peak:
            try:
                model = parse_resume(path, settings, resume_id=rid, extract_types=EXTRACT_TYPES)
                data = model.model_dump()
            except Exception:
                err = traceback.format_exc(limit=6)
        sr_seconds = time.perf_counter() - t0
        sr_peak = peak.peak
        sr_after = _rss_mb()

        # 2) fallback 对照（同一份文本，规则解析）
        t1 = time.perf_counter()
        extraction = extract_text(path)
        if not extraction.text.strip():
            # 对照组的文本提取为空时，recall=0 是环境缺陷不是解析效果，必须显式标出来，
            # 否则会得出"模型比规则强"的假结论。
            print("   !! fallback 对照无效：本地文本提取为空（检查 pypdf/python-docx 是否安装）")
        fb = FallbackResumeParser().parse(extraction, rid)
        fb_seconds = time.perf_counter() - t1
        fb_valid = bool(extraction.text.strip())

        rec = {
            "resume": name,
            "resume_id": rid,
            "smartresume": {
                "parsing_mode": (data or {}).get("parsing_mode"),
                "seconds": round(sr_seconds, 2),
                "peak_rss_mb": round(sr_peak, 1),
                "rss_after_mb": round(sr_after, 1),
                "error": err.splitlines()[-1] if err else "",
                "error_detail": err,
                "score": score(data, gt_all.get(gt_key, {})) if data else None,
                "notes": (data or {}).get("parsing_notes"),
            },
            "fallback": {
                "parsing_mode": fb.get("parsing_mode"),
                "seconds": round(fb_seconds, 3),
                "valid_comparison": fb_valid,
                "score": score(fb, gt_all.get(gt_key, {})),
            },
            "output": data,
            "output_fallback": fb,
        }
        records.append(rec)
        print(f"   smartresume: mode={rec['smartresume']['parsing_mode']} "
              f"{rec['smartresume']['seconds']}s peak={rec['smartresume']['peak_rss_mb']}MB "
              f"recall={(rec['smartresume']['score'] or {}).get('recall')}")
        if err:
            print(f"   !! 异常：{rec['smartresume']['error']}")
        print(f"   fallback:    {rec['fallback']['seconds']}s recall={rec['fallback']['score']['recall']}")

    summary = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "env": env,
        "model": {
            "dir": str(model_dir),
            "safetensors_bytes": (model_dir / "model.safetensors").stat().st_size,
        },
        "upstream_config": json.loads(cfg_path.read_text(encoding="utf-8")),
        "records": records,
        "mode_counts": {
            m: sum(1 for r in records if r["smartresume"]["parsing_mode"] == m)
            for m in {r["smartresume"]["parsing_mode"] for r in records}
        },
        "avg_smartresume_seconds": round(
            sum(r["smartresume"]["seconds"] for r in records) / len(records), 2
        ) if records else None,
        "max_peak_rss_mb": max((r["smartresume"]["peak_rss_mb"] for r in records), default=None),
    }
    out = PACK / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n== 产物：{out}")
    # 只看 parsing_mode 会被"空壳 smartresume"骗过（上游模型没加载也会返回合法空结构），
    # 所以必须同时要求真的抽到东西：经历数 > 0 且关键实体召回 > 0。
    def _real(r: dict) -> bool:
        s = r["smartresume"]
        sc = s.get("score") or {}
        return (
            s["parsing_mode"] == "smartresume"
            and (sc.get("experiences") or 0) > 0
            and (sc.get("recall") or 0) > 0
        )

    ok = bool(records) and all(_real(r) for r in records)
    if ok:
        print(f"== 结论：{len(records)} 份全部 parsing_mode=smartresume 且非空壳")
    else:
        print("== 结论：存在降级/空壳/异常，见产物")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
