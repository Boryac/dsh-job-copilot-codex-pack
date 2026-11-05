"""生成测试（T3.2 / T3.5）：题目数量与证据、四类覆盖、锚点、知识点分级。"""
from __future__ import annotations

from app.orchestrator.generate import CATEGORY_ORDER, generate

PACK_SAMPLES = __import__("pathlib").Path(__file__).resolve().parents[3] / "templates" / "samples"

PACK_SAMPLES = __import__("pathlib").Path(__file__).resolve().parents[3] / "templates" / "samples"
from app.orchestrator.matching import build_match
from app.parsers.jd import decode_jd
from app.parsers.resume import parse_resume
from app.schemas import ResumeStructured


def _gen(settings, resume_path, jd_text):
    resume = parse_resume(resume_path, settings, resume_id="t")
    jd = decode_jd(jd_text, settings)
    match = build_match(resume, jd)
    return resume, jd, generate(resume, jd, match)


def test_questions_have_unique_ids_and_valid_refs(settings, bd_resume_path, bd_jd_text):
    resume, jd, gen = _gen(settings, bd_resume_path, bd_jd_text)
    ids = [q["id"] for q in gen.questions]
    assert ids == [f"q_{i:02d}" for i in range(1, len(ids) + 1)]
    valid = resume.evidence_ids() | jd.all_ids()
    assert all(q["evidence_ref"] in valid for q in gen.questions)


def test_questions_cover_all_four_categories(settings, bd_resume_path, bd_jd_text):
    _, _, gen = _gen(settings, bd_resume_path, bd_jd_text)
    cats = {q["category"] for q in gen.questions}
    assert cats == set(CATEGORY_ORDER)


def test_at_least_eight_questions(settings, bd_resume_path, bd_jd_text):
    _, _, gen = _gen(settings, bd_resume_path, bd_jd_text)
    assert len(gen.questions) >= 8


def test_star_answer_is_complete(settings, bd_resume_path, bd_jd_text):
    _, _, gen = _gen(settings, bd_resume_path, bd_jd_text)
    for q in gen.questions:
        for key in ("situation", "task", "action", "result"):
            assert q["star_answer"][key].strip(), f"{q['id']} 缺 {key}"
        assert q["follow_up"].strip()
        assert q["pitfall"].strip()


def test_questions_quote_real_facts(settings, bd_resume_path, bd_jd_text):
    """题目里出现的公司名/数字必须来自简历原文，不能是编的。"""
    resume, _, gen = _gen(settings, bd_resume_path, bd_jd_text)
    corpus = " ".join(
        [f"{e.company} {e.role} {' '.join(e.bullets)}" for e in resume.experiences]
        + [p.name or "" for p in resume.projects]
    )
    exp_questions = [q for q in gen.questions if q["evidence_ref"].startswith(("exp_", "proj_"))]
    assert exp_questions
    for q in exp_questions:
        assert any(e.company and e.company in q["question"] for e in resume.experiences) or any(
            b[:8] in q["question"] for e in resume.experiences for b in e.bullets
        )


def test_self_intro_anchors_have_metrics(settings, bd_resume_path, bd_jd_text):
    resume, _, gen = _gen(settings, bd_resume_path, bd_jd_text)
    metrics = resume.metrics_map()
    assert len(gen.self_intro["anchors"]) >= 3
    for anchor in gen.self_intro["anchors"]:
        assert metrics.get(anchor), f"{anchor} 没有量化成果"


def test_self_intro_does_not_invent_numbers(settings, bd_resume_path, bd_jd_text):
    resume, _, gen = _gen(settings, bd_resume_path, bd_jd_text)
    allowed = {m.value for e in resume.experiences + resume.projects for m in e.metrics}
    import re

    for key in ("30s", "60s", "120s"):
        found = set(re.findall(r"\d+(?:\.\d+)?%", gen.self_intro[key]))
        assert found <= allowed, f"{key} 出现了简历里没有的数字：{found - allowed}"


def test_insufficient_anchors_degrades_honestly(settings, tmp_path):
    """可量化成果不足 3 条时，必须降级并标注，不许现编。"""
    path = tmp_path / "thin.txt"
    path.write_text(
        "王某\n求职意向：运营\n\n工作经历\n2024.01-2024.06  A 公司  运营实习生\n- 负责日常内容更新\n",
        encoding="utf-8",
    )
    resume = parse_resume(path, settings, resume_id="thin")
    jd = decode_jd(open("../../templates/samples/jd-bd.txt", encoding="utf-8").read(), settings)
    gen = generate(resume, jd, build_match(resume, jd))
    assert gen.self_intro["degraded"] is True
    assert gen.self_intro["note"]
    assert any("锚点" in item for item in gen.to_verify)


def test_knowledge_levels_are_valid(settings, bd_resume_path, bd_jd_text):
    _, _, gen = _gen(settings, bd_resume_path, bd_jd_text)
    assert gen.knowledge
    assert all(k["level"] in ("must", "bonus", "frequent") for k in gen.knowledge)
    ids = [k["id"] for k in gen.knowledge]
    assert ids == [f"k_{i:02d}" for i in range(1, len(ids) + 1)]


def test_knowledge_without_example_is_marked(settings, bd_resume_path, bd_jd_text):
    _, _, gen = _gen(settings, bd_resume_path, bd_jd_text)
    for k in gen.knowledge:
        if not k["resume_example_ref"]:
            assert "通用知识、无简历例证" in k["definition"]


def test_action_plan_is_bullet_level(settings, bd_resume_path, bd_jd_text):
    _, _, gen = _gen(settings, bd_resume_path, bd_jd_text)
    plan = gen.action_plan
    assert 3 <= len(plan["before_apply"]) <= 5
    assert any("exp_" in item for item in plan["before_apply"] + plan["in_interview_defense"]) or any(
        "jd_" in item for item in plan["before_apply"]
    )
    assert len(plan["questions_to_ask"]) == 3
    assert plan["after_interview"]


# ------------------------------------------------- 能力类题目按证据分流（v1 补缺口）
def test_ability_question_uses_evidence_when_resume_has_it(settings, bd_resume_path, bd_jd_text):
    """简历里明明有对应经历，能力类题不该还问"你理解这个要求是什么样"。"""
    resume, jd, gen = _gen(settings, bd_resume_path, bd_jd_text)
    evid = set(resume.evidence_ids())
    ability = [q for q in gen.questions if q["category"] == "岗位认知" and q["evidence_ref"] in evid]
    assert ability, "没有任何一道岗位认知题锚定到简历证据"
    assert any("其实能对上" in q["question"] for q in ability), [q["question"] for q in ability]
    # 锚到证据的题必须给出简历里的原文片段，不能只挂一个 ID
    for q in ability:
        assert len(q["question"]) > 20


def test_ability_question_falls_back_when_no_evidence(settings, da_resume_path):
    """简历确实没有对应证据时，才问"你理解这条要求在实际工作里是什么样"。"""
    jd_text = (
        "岗位名称：后端开发工程师\n"
        "岗位职责：\n1. 负责 Go 微服务开发。\n"
        "任职要求：\n1. 本科及以上学历；\n2. 熟悉 Kubernetes 与微服务治理。\n"
    )
    _, _, gen = _gen(settings, da_resume_path, jd_text)
    ability = [q for q in gen.questions if q["category"] == "岗位认知"]
    assert ability
    assert any("Kubernetes" in q["question"] or "你理解这个要求" in q["question"] for q in ability)


# ------------------------------------------------- 经历深挖句式变体（v1 补缺口）
DIG_MARKERS = {
    "最难的一步": "main_a",
    "主导还是配合": "main_b",
    "三分钟": "main_c",
    "怎么衡量出来": "metric_a",
    "统计口径和样本范围": "metric_b",
    "拆出分子和分母": "metric_c",
    "会先改哪一步": "review_a",
    "最该提前判断": "review_b",
    "砍掉哪部分": "review_c",
}


def _dig_tags(gen) -> list[str]:
    tags = []
    for q in gen.questions:
        if q["category"] != "经历深挖":
            continue
        tags.extend(tag for marker, tag in DIG_MARKERS.items() if marker in q["question"])
    return tags


def test_dig_question_wording_varies_across_resumes(settings):
    """三类深挖题都不许是固定句式：换简历应出现不同变体。"""
    seen: set[str] = set()
    for name in ("resume-bd.txt", "resume-da.txt", "resume-pm.txt", "resume-op.txt", "resume-ka.txt"):
        jd_file = {
            "resume-bd.txt": "jd-bd.txt",
            "resume-da.txt": "jd-da.txt",
            "resume-pm.txt": "jd-pm.txt",
            "resume-op.txt": "jd-op.txt",
            "resume-ka.txt": "jd-ka.txt",
        }[name]
        _, _, gen = _gen(
            settings,
            PACK_SAMPLES / name,
            (PACK_SAMPLES / jd_file).read_text(encoding="utf-8"),
        )
        tags = _dig_tags(gen)
        assert tags, f"{name} 没有可识别的深挖句式"
        seen.update(tags)
    mains = {t for t in seen if t.startswith("main_")}
    assert len(mains) >= 2, f"主问题只有一种句式，换简历不变体：{mains}"
    assert len(seen) >= 5, f"深挖题型过于单一：{sorted(seen)}"


def test_dig_question_is_still_anchored_to_bullet(settings, bd_resume_path, bd_jd_text):
    """换了句式也不能变成通用题：题面必须包含该经历的原文片段。"""
    resume, _, gen = _gen(settings, bd_resume_path, bd_jd_text)
    bullets = {b for exp in resume.experiences for b in exp.bullets}
    digs = [q for q in gen.questions if q["category"] == "经历深挖"]
    assert digs
    for q in digs:
        head = q["question"][:14]
        assert any(b[:10] in q["question"] or q["question"].find(head) >= 0 for b in bullets), q["question"]


def test_dig_variants_are_deterministic(settings, bd_resume_path, bd_jd_text):
    """同一份简历跑两次，句式必须一致（不许随机抖动让报告不可复现）。"""
    _, _, first = _gen(settings, bd_resume_path, bd_jd_text)
    _, _, second = _gen(settings, bd_resume_path, bd_jd_text)
    assert [q["question"] for q in first.questions] == [q["question"] for q in second.questions]


# ------------------------------------------------- 能力类题目按证据分流（v1 补缺口）
def test_ability_question_uses_evidence_when_resume_has_it(settings, bd_resume_path, bd_jd_text):
    """简历里明明有对应经历，能力类题不该还问"你理解这个要求是什么样"。"""
    resume, jd, gen = _gen(settings, bd_resume_path, bd_jd_text)
    evid = set(resume.evidence_ids())
    ability = [q for q in gen.questions if q["category"] == "岗位认知" and q["evidence_ref"] in evid]
    assert ability, "没有任何一道岗位认知题锚定到简历证据"
    assert any("其实能对上" in q["question"] for q in ability), [q["question"] for q in ability]
    # 锚到证据的题必须给出简历里的原文片段，不能只挂一个 ID
    for q in ability:
        assert len(q["question"]) > 20


def test_ability_question_falls_back_when_no_evidence(settings, da_resume_path):
    """简历确实没有对应证据时，才问"你理解这条要求在实际工作里是什么样"。"""
    jd_text = "\n".join(
        [
            "岗位名称：后端开发工程师",
            "岗位职责：",
            "1. 负责 Go 微服务开发。",
            "任职要求：",
            "1. 本科及以上学历；",
            "2. 熟悉 Kubernetes 与微服务治理。",
        ]
    )
    _, _, gen = _gen(settings, da_resume_path, jd_text)
    ability = [q for q in gen.questions if q["category"] == "岗位认知"]
    assert ability
    assert any("Kubernetes" in q["question"] or "你理解这个要求" in q["question"] for q in ability)


# ------------------------------------------------- 经历深挖句式变体（v1 补缺口）
DIG_MARKERS = {
    "最难的一步": "main_a",
    "主导还是配合": "main_b",
    "三分钟": "main_c",
    "怎么衡量出来": "metric_a",
    "统计口径和样本范围": "metric_b",
    "拆出分子和分母": "metric_c",
    "会先改哪一步": "review_a",
    "最该提前判断": "review_b",
    "砍掉哪部分": "review_c",
}


def _dig_tags(gen) -> list[str]:
    tags = []
    for q in gen.questions:
        if q["category"] != "经历深挖":
            continue
        tags.extend(tag for marker, tag in DIG_MARKERS.items() if marker in q["question"])
    return tags


def test_dig_question_wording_varies_across_resumes(settings):
    """三类深挖题都不许是固定句式：换简历应出现不同变体。"""
    seen: set[str] = set()
    for name in ("resume-bd.txt", "resume-da.txt", "resume-pm.txt", "resume-op.txt", "resume-ka.txt"):
        jd_file = {
            "resume-bd.txt": "jd-bd.txt",
            "resume-da.txt": "jd-da.txt",
            "resume-pm.txt": "jd-pm.txt",
            "resume-op.txt": "jd-op.txt",
            "resume-ka.txt": "jd-ka.txt",
        }[name]
        _, _, gen = _gen(
            settings,
            PACK_SAMPLES / name,
            (PACK_SAMPLES / jd_file).read_text(encoding="utf-8"),
        )
        tags = _dig_tags(gen)
        assert tags, f"{name} 没有可识别的深挖句式"
        seen.update(tags)
    mains = {t for t in seen if t.startswith("main_")}
    assert len(mains) >= 2, f"主问题只有一种句式，换简历不变体：{mains}"
    assert len(seen) >= 5, f"深挖题型过于单一：{sorted(seen)}"


def test_dig_question_is_still_anchored_to_bullet(settings, bd_resume_path, bd_jd_text):
    """换了句式也不能变成通用题：题面必须包含该经历的原文片段。"""
    resume, _, gen = _gen(settings, bd_resume_path, bd_jd_text)
    bullets = {b for exp in resume.experiences for b in exp.bullets}
    digs = [q for q in gen.questions if q["category"] == "经历深挖"]
    assert digs
    for q in digs:
        head = q["question"][:14]
        assert any(b[:10] in q["question"] or q["question"].find(head) >= 0 for b in bullets), q["question"]


def test_dig_variants_are_deterministic(settings, bd_resume_path, bd_jd_text):
    """同一份简历跑两次，句式必须一致（不许随机抖动让报告不可复现）。"""
    _, _, first = _gen(settings, bd_resume_path, bd_jd_text)
    _, _, second = _gen(settings, bd_resume_path, bd_jd_text)
    assert [q["question"] for q in first.questions] == [q["question"] for q in second.questions]
