"""CI 构建证据包校验：只有证据齐全且内容自洽，才允许判定「已构建」。

为什么需要这个脚本：
- 本机没有 docker，Docker 的「已证」只能来自 CI；
- CI 日志/产物一旦下载到本地，就可能被空文件、手改文本冒充；
- 所以这里做机械校验：五件套齐全 + 镜像 ID 形态合法 + 构建日志有成功标记 +
  /health 真返回 200 + 容器日志有 uvicorn 启动 + 容器内 verify 以 `verify passed` 收尾。

用法：
    python3 scripts/check_ci_evidence.py --dir .tmp/docker-evidence
    python3 scripts/check_ci_evidence.py --dir .tmp/docker-evidence --json .tmp/ci-evidence.json

退出码：0 = 证据通过（certified）；2 = 证据不足（未实证）；1 = 证据存在但互相矛盾。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

REQUIRED = {
    "build.log": "docker build 原始输出",
    "image-id.txt": "镜像 ID（docker image inspect --format '{{.Id}}'）",
    "container.log": "docker logs 原始输出",
    "health.json": "/health 响应体",
    "health-status.txt": "/health 的 HTTP 状态码",
    "verify.log": "容器内 scripts/verify.sh 输出",
}

IMAGE_ID_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
BUILD_OK_MARKERS = ("Successfully tagged", "writing image sha256:", "naming to", "DONE ")
VERIFY_OK = "== verify passed"
UVICORN_MARKERS = ("Uvicorn running", "Application startup complete")


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def sha256_of(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def check(dirpath: Path) -> dict:
    """返回 {status, ok, checks[], evidence{path,sha256,bytes}}。"""
    results: list[dict] = []
    evidence: dict[str, dict] = {}

    def add(cid: str, ok: bool, desc: str, detail: str = "") -> None:
        results.append({"id": cid, "ok": bool(ok), "desc": desc, "detail": detail})

    if not dirpath.is_dir():
        return {
            "status": "missing",
            "ok": False,
            "checks": [{"id": "E0", "ok": False, "desc": "证据目录存在", "detail": str(dirpath)}],
            "evidence": {},
        }

    for name, desc in REQUIRED.items():
        f = dirpath / name
        exists = f.is_file() and f.stat().st_size > 0
        add(f"E-{name}", exists, f"{desc} 存在且非空", "" if exists else "缺失或 0 字节")
        if exists:
            evidence[name] = {
                "path": str(f),
                "bytes": f.stat().st_size,
                "sha256": sha256_of(f),
            }

    if not all(r["ok"] for r in results):
        return {"status": "incomplete", "ok": False, "checks": results, "evidence": evidence}

    image_id = _read(dirpath / "image-id.txt").strip().splitlines()
    first = image_id[0].strip() if image_id else ""
    add("E1", bool(IMAGE_ID_RE.match(first)), "镜像 ID 形态合法（sha256:64 hex）", first[:24] + "…")

    build = _read(dirpath / "build.log")
    add(
        "E2",
        any(m in build for m in BUILD_OK_MARKERS),
        "构建日志含成功标记",
        next((m for m in BUILD_OK_MARKERS if m in build), "未找到任何成功标记"),
    )
    # 只认真正的失败行：buildkit 的 `#12 ERROR: ...` 或传统输出的 `ERROR: ...`
    fail_lines = [ln for ln in build.splitlines() if re.match(r"^\s*(#\d+\s+)?ERROR[:\s]", ln)]
    add("E3", not fail_lines, "构建日志无 ERROR 行", fail_lines[0][:120] if fail_lines else "")

    status = _read(dirpath / "health-status.txt").strip()
    add("E4", status == "200", "/health 返回 HTTP 200", f"实际 {status or '空'}")

    health = _read(dirpath / "health.json").strip()
    ok_json = False
    try:
        payload = json.loads(health)
        ok_json = isinstance(payload, dict) and bool(payload)
    except Exception:
        ok_json = False
    add("E5", ok_json, "health.json 是可解析的 JSON 对象", health[:80])

    container = _read(dirpath / "container.log")
    add(
        "E6",
        any(m in container for m in UVICORN_MARKERS),
        "容器日志含 uvicorn 启动标记",
        next((m for m in UVICORN_MARKERS if m in container), "未找到启动标记"),
    )

    verify = _read(dirpath / "verify.log")
    add("E7", VERIFY_OK in verify, "容器内 verify.sh 以 `== verify passed` 收尾", "")

    ok = all(r["ok"] for r in results)
    return {
        "status": "certified" if ok else "contradictory",
        "ok": ok,
        "checks": results,
        "evidence": evidence,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=".tmp/docker-evidence", help="CI artifact 解压目录")
    ap.add_argument("--json", default=".tmp/ci-evidence.json")
    args = ap.parse_args()

    rep = check(Path(args.dir))
    print(f"== CI 证据包：{args.dir}")
    for c in rep["checks"]:
        print(f"  {'ok' if c['ok'] else 'NG'} {c['id']} {c['desc']}" + (f" -> {c['detail']}" if c["detail"] else ""))
    print(f"== status: {rep['status']}")

    out = Path(args.json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")

    if rep["status"] == "certified":
        return 0
    if rep["status"] == "missing":
        return 2
    return 2 if rep["status"] == "incomplete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
