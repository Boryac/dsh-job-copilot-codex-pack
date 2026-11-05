"""契约测试：三个工具的 Schema 各给正例 + 反例。

反例不是"随便造个错"，每个都对应数据契约的一条校验要点，改坏了必须红。
"""
from __future__ import annotations

import copy

import pytest
from pydantic import ValidationError

from app.schemas import CompanyRecon, InterviewQuestion, JdDecoded, ReportStructured, ResumeStructured

VALID_RESUME = {
    "schema_version": "1.0",
    "parsing_mode": "fallback",
    "basic_info": {"name": "林舟", "title": "商务拓展", "location": "福州", "links": []},
    "education": [{"school": "某学院", "major": "人工智能", "degree": "本科", "period": "2023.09-2027.06"}],
    "experiences": [
        {
            "id": "exp_01",
            "company": "云途旅行",
            "role": "商务拓展实习生",
            "period": "2025.07-2025.09",
            "bullets": ["负责 32 家酒店供应商签约，季度 GMV 提升 18%"],
            "metrics": [{"value": "18%", "context": "季度 GMV 提升 18%"}],
        },
        {
            "id": "exp_02",
            "company": "山海文旅",
            "role": "市场运营实习生",
            "period": "2024.12-2025.03",
            "bullets": ["策划 6 条线路，单月引流 1.2 万人次"],
            "metrics": [{"value": "6条", "context": "策划 6 条线路"}],
        },
    ],
    "projects": [],
    "skills": ["Excel"],
    "parsing_notes": ["Mock 样例"],
}


def _resume(**overrides) -> dict:
    data = copy.deepcopy(VALID_RESUME)
    data.update(overrides)
    return data


def test_resume_positive():
    model = ResumeStructured.model_validate(_resume())
    assert model.experience_ids() == {"exp_01", "exp_02"}
    assert model.parsing_mode == "fallback"


@pytest.mark.parametrize(
    "bad_id",
    ["exp_1", "EXP_01", "exp-01", "experience_01"],
)
def test_resume_rejects_bad_id_format(bad_id):
    data = _resume()
    data["experiences"][0]["id"] = bad_id
    with pytest.raises(ValidationError):
        ResumeStructured.model_validate(data)


def test_resume_rejects_duplicate_ids():
    data = _resume()
    data["experiences"][1]["id"] = "exp_01"
    with pytest.raises(ValidationError):
        ResumeStructured.model_validate(data)


def test_resume_rejects_non_continuous_ids():
    data = _resume()
    data["experiences"][0]["id"] = "exp_02"
    with pytest.raises(ValidationError):
        ResumeStructured.model_validate(data)


def test_resume_rejects_unknown_parsing_mode():
    with pytest.raises(ValidationError):
        ResumeStructured.model_validate(_resume(parsing_mode="magic"))


VALID_JD = {
    "schema_version": "1.0",
    "source_type": "pasted_text",
    "must_have": [{"id": "jd_01", "text": "本科及以上学历", "type": "hard"}],
    "nice_to_have": [{"id": "jd_02", "text": "有商户资源者优先", "type": "soft"}],
    "responsibilities": [{"id": "jd_03", "text": "负责商户拓展与签约"}],
    "hidden_priorities": [{"text": "结果导向", "evidence_sentence_ids": ["jd_03"], "inferred": True}],
    "red_flags": [{"text": "可能加班", "evidence_sentence_ids": [], "inferred": True}],
    "role_summary": "本地生活 BD",
}


def test_jd_positive():
    model = JdDecoded.model_validate(VALID_JD)
    assert model.requirement_ids() == {"jd_01", "jd_02"}
    assert model.all_ids() == {"jd_01", "jd_02", "jd_03"}


def test_jd_rejects_duplicate_ids_across_sections():
    data = copy.deepcopy(VALID_JD)
    data["responsibilities"][0]["id"] = "jd_01"
    with pytest.raises(ValidationError):
        JdDecoded.model_validate(data)


def test_jd_requires_inferred_true():
    data = copy.deepcopy(VALID_JD)
    data["hidden_priorities"][0]["inferred"] = False
    with pytest.raises(ValidationError):
        JdDecoded.model_validate(data)


def _company(**overrides) -> dict:
    base = {
        "schema_version": "1.0",
        "company_input": "云栖生活",
        "company_resolved": {
            "name": "云栖生活科技（福州）有限公司",
            "unified_credit_code": None,
            "disambiguation": {"candidates": [], "chosen_reason": "唯一候选", "needs_user_confirm": False},
        },
        "hard_data": {
            "founded_at": {"value": "2019-04-11", "verified": True, "source": "tianyancha_mcp"},
            "registered_capital": {"value": None, "verified": False, "source": "not_fetched"},
            "legal_representative": {"value": None, "verified": False, "source": "not_fetched"},
            "business_scope": {"value": None, "verified": False, "source": "not_fetched"},
        },
        "soft_profile": {"products": [], "news": [], "financing": [], "hiring_signals": [],
                         "inferred": True, "source_urls": []},
        "deep_data": None,
        "depth_used": "basic",
        "quota_consumed": {"tianyancha_calls": 2, "tianyancha_detail": [], "search_calls": 4},
        "fetched_at": "2026-11-05T10:00:00+08:00",
        "data_mode": "mock",
    }
    base.update(overrides)
    return base


def test_company_positive():
    model = CompanyRecon.model_validate(_company())
    assert model.quota_consumed.tianyancha_calls == 2
    assert model.soft_profile.inferred is True


def test_company_rejects_inferred_inside_hard_data():
    data = _company()
    data["hard_data"]["founded_at"] = {"value": "2019-04-11", "verified": True, "source": "x", "inferred": True}
    with pytest.raises(ValidationError):
        CompanyRecon.model_validate(data)


def test_company_deep_requires_deep_data():
    with pytest.raises(ValidationError):
        CompanyRecon.model_validate(_company(depth_used="deep", deep_data=None))


def test_company_soft_profile_must_be_inferred():
    data = _company()
    data["soft_profile"]["inferred"] = False
    with pytest.raises(ValidationError):
        CompanyRecon.model_validate(data)


def test_question_requires_valid_id():
    with pytest.raises(ValidationError):
        InterviewQuestion(
            id="q1",
            category="动机",
            question="为什么投我们",
            focus="动机",
            evidence_ref="exp_01",
            star_answer={"situation": "s", "task": "t", "action": "a", "result": "r"},
        )


def test_report_requires_exactly_four_dimensions():
    report = {
        "analysis_id": "11111111-1111-1111-1111-111111111111",
        "verdict": {"tier": "discussable", "headline": "h", "top_strength": "s", "top_gap": "g"},
        "match": {"dimensions": [
            {"name": "硬性条件", "tier": "gap", "evidence_refs": [], "note": ""},
            {"name": "职责匹配", "tier": "strong", "evidence_refs": [], "note": ""},
        ]},
        "self_intro": {"30s": "a", "60s": "b", "120s": "c", "anchors": []},
        "interview_questions": [],
        "knowledge": [],
        "action_plan": {},
        "sources_and_confidence": [],
        "to_verify": [],
    }
    with pytest.raises(ValidationError):
        ReportStructured.model_validate(report)
