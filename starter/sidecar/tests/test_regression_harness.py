"""回归 harness 自身的反向验证（v1 补缺口）。

不会失败的回归测试等于没有。这组用例专门证明：档位写错、题量要求过高、
禁用词命中、伪造 evidence_ref、三档覆盖缺失，harness 都必须判失败。
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.config import Settings
from app.orchestrator.service import run_analysis

PACK = Path(__file__).resolve().parents[3]
GOLDEN_DIR = PACK / "templates" / "golden"
SAMPLES = PACK / "templates" / "samples"


def _harness():
    spec = importlib.util.spec_from_file_location(
        "golden_regression", PACK / "scripts" / "run_golden_regression.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def bd_result(tmp_path_factory):
    settings = Settings(app_mode="mock", cache_dir=tmp_path_factory.mktemp("cache"))
    return run_analysis(
        SAMPLES / "resume-bd.txt",
        (SAMPLES / "jd-bd.txt").read_text(encoding="utf-8"),
        "云栖生活",
        settings,
    )


# ------------------------------------------------------------ 检查器必须能报错
def test_tier_check_fails_on_wrong_tier(bd_result):
    h = _harness()
    ok, detail = h._run_check({"type": "tier_equals", "value": "strong"}, bd_result)
    assert ok is False, f"档位写错也判通过，检查器空转：{detail}"
    assert "strong" in detail and "discussable" in detail


def test_tier_check_passes_on_actual_tier(bd_result):
    h = _harness()
    ok, _ = h._run_check({"type": "tier_equals", "value": bd_result.structured.verdict.tier}, bd_result)
    assert ok is True


def test_min_questions_fails_when_threshold_too_high(bd_result):
    h = _harness()
    ok, detail = h._run_check({"type": "min_questions", "value": 99}, bd_result)
    assert ok is False and "99" in detail


def test_forbidden_phrase_is_detected(bd_result):
    h = _harness()
    ok, detail = h._run_check({"type": "report_not_contains", "values": ["第 0 节"]}, bd_result)
    assert ok is False and "第 0 节" in detail


def test_questions_not_contain_detects_hallucinated_scope(bd_result):
    h = _harness()
    ok, _ = h._run_check({"type": "questions_not_contain", "values": ["这句话不可能出现在题面里"]}, bd_result)
    assert ok is True
    ok, detail = h._run_check({"type": "questions_not_contain", "values": ["实习"]}, bd_result)
    assert ok is False, "题面里明明有『实习』，禁用词检查却没命中"


# ------------------------------------------------------------ 严重失败一票否决
def test_severe_failure_detects_fabricated_evidence_ref(bd_result):
    h = _harness()
    report = bd_result.structured.model_copy(deep=True)
    report.interview_questions[0].evidence_ref = "exp_99"
    shim = SimpleNamespace(
        structured=report,
        markdown=bd_result.markdown,
        company=bd_result.company,
        jd=bd_result.jd,
    )
    problems = h._severe_failures(shim, bd_result.resume)
    assert any("证据造假" in p for p in problems), problems


def test_severe_failure_flag_makes_case_fail(bd_result):
    """只要出现严重失败，即使所有要点都命中，该组也不许判通过。"""
    h = _harness()
    outcome = h.CaseResult("demo", "demo", "discussable")
    outcome.checks = [{"id": "P1", "desc": "都过", "kind": "must", "ok": True, "detail": ""}]
    assert outcome.passed is True
    outcome.severe = ["题目 q_01 的 evidence_ref=exp_99 不存在（证据造假）"]
    assert outcome.passed is False


# ------------------------------------------------------------ 三档覆盖是硬要求
def test_required_tiers_are_all_three():
    h = _harness()
    assert h.TIER_COVERAGE_REQUIRED == {"strong", "discussable", "gap"}


def test_golden_set_actually_covers_three_tiers():
    tiers = {
        json.loads(path.read_text(encoding="utf-8"))["expected_tier"]
        for path in GOLDEN_DIR.glob("*.json")
    }
    assert tiers == {"strong", "discussable", "gap"}, tiers


def test_every_golden_case_declares_tier_reason():
    for path in GOLDEN_DIR.glob("*.json"):
        case = json.loads(path.read_text(encoding="utf-8"))
        assert case.get("expected_tier") in {"strong", "discussable", "gap"}, path.name
        assert len(case.get("expected_tier_reason", "")) >= 20, path.name
        check_types = {p["check"]["type"] for p in case["expected_points"] + case.get("forbidden", [])}
        assert "tier_equals" in check_types, f"{path.name} 没有把档位写成可执行断言"
