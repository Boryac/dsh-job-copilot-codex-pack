"""证据校验器：引用存在性、来源分区、隐私检查等规则，不过即降级并进待核实清单。

设计原则：
- 校验失败不许直接输出：调用方重生成一次，仍失败则降级标注并进待核实清单。
- 每条规则都有正例与反例测试（见 starter/sidecar/tests/test_validator.py）。
- 阈值写在本文件顶部，不许在测试里改阈值让测试变绿（09 第 6 节）。
"""
from __future__ import annotations

import re

MIN_QUESTIONS = 8
MIN_ANCHORS = 3
GAP_NOTE_MARKER = "无对应证据"
GENERIC_KNOWLEDGE_MARKER = "通用知识、无简历例证"

PHONE_RE = re.compile(r"1[3-9]\d[\d\-\s]{7,11}")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
MOCK_URL_PREFIX = "mock://"
DIMENSION_NAMES = ("硬性条件", "职责匹配", "履历证据", "加分项")


class Finding:
    __slots__ = ("rule", "severity", "message", "ref")

    def __init__(self, rule: str, severity: str, message: str, ref: str = ""):
        self.rule = rule
        self.severity = severity
        self.message = message
        self.ref = ref

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return f"Finding({self.rule}, {self.severity}, {self.message})"

    def as_dict(self) -> dict:
        return {"rule": self.rule, "severity": self.severity, "message": self.message, "ref": self.ref}


class ValidationResult:
    def __init__(self, findings: list[Finding]):
        self.findings = findings

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "error"]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "warning"]

    @property
    def passed(self) -> bool:
        return not self.errors

    def messages(self, severity: str = "error") -> list[str]:
        return [f"[{f.rule}] {f.message}" for f in self.findings if f.severity == severity]


def _get(obj, key, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _resume_metrics(resume) -> dict[str, int]:
    """返回 {evidence_id: 量化成果条数}，用于判断锚点是否有真实量化支撑。"""
    out: dict[str, int] = {}
    if resume is None:
        return out
    for exp in _get(resume, "experiences", []) or []:
        out[_get(exp, "id")] = len(_get(exp, "metrics", []) or [])
    for proj in _get(resume, "projects", []) or []:
        out[_get(proj, "id")] = len(_get(proj, "metrics", []) or [])
    return out


def _iter_text_fields(report) -> list[str]:
    texts: list[str] = []
    verdict = _get(report, "verdict")
    if verdict:
        texts.extend([_get(verdict, "headline") or "", _get(verdict, "top_strength") or "", _get(verdict, "top_gap") or ""])
    intro = _get(report, "self_intro")
    if intro:
        texts.extend([_get(intro, "30s") or "", _get(intro, "60s") or "", _get(intro, "120s") or ""])
    for q in _get(report, "interview_questions", []) or []:
        texts.extend([_get(q, "question") or "", _get(q, "focus") or "", _get(q, "follow_up") or ""])
        star = _get(q, "star_answer") or {}
        for key in ("situation", "task", "action", "result"):
            texts.append(_get(star, key) or "")
    return texts


def validate_report_full(
    report,
    resume_ids: set,
    jd_ids: set,
    *,
    resume=None,
    company=None,
    data_mode: str | None = None,
    partial: bool = False,
) -> ValidationResult:
    """partial=True 只用于"生成步骤超时/失败"的部分报告：
    数量类要求降级为 warning（报告会显式标注未生成），但已存在的题目仍逐条校验证据。
    这不是放宽阈值：正常路径必须 partial=False 且全部 error 通过。
    """
    findings: list[Finding] = []
    questions = _get(report, "interview_questions", []) or []

    # 规则 1：面试题 evidence_ref 必须存在；数量 ≥ 8
    if len(questions) < MIN_QUESTIONS:
        findings.append(
            Finding(
                "R1-evidence-ref",
                "warning" if partial and not questions else "error",
                f"面试题只有 {len(questions)} 道，要求至少 {MIN_QUESTIONS} 道"
                + ("（部分报告，已标注未生成）" if partial and not questions else ""),
            )
        )
    seen_qids: set[str] = set()
    for q in questions:
        qid = _get(q, "id") or "?"
        if qid in seen_qids:
            findings.append(Finding("R1-evidence-ref", "error", f"面试题 ID 重复：{qid}", qid))
        seen_qids.add(qid)
        ref = _get(q, "evidence_ref")
        if not ref:
            findings.append(Finding("R1-evidence-ref", "error", f"面试题 {qid} 缺少 evidence_ref", qid))
        elif ref not in resume_ids and ref not in jd_ids:
            findings.append(
                Finding("R1-evidence-ref", "error", f"面试题 {qid} 的 evidence_ref {ref} 不存在于简历或 JD ID 集合里", qid)
            )
        star = _get(q, "star_answer") or {}
        empty = [k for k in ("situation", "task", "action", "result") if not (_get(star, k) or "").strip()]
        if empty:
            findings.append(Finding("R1-evidence-ref", "error", f"面试题 {qid} 的 STAR 骨架缺字段：{', '.join(empty)}", qid))
        if _get(q, "evidence_status") == "degraded":
            findings.append(
                Finding("R1-evidence-ref", "warning", f"面试题 {qid} 证据已降级，必须出现在待核实清单", qid)
            )

    # 规则 2：自我介绍锚点 ≥ 3，且每条能在简历里找到量化成果
    intro = _get(report, "self_intro")
    anchors = _get(intro, "anchors", []) or []
    degraded = bool(_get(intro, "degraded", False))
    note = _get(intro, "note") or ""
    to_verify = _get(report, "to_verify", []) or []
    if len(anchors) < MIN_ANCHORS:
        if degraded and note:
            findings.append(
                Finding("R2-anchors", "warning", f"自我介绍锚点 {len(anchors)} 条（不足 {MIN_ANCHORS}），已按降级处理并标注")
            )
            if not any("锚点" in t for t in to_verify):
                findings.append(Finding("R2-anchors", "error", "锚点不足但待核实清单里没有记录"))
        elif partial:
            findings.append(
                Finding("R2-anchors", "warning", f"自我介绍未生成（部分报告），锚点 {len(anchors)} 条")
            )
        else:
            findings.append(
                Finding("R2-anchors", "error", f"自我介绍锚点不足：{len(anchors)} 条，要求至少 {MIN_ANCHORS} 条")
            )
    metrics = _resume_metrics(resume)
    for a in anchors:
        if a not in resume_ids:
            findings.append(Finding("R2-anchors", "error", f"自我介绍锚点 {a} 不存在于简历 ID 集合里", a))
        elif metrics and metrics.get(a, 0) == 0:
            findings.append(
                Finding("R2-anchors", "error", f"自我介绍锚点 {a} 在简历里没有量化成果，属于无证据引用", a)
            )

    # 规则 3：匹配表每行必须同时有 jd ID 和 exp ID
    dims = _get(_get(report, "match"), "dimensions", []) or []
    dim_names = [_get(d, "name") for d in dims]
    if sorted(dim_names) != sorted(DIMENSION_NAMES):
        findings.append(
            Finding("R3-match-refs", "error", f"人岗匹配必须且只能是四维 {DIMENSION_NAMES}，实际 {dim_names}")
        )
    for dim in dims:
        refs = _get(dim, "evidence_refs", []) or []
        has_exp = any(str(r).startswith(("exp_", "proj_")) for r in refs)
        has_jd = any(str(r).startswith("jd_") for r in refs)
        note_text = _get(dim, "note") or ""
        if not has_exp or not has_jd:
            if GAP_NOTE_MARKER not in note_text:
                findings.append(
                    Finding(
                        "R3-match-refs",
                        "error",
                        f"维度「{_get(dim, 'name')}」缺少{'简历' if not has_exp else 'JD'}证据，但备注未写「无对应证据」",
                        _get(dim, "name") or "",
                    )
                )
        for row in _get(dim, "rows", []) or []:
            jd_ref = row.get("jd_ref")
            exp_ref = row.get("exp_ref")
            if not jd_ref or jd_ref not in jd_ids:
                findings.append(
                    Finding("R3-match-refs", "error", f"匹配行引用了不存在的 JD ID：{jd_ref}", _get(dim, "name") or "")
                )
            if not exp_ref or (exp_ref != GAP_NOTE_MARKER and exp_ref not in resume_ids):
                if exp_ref != GAP_NOTE_MARKER:
                    findings.append(
                        Finding("R3-match-refs", "error", f"匹配行引用了不存在的简历证据：{exp_ref}", _get(dim, "name") or "")
                    )

    # 规则 4：知识点无简历例证时必须标注"通用知识、无简历例证"
    for k in _get(report, "knowledge", []) or []:
        if not _get(k, "resume_example_ref"):
            definition = _get(k, "definition") or ""
            if GENERIC_KNOWLEDGE_MARKER not in definition:
                findings.append(
                    Finding(
                        "R4-knowledge",
                        "error",
                        f"知识点 {_get(k, 'id')} 没有简历例证，但未标注「{GENERIC_KNOWLEDGE_MARKER}」",
                        _get(k, "id") or "",
                    )
                )

    # 规则 5：硬数据 verified=false 不许进正文结论
    hard = _get(_get(company, "hard_data"), "fields") if company is not None else None
    if company is not None:
        hard_fields = company.hard_data.fields() if hasattr(company, "hard_data") else {}
        unverified_values = [
            str(f.value) for f in hard_fields.values() if (not f.verified) and f.value not in (None, "")
        ]
        body = " ".join(_iter_text_fields(report))
        for value in unverified_values:
            if value and value in body:
                findings.append(
                    Finding("R5-hard-data", "error", f"未验证的硬数据「{value}」出现在正文结论里", value)
                )
        if any(not f.verified for f in hard_fields.values()):
            if not any(("核实" in t or "未获取" in t) for t in to_verify):
                findings.append(
                    Finding("R5-hard-data", "warning", "存在未验证的硬数据，但待核实清单里没有对应条目")
                )

    # 规则 6：来源 URL 合法且不可自编（mock 模式必须用 mock:// scheme）
    mode = data_mode or _get(report, "data_mode", "mock")
    urls: list[str] = []
    if company is not None and hasattr(company, "soft_profile"):
        urls.extend(company.soft_profile.source_urls)
    for s in _get(report, "sources_and_confidence", []) or []:
        src = _get(s, "source") or ""
        if src.startswith(("http://", "https://", "mock://")):
            urls.append(src)
    for url in urls:
        if mode == "mock":
            if not url.startswith(MOCK_URL_PREFIX):
                findings.append(
                    Finding("R6-source-url", "error", f"Mock 模式的来源链接必须是 {MOCK_URL_PREFIX} scheme，实际 {url}", url)
                )
        else:
            if not re.match(r"^https?://[\w.-]+\.[a-z]{2,}", url):
                findings.append(Finding("R6-source-url", "error", f"来源链接格式非法或疑似自编：{url}", url))
            elif re.search(r"(example\.(com|org|net)|localhost|127\.0\.0\.1)", url):
                findings.append(Finding("R6-source-url", "error", f"来源链接是占位域名，疑似自编：{url}", url))

    # 规则 6b（本项目追加）：硬数据的 source 要与 data_mode 自洽
    # Mock 模式下若写着 tianyancha_mcp，读者会以为这条工商数据真的查过，属于来源失真。
    if company is not None and hasattr(company, "hard_data"):
        for key, field in (company.hard_data.fields() if hasattr(company.hard_data, "fields") else {}).items():
            source = getattr(field, "source", "") or ""
            if not source or source == "not_fetched":
                continue
            if mode == "mock" and not source.startswith(MOCK_URL_PREFIX):
                findings.append(
                    Finding(
                        "R6b-hard-source",
                        "error",
                        f"Mock 模式下硬数据 {key} 的来源标注为 {source}，应为 {MOCK_URL_PREFIX} 前缀，否则会冒充真实核验结果",
                        key,
                    )
                )

    # 规则 7（本项目追加）：报告正文不许出现电话 / 邮箱
    text = " ".join(_iter_text_fields(report))
    if PHONE_RE.search(text):
        findings.append(Finding("R7-privacy", "error", "报告正文出现手机号，违反隐私规范"))
    if EMAIL_RE.search(text):
        findings.append(Finding("R7-privacy", "error", "报告正文出现邮箱，违反隐私规范"))

    return ValidationResult(findings)


def validate_report(report, resume_ids: set, jd_ids: set, **kwargs) -> list[str]:
    """兼容旧签名：返回 error 级消息列表（空列表 = 通过）。"""
    return validate_report_full(report, resume_ids, jd_ids, **kwargs).messages("error")


if __name__ == "__main__":
    # 自检：正例通过，反例必须报错
    ok_report = {
        "interview_questions": [
            {
                "id": f"q_{i:02d}",
                "evidence_ref": "exp_01",
                "star_answer": {"situation": "s", "task": "t", "action": "a", "result": "r"},
            }
            for i in range(1, 9)
        ],
        "self_intro": {"anchors": ["exp_01", "exp_02", "exp_03"]},
        "match": {
            "dimensions": [
                {"name": n, "evidence_refs": ["exp_01", "jd_01"], "note": "", "rows": []}
                for n in DIMENSION_NAMES
            ]
        },
        "knowledge": [],
        "to_verify": [],
        "data_mode": "mock",
    }
    ok = validate_report(ok_report, {"exp_01", "exp_02", "exp_03"}, {"jd_01"})
    assert ok == [], f"正例应通过，实际：{ok}"

    bad_report = {
        "interview_questions": [
            {
                "id": "q_01",
                "evidence_ref": "exp_99",
                "star_answer": {"situation": "s", "task": "t", "action": "a", "result": ""},
            }
        ],
        "self_intro": {"anchors": ["exp_01"]},
        "match": {"dimensions": [{"name": "硬性条件", "evidence_refs": ["jd_01"], "note": "", "rows": []}]},
        "knowledge": [{"id": "k_01", "definition": "没有标注通用知识", "resume_example_ref": None}],
        "to_verify": [],
        "data_mode": "mock",
    }
    bad = validate_report(bad_report, {"exp_01"}, {"jd_01"})
    assert len(bad) >= 4, f"反例应至少报 4 个错误，实际 {len(bad)}：{bad}"
    print("validator self-check passed")
