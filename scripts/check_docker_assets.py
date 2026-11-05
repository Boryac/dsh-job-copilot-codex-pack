"""Docker 资产可行性检查（只做可行性结论，不虚报"已构建"）。

规则（用户明确要求）：
- 本机有 docker：跑一次真实 `docker build`，构建结果照实记录；
- 本机没有 docker：**只**校验 Dockerfile / compose / CI 工作流的静态约束，输出必须写明"未构建"；
- 只有在提供 CI 证据包（`--ci-evidence`）且通过 `check_ci_evidence.py` 机械校验时，
  status 才允许是 `built`，且 `built_source` 标为 `ci`。

用法：
    python3 scripts/check_docker_assets.py
    python3 scripts/check_docker_assets.py --json .tmp/docker-check.json
    python3 scripts/check_docker_assets.py --ci-evidence .tmp/docker-evidence
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

PACK = Path(__file__).resolve().parent.parent
SIDECAR = PACK / "starter" / "sidecar"
DOCKERFILE = SIDECAR / "Dockerfile"
COMPOSE = PACK / "starter" / "docker-compose.yml"
DOCKERIGNORE = SIDECAR / ".dockerignore"
CI_WORKFLOW = PACK / ".github" / "workflows" / "docker-build.yml"
SIDECAR_PORT = 8000

SECRET_RE = re.compile(r"(sk-[A-Za-z0-9]{16,}|AKIA[0-9A-Z]{12,}|ghp_[A-Za-z0-9]{20,})")


def docker_available() -> tuple[bool, str]:
    exe = shutil.which("docker")
    if not exe:
        return False, "PATH 中找不到 docker 可执行文件"
    try:
        out = subprocess.run(
            [exe, "--version"], capture_output=True, text=True, timeout=20, check=False
        )
    except Exception as exc:  # 装了但跑不起来，等同于不可用
        return False, f"docker 无法执行：{type(exc).__name__}"
    if out.returncode != 0:
        return False, (out.stderr or out.stdout).strip()[:200]
    return True, (out.stdout or "").strip()


def _check(checks: list[dict], cid: str, ok: bool, desc: str, detail: str = "") -> None:
    checks.append({"id": cid, "ok": bool(ok), "desc": desc, "detail": detail})


def static_checks() -> list[dict]:
    checks: list[dict] = []
    _check(checks, "D1", DOCKERFILE.exists(), "Dockerfile 存在", str(DOCKERFILE))
    if not DOCKERFILE.exists():
        return checks

    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    compose = COMPOSE.read_text(encoding="utf-8") if COMPOSE.exists() else ""

    from_line = next((ln.strip() for ln in dockerfile.splitlines() if ln.strip().upper().startswith("FROM ")), "")
    base = from_line.split()[1] if len(from_line.split()) > 1 else ""
    _check(checks, "D2", bool(base) and ":latest" not in base, "基础镜像固定版本、不用 latest", base or "未找到 FROM")

    _check(checks, "D3", "requirements.txt" in dockerfile, "安装 dependencies 用 requirements.txt", "")
    req_pos = dockerfile.find("COPY requirements.txt")
    app_pos = dockerfile.find("COPY app")
    _check(
        checks,
        "D4",
        req_pos != -1 and app_pos != -1 and req_pos < app_pos,
        "先拷依赖再拷代码（利用层缓存）",
        f"requirements@{req_pos} app@{app_pos}",
    )
    _check(checks, "D5", bool(re.search(r"^USER\s+\S+", dockerfile, re.M)), "非 root 运行", "")

    expose = re.search(r"^EXPOSE\s+(\d+)", dockerfile, re.M)
    _check(
        checks,
        "D6",
        bool(expose) and int(expose.group(1)) == SIDECAR_PORT,
        f"EXPOSE 与 sidecar 端口一致（{SIDECAR_PORT}）",
        expose.group(0) if expose else "未声明 EXPOSE",
    )
    _check(checks, "D7", "HEALTHCHECK" in dockerfile, "声明 HEALTHCHECK（/health 可探活）", "")
    _check(
        checks,
        "D8",
        "COPY .env" not in dockerfile and ".env" not in dockerfile,
        "镜像内不拷贝 .env（避免把密钥烤进镜像）",
        "",
    )
    _check(
        checks,
        "D9",
        not SECRET_RE.search(dockerfile),
        "Dockerfile 里没有硬编码密钥",
        "",
    )

    _check(checks, "C1", COMPOSE.exists(), "docker-compose.yml 存在", str(COMPOSE))
    _check(
        checks,
        "C2",
        "context: ./sidecar" in compose and "dockerfile: Dockerfile" in compose,
        "compose 的 build context / dockerfile 指向真实路径",
        "",
    )
    _check(
        checks,
        "C3",
        (SIDECAR / "Dockerfile").exists()
        and "context: ./sidecar" in compose
        and (PACK / "starter" / "sidecar").is_dir(),
        "compose 引用的 context 目录存在（静态存在性，非构建验证）",
        "",
    )
    _check(
        checks,
        "C4",
        f"${{SIDECAR_PORT:-{SIDECAR_PORT}}}:{SIDECAR_PORT}" in compose,
        "端口映射可用环境变量覆盖且容器端口一致",
        "",
    )
    _check(
        checks,
        "C5",
        not SECRET_RE.search(compose),
        "compose 里没有硬编码密钥（密钥只来自 env_file/环境变量）",
        "",
    )

    ignore = DOCKERIGNORE.read_text(encoding="utf-8") if DOCKERIGNORE.exists() else ""
    _check(checks, "I1", ".cache" in ignore, ".dockerignore 排除 .cache", "")
    _check(checks, "I2", ".env" in ignore, ".dockerignore 排除 .env", "")
    _check(checks, "I3", (SIDECAR / "requirements.txt").exists(), "requirements.txt 存在", "")
    checks.extend(ci_workflow_checks())
    return checks


def ci_workflow_checks() -> list[dict]:
    """CI 工作流的静态校验：语法可解析 + 关键步骤齐全。

    这只是"工作流写得对"，不等于"工作流跑过"。构建结论必须由 artifact 证据支撑。
    """
    checks: list[dict] = []
    _check(checks, "W1", CI_WORKFLOW.exists(), "CI 工作流存在", str(CI_WORKFLOW))
    if not CI_WORKFLOW.exists():
        return checks

    raw = CI_WORKFLOW.read_text(encoding="utf-8")
    parsed = None
    try:
        import yaml  # 本地有则用；没有就退化为文本检查

        parsed = yaml.safe_load(raw)
    except Exception as exc:  # pragma: no cover - 环境相关
        _check(checks, "W2", False, "CI 工作流 YAML 可解析", f"未校验：{type(exc).__name__}")
        return checks

    ok_yaml = isinstance(parsed, dict) and isinstance(parsed.get("jobs"), dict) and bool(parsed["jobs"])
    _check(checks, "W2", ok_yaml, "CI 工作流 YAML 可解析且含 jobs", f"jobs={list(parsed.get('jobs', {})) if isinstance(parsed, dict) else '?'}")

    # 把 steps 里的 run/uses 全拼起来做关键词检查，避免嵌套结构写错导致漏判
    steps_text: list[str] = []
    for job in (parsed.get("jobs") or {}).values():
        for step in (job or {}).get("steps") or []:
            steps_text.append(json.dumps(step, ensure_ascii=False))
    joined = "\n".join(steps_text)

    _check(checks, "W3", "docker build" in joined, "工作流里真的执行 docker build", "")
    _check(checks, "W4", "docker run" in joined, "工作流里真的执行 docker run", "")
    _check(
        checks,
        "W5",
        "/health" in joined and "200" in joined,
        "工作流探活 /health 且校验 200",
        "",
    )
    _check(checks, "W6", "verify.sh" in joined, "工作流在容器内跑 verify.sh", "")
    _check(checks, "W7", "upload-artifact" in joined, "构建证据以 artifact 形式留存", "")
    _check(
        checks,
        "W8",
        "docker image inspect" in joined and "{{.Id}}" in joined,
        "工作流记录镜像 ID",
        "",
    )
    return checks



def try_build() -> dict:
    """有 docker 才跑；没有就返回未构建 + 原因，绝不写"已构建"。"""
    ok, version = docker_available()
    if not ok:
        return {"attempted": False, "built": False, "reason": version}
    image = "dsh-job-copilot-sidecar:verify"
    try:
        proc = subprocess.run(
            ["docker", "build", "-t", image, str(SIDECAR)],
            capture_output=True,
            text=True,
            timeout=900,
            check=False,
        )
    except Exception as exc:
        return {"attempted": True, "built": False, "reason": f"{type(exc).__name__}: {exc}"}
    return {
        "attempted": True,
        "built": proc.returncode == 0,
        "image": image,
        "reason": (proc.stderr or proc.stdout).strip()[-400:],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=str(PACK / ".tmp" / "docker-check.json"))
    ap.add_argument(
        "--ci-evidence",
        default="",
        help="CI artifact 解压目录；提供且校验通过才允许 status=built（built_source=ci）",
    )
    args = ap.parse_args()

    ok, version = docker_available()
    checks = static_checks()
    build = try_build() if ok else {"attempted": False, "built": False, "reason": version}
    static_ok = all(c["ok"] for c in checks)

    ci = {"status": "not_provided", "ok": False, "checks": [], "evidence": {}}
    if args.ci_evidence:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from check_ci_evidence import check as check_ci  # 本地脚本，非第三方

        ci = check_ci(Path(args.ci_evidence))

    print("== Docker 资产检查（只做可行性结论）")
    print(f"docker 可用：{'是' if ok else '否'} — {version}")
    for c in checks:
        print(f"  {'ok' if c['ok'] else 'NG'} {c['id']} {c['desc']}" + (f" -> {c['detail']}" if c["detail"] else ""))
    if build["attempted"]:
        print(f"本机构建：{'成功' if build['built'] else '失败'} — {build['reason'][:200]}")
    else:
        print(f"本机构建：未执行（{build['reason']}）—— 静态校验不等于构建通过")

    if args.ci_evidence:
        print(f"CI 证据包：{ci['status']}（{args.ci_evidence}）")
        for c in ci["checks"]:
            print(f"  {'ok' if c['ok'] else 'NG'} {c['id']} {c['desc']}")
    else:
        print("CI 证据包：未提供 —— 未实证")

    built = bool(build.get("built")) or ci.get("status") == "certified"
    source = "local" if build.get("built") else ("ci" if ci.get("status") == "certified" else "")
    if built:
        print(f"镜像构建：已证（来源 {source}）")
    else:
        print("镜像构建：未实证（缺镜像 ID / 构建日志 / 容器日志三件套）—— 不许写成『已构建』")

    report = {
        "docker_available": ok,
        "docker_version": version,
        "static_checks": checks,
        "static_ok": static_ok,
        "build": build,
        "ci_evidence": ci,
        "status": "built" if built else ("static_only" if static_ok else "failed"),
        "built_source": source,
        "note": (
            "status=built 只在两种情况成立：本机 docker build 成功，或 CI 证据包通过 "
            "scripts/check_ci_evidence.py 机械校验。静态校验通过一律记为 static_only。"
        ),
    }
    out = Path(args.json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"明细 -> {out}")
    return 0 if static_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
