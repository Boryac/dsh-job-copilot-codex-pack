"""契约校验（T1.6）：不依赖 pytest，直接对**真实产物**做校验。

分两层：
1. 模板层：`templates/` 下的 golden / 消歧 / 报告模板结构自洽。
2. 产物层：跑三组 Mock 端到端，把 `ReportStructured` 拿回来重新 `model_validate`，
   再逐条核对 ID 体系（exp_/jd_/q_/k_）、引用存在性、四维齐全、9 节齐全、卡片字段完整。

为什么产物层要重校验一遍：Pydantic 校验发生在构造时，如果哪天有人为了"跑通"把
字段放宽成 `Any`，构造能过、下游渲染就崩。这里用同一份模型再校验 + 独立断言引用关系，
把"契约有没有真的被遵守"钉死。verify.sh 的第 3 步就是它。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

PACK = Path(__file__).resolve().parent.parent
SIDECAR = PACK / "starter" / "sidecar"
sys.path.insert(0, str(SIDECAR))

from app.config import load_settings  # noqa: E402
from app.orchestrator.report import REQUIRED_SECTIONS  # noqa: E402
from app.orchestrator.service import run_analysis  # noqa: E402
from app.recon.service import estimate_deep  # noqa: E402
from app.schemas import ReportStructured  # noqa: E402

SAMPLES = PACK / "templates" / "samples"
CASES = {
    "bd": ("resume-bd.txt", "jd-bd.txt", "云栖生活"),
    "da": ("resume-da.txt", "jd-da.txt", "星河数据"),
    "pm": ("resume-pm.txt", "jd-pm.txt", "未知示例公司"),
}
EXP_ID = re.compile(r"^exp_\d{2,3}$")
JD_ID = re.compile(r"^jd_\d{2,3}$")
CARD_KEYS = {
    "analysis_id",
    "verdict_tier",
    "headline",
    "top_strength",
    "top_gap",
    "recommended_action",
    "company_name",
    "depth",
    "report_filename",
    "sections",
    "data_mode",
}


def check_templates() -> None:
    golden = json.loads((PACK / "templates/golden-case-template.json").read_text(encoding="utf-8"))
    assert golden["resume_structured"]["schema_version"] == "1.0"
    assert golden["jd_structured"]["schema_version"] == "1.0"
    experiences = golden["resume_structured"]["experiences"]
    exp_ids = [e["id"] for e in experiences]
    assert len(set(exp_ids)) == len(exp_ids), "经历 ID 必须唯一"
    assert exp_ids == [f"exp_{i:02d}" for i in range(1, len(exp_ids) + 1)], "经历 ID 必须从 exp_01 连续编号"
    jd_ids = [
        item["id"]
        for key in ("must_have", "nice_to_have", "responsibilities")
        for item in golden["jd_structured"].get(key, [])
    ]
    assert len(set(jd_ids)) == len(jd_ids), "JD ID 必须全局唯一"
    assert all(JD_ID.match(i) for i in jd_ids), f"JD ID 格式非法：{jd_ids}"
    assert golden["verdict_expected_tier"] in ("strong", "discussable", "gap")

    dis = json.loads((PACK / "templates/company-disambiguation-template.json").read_text(encoding="utf-8"))
    assert "candidates" in dis and "needs_user_confirm" in dis

    tpl = (PACK / "templates/report-template.md").read_text(encoding="utf-8")
    for section in [
        "执行摘要",
        "公司背调",
        "岗位拆解",
        "人岗匹配",
        "自我介绍",
        "HR 面试题",
        "背靠知识点",
        "应对方案",
        "数据来源与置信度",
    ]:
        assert section in tpl, f"报告模板缺失：{section}"
    print("  templates ok")


def check_case(name: str, settings) -> None:
    resume_file, jd_file, company = CASES[name]
    result = run_analysis(
        resume_path=SAMPLES / resume_file,
        jd_text=(SAMPLES / jd_file).read_text(encoding="utf-8"),
        company_name=company,
        settings=settings,
    )

    # 1) 产物必须能被同一份契约模型重新解析（extra=forbid，字段漂移会直接炸）
    report = ReportStructured.model_validate(result.structured.model_dump(by_alias=True))

    # 2) 证据 ID 体系：经历连续编号，JD ID 全局唯一且格式正确
    exp_ids = [e["id"] for e in result.resume.model_dump()["experiences"]]
    assert exp_ids == [f"exp_{i:02d}" for i in range(1, len(exp_ids) + 1)], f"[{name}] 经历 ID 不连续：{exp_ids}"
    assert all(EXP_ID.match(i) for i in exp_ids)
    jd_ids = result.jd.all_ids()
    assert len(jd_ids) == len(set(jd_ids)), f"[{name}] JD ID 重复"
    # 项目也是证据来源：维度行与锚点都可以引 proj_xx，不能只认 exp_xx
    resume_ref_ids = result.resume.evidence_ids()

    # 3) 四维齐全，且每维的 JD 引用都真实存在
    dims = {d.name: d for d in report.match.dimensions}
    assert set(dims) == {"硬性条件", "职责匹配", "履历证据", "加分项"}, f"[{name}] 四维不全：{set(dims)}"
    for dim in report.match.dimensions:
        for ref in dim.evidence_refs:
            assert ref in jd_ids or ref in resume_ref_ids or ref in ("未获取", "无对应证据"), f"[{name}] 维度引用了不存在的 ID：{ref}"

    # 4) 面试题：数量达标 + evidence_ref 必须存在
    questions = report.interview_questions
    assert len(questions) >= 8, f"[{name}] 面试题不足 8 道：{len(questions)}"
    for q in questions:
        assert q.evidence_ref in resume_ref_ids or q.evidence_ref in jd_ids, f"[{name}] 题目 {q.id} 引用了不存在的证据 {q.evidence_ref}"
        assert q.question.strip(), f"[{name}] 题目 {q.id} 没有正文"

    # 5) 自我介绍锚点 ≥3 且都是真实证据
    anchors = report.self_intro.anchors
    assert len(anchors) >= 3, f"[{name}] 锚点不足 3 条：{anchors}"
    assert all(a in resume_ref_ids for a in anchors), f"[{name}] 锚点引用了不存在的证据：{anchors}"

    # 6) 9 节齐全且顺序正确
    positions = [result.markdown.find(title) for title in REQUIRED_SECTIONS]
    assert all(p >= 0 for p in positions), f"[{name}] 报告缺节：{[t for t, p in zip(REQUIRED_SECTIONS, positions) if p < 0]}"
    assert positions == sorted(positions), f"[{name}] 报告节顺序错乱"

    # 7) 摘要卡片字段完整、档位合法
    card = result.card
    missing = CARD_KEYS - set(card)
    assert not missing, f"[{name}] 卡片缺字段：{missing}"
    assert card["verdict_tier"] in ("strong", "discussable", "gap")
    assert card["sections"], f"[{name}] 卡片没有各节锚点"
    assert card["report_filename"].endswith(".md")

    # 8) Mock 模式必须自曝：卡片与报告都要写明数据模式
    assert card["data_mode"] == "mock", f"[{name}] Mock 模式未在卡片标注"
    assert "mock" in result.markdown.lower(), f"[{name}] 报告未标注数据模式"

    print(f"  case {name} ok（{len(questions)} 题 / {len(anchors)} 锚点 / {card['verdict_tier']}）")


def check_deep_estimate_is_free(settings) -> None:
    """预估卡片必须零调用——这是"取消 = 不花钱"的结构性保证。"""
    estimate = estimate_deep("云栖生活", settings)
    assert estimate.needs_confirmation is True
    assert estimate.quota_consumed.tianyancha_calls == 0, "预估卡片产生了天眼查调用"
    assert estimate.quota_consumed.search_calls == 0, "预估卡片产生了搜索调用"
    assert estimate.fields, "预估卡片没列出要买的字段"
    print("  deep estimate ok（零调用）")


def main() -> None:
    settings = load_settings()
    check_templates()
    for name in CASES:
        check_case(name, settings)
    check_deep_estimate_is_free(settings)
    print("contracts ok")


if __name__ == "__main__":
    main()
