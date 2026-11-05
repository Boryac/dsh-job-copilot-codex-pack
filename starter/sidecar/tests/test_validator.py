"""证据校验器测试：每条规则一个正例 + 一个反例。"""
from __future__ import annotations

import copy

from app.validator import GENERIC_KNOWLEDGE_MARKER, MIN_ANCHORS, MIN_QUESTIONS, validate_report_full


def _payload(analysis) -> dict:
    return copy.deepcopy(analysis.structured.model_dump(by_alias=True))


def _validate(payload, analysis):
    return validate_report_full(
        payload,
        analysis.resume.evidence_ids(),
        analysis.jd.all_ids(),
        resume=analysis.resume,
        company=analysis.company,
        data_mode=payload.get("data_mode", "mock"),
    )


# ---------------------------------------------------------------- 规则 1：evidence_ref
def test_rule1_valid_report_passes(bd_analysis):
    result = _validate(_payload(bd_analysis), bd_analysis)
    assert result.passed, result.messages("error")


def test_rule1_missing_evidence_ref_fails(bd_analysis):
    payload = _payload(bd_analysis)
    payload["interview_questions"][0]["evidence_ref"] = ""
    result = _validate(payload, bd_analysis)
    assert any("evidence_ref" in m for m in result.messages("error"))


def test_rule1_fabricated_evidence_ref_fails(bd_analysis):
    payload = _payload(bd_analysis)
    payload["interview_questions"][1]["evidence_ref"] = "exp_99"
    result = _validate(payload, bd_analysis)
    assert any("exp_99" in m for m in result.messages("error"))


def test_rule1_too_few_questions_fails(bd_analysis):
    payload = _payload(bd_analysis)
    payload["interview_questions"] = payload["interview_questions"][: MIN_QUESTIONS - 1]
    result = _validate(payload, bd_analysis)
    assert any("至少" in m for m in result.messages("error"))


def test_rule1_incomplete_star_fails(bd_analysis):
    payload = _payload(bd_analysis)
    payload["interview_questions"][0]["star_answer"]["result"] = ""
    result = _validate(payload, bd_analysis)
    assert any("STAR" in m for m in result.messages("error"))


# ------------------------------------------------------------------- 规则 2：锚点
def test_rule2_anchor_requires_metrics(bd_analysis):
    payload = _payload(bd_analysis)
    payload["self_intro"]["anchors"] = ["exp_01", "exp_02", "proj_01", "exp_03"]
    result = _validate(payload, bd_analysis)
    assert any("exp_03" in m for m in result.messages("error"))


def test_rule2_too_few_anchors_without_degradation_fails(bd_analysis):
    payload = _payload(bd_analysis)
    payload["self_intro"]["anchors"] = ["exp_01"]
    payload["self_intro"]["degraded"] = False
    result = _validate(payload, bd_analysis)
    assert any("锚点不足" in m for m in result.messages("error"))


def test_rule2_too_few_anchors_with_degradation_is_warning(bd_analysis):
    payload = _payload(bd_analysis)
    payload["self_intro"]["anchors"] = ["exp_01"]
    payload["self_intro"]["degraded"] = True
    payload["self_intro"]["note"] = "锚点不足，已改为通用表述"
    payload["to_verify"].append("自我介绍锚点不足 3 条，需人工确认")
    result = _validate(payload, bd_analysis)
    assert any("降级处理" in w for w in result.messages("warning"))


# --------------------------------------------------------------- 规则 3：匹配证据表
def test_rule3_dimension_without_exp_ref_needs_gap_note(bd_analysis):
    payload = _payload(bd_analysis)
    dim = payload["match"]["dimensions"][0]
    dim["evidence_refs"] = [r for r in dim["evidence_refs"] if not r.startswith(("exp_", "proj_"))]
    dim["note"] = "只有 JD 侧证据"
    result = _validate(payload, bd_analysis)
    assert any("无对应证据" in m for m in result.messages("error"))


def test_rule3_dimension_with_gap_note_passes(bd_analysis):
    payload = _payload(bd_analysis)
    dim = payload["match"]["dimensions"][0]
    dim["evidence_refs"] = ["jd_01"]
    dim["note"] = "门槛类要求，无对应证据"
    result = _validate(payload, bd_analysis)
    assert not any("无对应证据" in m for m in result.messages("error"))


def test_rule3_row_with_fake_exp_fails(bd_analysis):
    payload = _payload(bd_analysis)
    payload["match"]["dimensions"][0]["rows"][0]["exp_ref"] = "exp_77"
    result = _validate(payload, bd_analysis)
    assert any("exp_77" in m for m in result.messages("error"))


def test_rule3_missing_dimension_fails(bd_analysis):
    payload = _payload(bd_analysis)
    payload["match"]["dimensions"] = payload["match"]["dimensions"][:3]
    result = _validate(payload, bd_analysis)
    assert any("四维" in m for m in result.messages("error"))


# ----------------------------------------------------------------- 规则 4：知识点
def test_rule4_knowledge_without_example_needs_marker(bd_analysis):
    payload = _payload(bd_analysis)
    payload["knowledge"][0]["resume_example_ref"] = None
    payload["knowledge"][0]["definition"] = "只是定义，没有标注"
    result = _validate(payload, bd_analysis)
    assert any(GENERIC_KNOWLEDGE_MARKER in m for m in result.messages("error"))


def test_rule4_knowledge_with_marker_passes(bd_analysis):
    payload = _payload(bd_analysis)
    payload["knowledge"].append(
        {
            "id": "k_99",
            "level": "frequent",
            "term": "GMV 拆解",
            "definition": f"GMV 拆解：通用知识、无简历例证",
            "resume_example_ref": None,
            "likely_follow_up": "你会怎么拆？",
        }
    )
    result = _validate(payload, bd_analysis)
    assert not any("k_99" in m for m in result.messages("error"))


# ------------------------------------------------------------- 规则 5：硬数据泄漏
def test_rule5_unverified_value_must_not_leak(settings, bd_resume_path, bd_jd_text):
    from app.orchestrator.service import run_analysis

    analysis = run_analysis(bd_resume_path, bd_jd_text, "星河数据", settings)
    payload = _payload(analysis)
    assert analysis.company.company_resolved.name is None
    payload["verdict"]["headline"] = "这家公司成立于 1999-09-09，很稳"
    from app.schemas import HardField

    analysis.company.hard_data.founded_at = HardField(value="1999-09-09", verified=False, source="not_fetched")
    result = _validate(payload, analysis)
    assert any("未验证的硬数据" in m for m in result.messages("error"))


# ----------------------------------------------------------------- 规则 6：来源 URL
def test_rule6_mock_mode_requires_mock_scheme(bd_analysis):
    payload = _payload(bd_analysis)
    bd_analysis.company.soft_profile.source_urls.append("https://fake-news.example.org/a")
    result = _validate(payload, bd_analysis)
    assert any("mock://" in m for m in result.messages("error"))


def test_rule6_live_mode_rejects_placeholder_domains(bd_analysis):
    payload = _payload(bd_analysis)
    payload["data_mode"] = "live"
    bd_analysis.company.soft_profile.source_urls = ["https://example.com/news"]
    result = _validate(payload, bd_analysis)
    assert any("占位域名" in m for m in result.messages("error"))


# -------------------------------------------------------------------- 规则 7：隐私
def test_rule7_phone_in_report_fails(bd_analysis):
    payload = _payload(bd_analysis)
    payload["self_intro"]["30s"] = "我叫林舟，电话 13800000000，很高兴认识你"
    result = _validate(payload, bd_analysis)
    assert any("手机号" in m for m in result.messages("error"))


def test_rule7_email_in_report_fails(bd_analysis):
    payload = _payload(bd_analysis)
    payload["self_intro"]["60s"] = "联系我 test@example.com"
    result = _validate(payload, bd_analysis)
    assert any("邮箱" in m for m in result.messages("error"))


def test_thresholds_are_not_lowered(bd_analysis):
    """防止有人为了让测试变绿偷偷改阈值。"""
    from app import validator

    assert validator.MIN_QUESTIONS == 8
    assert validator.MIN_ANCHORS == 3


# ------------------------------------------------------- 规则 6b：硬数据来源自洽
def test_rule6b_mock_hard_data_source_must_use_mock_scheme(bd_analysis):
    bd_analysis.company.hard_data.founded_at.source = "tianyancha_mcp"
    result = _validate(_payload(bd_analysis), bd_analysis)
    assert any("冒称" in m or "冒充" in m for m in result.messages("error")), result.messages("error")


def test_rule6b_mock_hard_data_with_mock_scheme_passes(bd_analysis):
    result = _validate(_payload(bd_analysis), bd_analysis)
    assert not any("R6b-hard-source" in f.rule for f in result.findings), result.messages("error")
