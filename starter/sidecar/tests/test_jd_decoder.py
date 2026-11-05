"""JD 拆解测试：ID 唯一、可追溯、推断标注、URL 失败明确提示粘贴。"""
from __future__ import annotations

import pytest

from app.errors import ToolError
from app.parsers.jd import decode_jd, decode_pasted_text


def test_decodes_requirements_and_responsibilities(settings, bd_jd_text):
    jd = decode_pasted_text(bd_jd_text, settings)
    assert jd.source_type == "pasted_text"
    assert len(jd.must_have) >= 4
    assert len(jd.responsibilities) >= 3
    assert all(item.id.startswith("jd_") for item in jd.must_have + jd.responsibilities)


def test_meta_lines_are_not_treated_as_requirements(settings, bd_jd_text):
    """岗位名称/工作地点/薪资是元信息，混进 must_have 会污染匹配。"""
    jd = decode_pasted_text(bd_jd_text, settings)
    texts = " ".join(i.text for i in jd.must_have + jd.nice_to_have)
    assert "岗位名称" not in texts
    assert "工作地点" not in texts
    assert "薪资范围" not in texts


def test_ids_are_globally_unique(settings, bd_jd_text):
    jd = decode_pasted_text(bd_jd_text, settings)
    ids = [i.id for i in jd.must_have + jd.nice_to_have + jd.responsibilities]
    assert len(ids) == len(set(ids))


def test_every_item_text_is_traceable_to_source(settings, bd_jd_text):
    jd = decode_pasted_text(bd_jd_text, settings)
    source = bd_jd_text.replace(" ", "")
    for item in jd.must_have + jd.nice_to_have + jd.responsibilities:
        assert item.text.replace(" ", "") in source


def test_inferences_are_flagged(settings, bd_jd_text):
    jd = decode_pasted_text(bd_jd_text, settings)
    assert jd.hidden_priorities or jd.red_flags
    for item in jd.hidden_priorities + jd.red_flags:
        assert item.inferred is True


def test_red_flag_years_requirement(settings, bd_jd_text):
    jd = decode_pasted_text(bd_jd_text, settings)
    assert any("年限" in f.text for f in jd.red_flags)


def test_nice_to_have_classification(settings, bd_jd_text):
    jd = decode_pasted_text(bd_jd_text, settings)
    assert any("优先" in i.text for i in jd.nice_to_have)


def test_too_short_text_is_rejected(settings):
    with pytest.raises(ToolError) as exc:
        decode_pasted_text("招人", settings)
    assert exc.value.code == "INVALID_INPUT"


def test_url_path_in_mock_mode_asks_for_paste(settings):
    with pytest.raises(ToolError) as exc:
        decode_jd(None, settings, jd_url="https://example.com/job/1")
    assert exc.value.code == "URL_FETCH_FAILED"
    assert exc.value.fallback == "pasted_text_required"
    assert "粘贴" in exc.value.message


def test_invalid_url_scheme_rejected(settings):
    with pytest.raises(ToolError) as exc:
        decode_jd(None, settings, jd_url="ftp://example.com/job")
    assert exc.value.code == "INVALID_INPUT"


def test_no_input_at_all(settings):
    with pytest.raises(ToolError) as exc:
        decode_jd("", settings)
    assert exc.value.code == "INVALID_INPUT"


def test_unstructured_jd_still_classifies(settings):
    text = (
        "我们在招增长运营，负责用户拉新和活动策划，推动跨部门协同。\n"
        "要求：本科以上学历，熟练使用 Excel，具备较强的沟通能力。"
    )
    jd = decode_pasted_text(text, settings)
    assert jd.must_have and jd.responsibilities


def test_nice_to_have_section_is_not_folded_into_must(settings):
    """加分项必须是加分项：被当成硬性要求会把硬性条件档位压低。"""
    text = """岗位名称：商务拓展
任职要求：
1. 本科及以上学历；
2. 有 OTA 商务拓展经验；
加分项：
1. 有公众号或小红书内容运营经验；
2. 有 RAG 或大模型应用项目经验。
"""
    jd = decode_pasted_text(text, settings)
    nice_texts = [i.text for i in jd.nice_to_have]
    must_texts = [i.text for i in jd.must_have]
    assert any("公众号" in t for t in nice_texts), nice_texts
    assert any("RAG" in t or "大模型" in t for t in nice_texts), nice_texts
    assert not any("公众号" in t for t in must_texts), must_texts


def test_nice_to_have_section_is_not_folded_into_must(settings):
    """加分项必须是加分项：被当成硬性要求会把硬性条件档位压低。"""
    text = """岗位名称：商务拓展
任职要求：
1. 本科及以上学历；
2. 有 OTA 商务拓展经验；
加分项：
1. 有公众号或小红书内容运营经验；
2. 有 RAG 或大模型应用项目经验。
"""
    jd = decode_pasted_text(text, settings)
    nice_texts = [i.text for i in jd.nice_to_have]
    must_texts = [i.text for i in jd.must_have]
    assert any("公众号" in t for t in nice_texts), nice_texts
    assert any("RAG" in t or "大模型" in t for t in nice_texts), nice_texts
    assert not any("公众号" in t for t in must_texts), must_texts
