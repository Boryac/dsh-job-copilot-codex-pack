"""下载 SmartResume 用的 Qwen3-0.6B 权重并核对哈希。

做法：
1. 先问 ModelScope 的文件接口要远端清单（每个文件带 Sha256），只留 Qwen3-0.6B/*；
2. 用 modelscope.snapshot_download 下载到本地目录；
3. 对本地文件逐个算 sha256，与远端逐字节比 Size、逐文件比 Sha256；
4. 任何一条不一致即返回非 0，输出 manifest 记下 revision 与哈希。

用法（需要装了 modelscope 的解释器）：
    .tmp/sr-venv/Scripts/python.exe scripts/fetch_smartresume_model.py \
        --dest .tmp/models/llm --json docs/proof/model-manifest.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.request
from pathlib import Path

REPO = "Alibaba-EI/SmartResume"
SUBDIR = "Qwen3-0.6B"
API = f"https://www.modelscope.cn/api/v1/models/{REPO}/repo/files?Revision=master&Root={SUBDIR}"


def remote_listing() -> tuple[list[dict], str]:
    with urllib.request.urlopen(API, timeout=60) as resp:
        payload = json.load(resp)
    data = payload.get("Data") or {}
    files = data.get("Files") or []
    revision = data.get("Revision") or (files[0].get("Revision") if files else "")
    keep = []
    for f in files:
        p = f.get("Path", "")
        if f.get("Type") != "blob":
            continue
        if not p.startswith(SUBDIR + "/"):
            continue
        keep.append({"path": p, "size": f.get("Size"), "sha256": (f.get("Sha256") or "").lower()})
    return keep, revision


def sha256_local(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest", default=".tmp/models/llm")
    ap.add_argument("--json", default="docs/proof/model-manifest.json")
    args = ap.parse_args()

    dest = Path(args.dest).resolve()
    dest.mkdir(parents=True, exist_ok=True)

    print(f"== 远端清单：{REPO} / {SUBDIR}")
    remote, revision = remote_listing()
    print(f"   revision={revision}  files={len(remote)}  total={sum(f['size'] or 0 for f in remote)/2**20:.1f} MiB")
    for f in remote:
        print(f"   {f['path']}  {f['size']}  {f['sha256'][:16]}…")

    from modelscope import snapshot_download

    t0 = time.time()
    local_dir = snapshot_download(
        REPO,
        allow_patterns=[f"{SUBDIR}/*"],
        local_dir=str(dest),
    )
    elapsed = time.time() - t0
    print(f"== 下载完成：{local_dir}（{elapsed:.1f}s）")

    results = []
    all_ok = True
    for f in remote:
        local = dest / f["path"]
        if not local.exists():
            results.append({"path": f["path"], "ok": False, "reason": "本地缺失"})
            all_ok = False
            continue
        size = local.stat().st_size
        digest = sha256_local(local)
        size_ok = size == f["size"]
        hash_ok = (not f["sha256"]) or digest == f["sha256"]
        ok = size_ok and hash_ok
        all_ok = all_ok and ok
        print(f"   {'ok ' if ok else 'NG '} {f['path']}  size={size}  sha256={digest[:16]}…")
        results.append(
            {
                "path": f["path"],
                "bytes": size,
                "sha256_local": digest,
                "sha256_remote": f["sha256"],
                "size_match": size_ok,
                "hash_match": hash_ok,
                "ok": ok,
            }
        )

    manifest = {
        "repo": REPO,
        "subdir": SUBDIR,
        "revision": revision,
        "downloaded_to": str(dest),
        "download_seconds": round(elapsed, 1),
        "total_bytes": sum(r.get("bytes", 0) for r in results),
        "all_ok": all_ok,
        "files": results,
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    out = Path(args.json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"== 哈希核对：{'全部一致' if all_ok else '存在不一致'} -> {out}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
