#!/usr/bin/env bash
# 包自检：不启动任何外部服务，不需要真实 key。
# 通过 = 包内文件齐全 + 模板 JSON 合法 + 校验器自检通过 + 契约脚本通过 + Mock 端到端演示通过
#        + （依赖已安装时）Python 测试与插件测试全绿。
#
# 路径说明：Git Bash / MSYS 下 `pwd` 返回 /c/Users/... 形式，原生 Windows Python 无法解析，
# 因此当 cygpath 可用时统一转成 Windows 路径再传给 Python 解释器；
# 但 `cd` 必须用 POSIX 路径，否则 Windows 反斜杠路径在 bash 里进不去。
set -euo pipefail
PACK_POSIX="$(cd "$(dirname "$0")/.." && pwd)"
PACK_DIR="$PACK_POSIX"
if command -v cygpath >/dev/null 2>&1; then
  PACK_DIR="$(cygpath -w "$PACK_POSIX")"
fi
echo "== pack: $PACK_DIR"
mkdir -p "$PACK_POSIX/.tmp"

# 1. 必备文件齐全
for f in 00_START_HERE.md AGENTS.md README.md 01_PRD.md 02_ARCHITECTURE.md 03_DATA_CONTRACTS.md 04_REPORT_SPEC.md 05_COMPANY_RECON_SPEC.md 06_EVIDENCE_QUALITY.md 07_TASK_PLAN.md 08_ENVIRONMENT.md 09_TESTING_ACCEPTANCE.md 10_AGENT_WORKFLOW.md 11_RISKS_GUARDRAILS.md 12_FORK_MAP.md PROGRESS.md docs/FORK_LOCK.md docs/PROOF.md docs/PERFORMANCE.md docs/REVIEW_T3.4.md docs/ACCEPTANCE_REPORT.md docs/ENV_FEASIBILITY.md docs/HUMAN_REVIEW_PACK.md docs/review-pack/golden_06_bd_strong.md docs/review-pack/golden_07_gap.md docs/proof/model-manifest.json docs/proof/smartresume-cpu.json docs/proof/tianyancha-live.json docs/proof/tyc-mock-isolation.json docs/proof/docker-static.json docs/proof/live-perf-preflight.log templates/report-template.md templates/golden/golden_01_bd.json templates/golden/golden_05_ka.json templates/golden/golden_06_bd_strong.json templates/golden/golden_07_gap.json templates/samples/jd-bd-campus.txt templates/samples/jd-backend.txt scripts/check_docker_assets.py scripts/check_ci_evidence.py scripts/check_proof.py scripts/export_review_pack.py scripts/proof_smartresume.py scripts/proof_tianyancha.py scripts/fetch_smartresume_model.py scripts/make_sample_pdfs.py .github/workflows/docker-build.yml starter/sidecar/app/version.py starter/sidecar/tests/test_cache_versioning.py starter/sidecar/tests/test_regression_harness.py starter/sidecar/tests/test_cost_cap.py templates/golden-case-template.json templates/company-disambiguation-template.json starter/dsh-plugin/src/tools.ts starter/dsh-plugin/src/skill/job-fit-orchestrator.md starter/dsh-plugin/package.json starter/sidecar/app/main.py starter/sidecar/app/validator.py starter/sidecar/requirements.txt starter/sidecar/Dockerfile starter/docker-compose.yml starter/.env.example; do
  test -f "$PACK_DIR/$f" || { echo "MISSING: $f"; exit 1; }
done
echo "== files ok"

# 2. JSON 模板合法
python3 -c "import json,sys; [json.load(open(p, encoding='utf-8')) for p in sys.argv[1:]]; print('== json ok')" \
  "$PACK_DIR/templates/golden-case-template.json" \
  "$PACK_DIR/templates/company-disambiguation-template.json" \
  "$PACK_DIR/starter/dsh-plugin/package.json"

# 3. 校验器自检 + 契约校验 + Mock 端到端演示（三组职业方向）
python3 "$PACK_DIR/starter/sidecar/app/validator.py"
python3 "$PACK_DIR/scripts/validate_contracts.py"
python3 "$PACK_DIR/scripts/run_mock_demo.py" --all --out-dir "$PACK_DIR/.tmp/demo"

# 3.5 golden set 回归（A5）：通过率 < 80% 直接判失败，不许"看一眼差不多就行"
#     同时强制三档覆盖（strong / discussable / gap），少一档也算失败
python3 "$PACK_DIR/scripts/run_golden_regression.py" --json "$PACK_DIR/.tmp/golden-report.json" | tail -4

# 3.6 Docker 资产：本机没有 docker 时只做静态校验，结论里必须写明"未构建"
python3 "$PACK_DIR/scripts/check_docker_assets.py" --json "$PACK_DIR/.tmp/docker-check.json" | tail -3

# 3.7 复核包守门：复核包必须是空白清单，不许 AI 代填"已人工通过"
grep -q "AI 没有、也不能代替真人" "$PACK_DIR/docs/HUMAN_REVIEW_PACK.md" \
  || { echo "复核包缺少『AI 不代评』声明"; exit 1; }
echo "== review pack ok（人工判定位仍为空白）"

# 3.8 缓存版本号可查（旧缓存靠它失效）
python3 -c "import sys; sys.path.insert(0, sys.argv[1]); from app.version import cache_version; print('== cache version:', cache_version())" \
  "$PACK_DIR/starter/sidecar"

# 3.9 外部依赖实证守门：证据缺件 / 状态词含糊 / 未实证却说已完成，一律失败
python3 "$PACK_DIR/scripts/check_proof.py"

# 4. 测试套件：依赖装了就必须绿；没装就明说跳过，不假装通过
if python3 -c "import pytest" >/dev/null 2>&1; then
  ( cd "$PACK_POSIX/starter/sidecar" && python3 -m pytest tests/ -q ) >"$PACK_POSIX/.tmp/pytest.log" 2>&1 || {
    echo "== pytest FAILED"; tail -25 "$PACK_POSIX/.tmp/pytest.log"; exit 1;
  }
  echo "== pytest ok ($(grep -oE '[0-9]+ passed' "$PACK_POSIX/.tmp/pytest.log" | tail -1))"
else
  echo "== pytest skipped（未安装，见 starter/sidecar/requirements-dev.txt）"
fi

if command -v npm >/dev/null 2>&1 && [ -d "$PACK_POSIX/starter/dsh-plugin/node_modules" ]; then
  ( cd "$PACK_POSIX/starter/dsh-plugin" && npm run --silent check && npm test --silent ) \
    >"$PACK_POSIX/.tmp/npm-test.log" 2>&1 || {
    echo "== plugin check/test FAILED"; tail -30 "$PACK_POSIX/.tmp/npm-test.log"; exit 1;
  }
  echo "== plugin check+test ok ($(grep -oE '# pass [0-9]+' "$PACK_POSIX/.tmp/npm-test.log" | tail -1))"
else
  echo "== plugin check/test skipped（未执行 npm install）"
fi

echo "== verify passed"
