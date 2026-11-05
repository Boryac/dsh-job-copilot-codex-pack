"""编排层（Lane D，T2.2）：固定顺序、分段生成、超时降级、校验后输出。

固定顺序（01 第 6 节）：
  resume-structurer ∥ jd-decoder ∥ company-recon(basic)
  -> 匹配（四维档位） -> 自我介绍 -> 面试题（带 evidence_ref） -> 8 节报告 + Markdown 导出

超时策略（02 第 4 节）：
- 简历超时 -> fallback 解析继续；
- 公司超时 -> 只出"未获取"的降级结果，不阻塞报告；
- 生成超时 -> 该段标"未生成"并给重试入口，其余段落照常输出；
- 任何一步都不许让整份报告空白。
"""
from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..config import Settings
from ..errors import EVIDENCE_INVALID, PARSE_FAILED, TIMEOUT, ToolError
from ..logging_utils import get_logger, hash_id, text_hash, timed
from ..parsers.jd import decode_jd
from ..parsers.resume import parse_resume
from ..recon.service import company_recon
from ..schemas import ReportStructured, ResumeStructured, JdDecoded, CompanyRecon
from ..validator import validate_report_full
from .generate import GenResult, generate
from .matching import build_match
from .report import build_filename, render_report, render_summary_card

CST = timezone(timedelta(hours=8))
logger = get_logger("orchestrator")


@dataclass
class AnalysisResult:
    analysis_id: str
    structured: ReportStructured
    markdown: str
    filename: str
    card: dict
    timings: dict[str, int] = field(default_factory=dict)
    degradations: list[str] = field(default_factory=list)
    validation_warnings: list[str] = field(default_factory=list)
    resume: ResumeStructured | None = None
    jd: JdDecoded | None = None
    company: CompanyRecon | None = None


def _run_with_budget(step: str, fn, budget_ms: int, fallback: str, force: bool = False):
    """在预算内执行；超时抛 TIMEOUT，由调用方决定降级。

    注意不要用 `with ThreadPoolExecutor(...)`：退出上下文会 shutdown(wait=True)，
    等于把超时又等回去了，超时保护失效。

    `force=True` 走 MOCK_FORCE_TIMEOUT 注入（config.mock_force_timeout），
    用来确定性地复现"某一步预算耗尽"的降级行为，不必真等 30 秒 ×N 次。
    """
    if force:
        raise ToolError(
            code=TIMEOUT,
            message=f"{step} 超过 {budget_ms / 1000:.0f} 秒预算，已按降级方案继续。（MOCK_FORCE_TIMEOUT 注入）",
            retryable=True,
            fallback=fallback,
        )
    pool = ThreadPoolExecutor(max_workers=1)
    future = pool.submit(fn)
    try:
        result = future.result(timeout=budget_ms / 1000)
    except FutureTimeout as exc:
        future.cancel()
        pool.shutdown(wait=False)
        raise ToolError(
            code=TIMEOUT,
            message=f"{step} 超过 {budget_ms / 1000:.0f} 秒预算，已按降级方案继续。",
            retryable=True,
            fallback=fallback,
        ) from exc
    pool.shutdown(wait=False)
    return result


def _now() -> str:
    return datetime.now(CST).replace(microsecond=0).isoformat()


def _sources_table(
    resume: ResumeStructured,
    jd: JdDecoded,
    company: CompanyRecon | None,
) -> list[dict]:
    rows: list[dict] = []
    if company is not None:
        labels = {
            "founded_at": "成立时间",
            "registered_capital": "注册资本",
            "legal_representative": "法定代表人",
            "business_scope": "经营范围",
            "registered_address": "注册地址",
            "status": "企业状态",
        }
        for key, label in labels.items():
            f = company.hard_data.fields().get(key)
            if f is None:
                continue
            rows.append(
                {
                    "item": label,
                    "source": f.source,
                    "confidence": "verified" if f.verified else "unverified",
                    "fetched_at": company.fetched_at,
                }
            )
        if company.soft_profile.source_urls:
            for url in company.soft_profile.source_urls[:6]:
                rows.append(
                    {"item": "软信息（产品/新闻/融资）", "source": url, "confidence": "inferred",
                     "fetched_at": company.fetched_at}
                )
        else:
            rows.append(
                {"item": "软信息（产品/新闻/融资）", "source": "未检索到", "confidence": "unverified",
                 "fetched_at": company.fetched_at}
            )
    rows.append(
        {
            "item": "JD 要求",
            "source": f"jd_{jd.source_type}",
            "confidence": "verified",
            "fetched_at": None,
        }
    )
    rows.append(
        {
            "item": "简历经历与量化成果",
            "source": f"resume_parse:{resume.parsing_mode}",
            "confidence": "verified" if resume.parsing_mode == "smartresume" else "inferred",
            "fetched_at": None,
        }
    )
    return rows


def _to_verify_list(
    resume: ResumeStructured,
    company: CompanyRecon | None,
    gen_verify: list[str],
    gen_degradations: list[str],
    question_degradations: list[str],
) -> list[str]:
    items: list[str] = []
    for note in resume.parsing_notes:
        items.append(f"简历解析：{note}")
    if company is not None:
        for d in company.degradations:
            items.append(f"公司背调：{d}")
        for key, f in company.hard_data.fields().items():
            if not f.verified:
                items.append(f"工商硬数据「{key}」未核实，报告正文未当作事实使用")
        if company.company_resolved.disambiguation.needs_user_confirm:
            items.append("公司主体未唯一确定，请先确认工商全称后再做深度背调")
        if company.data_mode == "mock":
            items.append("公司数据为 Mock 示例（虚构企业），不可用于真实投递决策")
    items.extend(gen_verify)
    items.extend(gen_degradations)
    items.extend(question_degradations)
    # 去重保序
    out: list[str] = []
    for item in items:
        if item not in out:
            out.append(item)
    return out


def _repair_questions(report_data: dict, resume_ids: set, jd_ids: set) -> tuple[dict, list[str]]:
    """校验失败时的重生成/降级：丢弃证据不存在的题，并把原因记入待核实清单。"""
    notes: list[str] = []
    kept = []
    for q in report_data.get("interview_questions", []):
        ref = q.get("evidence_ref")
        if ref and (ref in resume_ids or ref in jd_ids):
            kept.append(q)
        else:
            notes.append(f"面试题 {q.get('id')} 的 evidence_ref（{ref}）不存在，已从报告中移除，请补充对应经历")
    report_data["interview_questions"] = kept
    return report_data, notes


def run_analysis(
    resume_path: str | Path,
    jd_text: str | None,
    company_name: str,
    settings: Settings,
    depth: str = "basic",
    confirmed_deep: bool = False,
    jd_url: str | None = None,
    analysis_id: str | None = None,
) -> AnalysisResult:
    analysis_id = analysis_id or str(uuid.uuid4())
    timings: dict[str, int] = {}
    degradations: list[str] = []

    # 1. 简历
    with timed(logger, "resume_structurer", sink=timings, analysis=hash_id(analysis_id)):
        try:
            resume = _run_with_budget(
                "简历解析",
                lambda: parse_resume(resume_path, settings, resume_id=Path(resume_path).stem),
                settings.timeout_ms("resume_structurer"),
                fallback="fallback_parser",
                force=settings.mock_force_timeout == "resume",
            )
        except ToolError as exc:
            if exc.code == TIMEOUT:
                degradations.append("简历解析超时，已改用 fallback 解析（字段准确性需人工复核）")
                resume = parse_resume(resume_path, settings, resume_id=Path(resume_path).stem)
            else:
                raise
    if not resume.experiences:
        raise ToolError(
            code=PARSE_FAILED,
            message="简历没有解析出任何工作/实习经历，无法产出可溯源的报告。请提供文本版简历（PDF 需带文字层，或直接贴文本）。",
            retryable=True,
            fallback="",
        )

    # 2. JD
    with timed(logger, "jd_decoder", sink=timings, analysis=hash_id(analysis_id)):
        jd = _run_with_budget(
            "JD 拆解",
            lambda: decode_jd(jd_text, settings, jd_url=jd_url),
            settings.timeout_ms("jd_decoder"),
            fallback="pasted_text_required",
            force=settings.mock_force_timeout == "jd",
        )

    # 3. 公司（失败只降级，不阻塞）
    company: CompanyRecon | None = None
    with timed(logger, "company_recon", sink=timings, analysis=hash_id(analysis_id)):
        try:
            result = _run_with_budget(
                "公司背调",
                lambda: company_recon(
                    company_name,
                    settings,
                    depth=depth,
                    confirmed_deep=confirmed_deep,
                    role_keywords=[i.text for i in jd.must_have][:6],
                ),
                settings.timeout_ms("company_recon"),
                fallback="hard_data_only",
                force=settings.mock_force_timeout == "company",
            )
            if isinstance(result, CompanyRecon):
                company = result
            else:
                degradations.append("deep 背调需要用户确认预估费用，本次按 basic 结果生成报告")
                company = company_recon(company_name, settings, depth="basic")
        except ToolError as exc:
            degradations.append(f"公司背调未完成（{exc.code}）：{exc.message}")
            company = None

    # 公司侧重降级（额度耗尽、软信息未获取、消歧失败…）必须上浮到报告与卡片。
    # 只留在 company.degradations 里用户看不到 —— 11 第 1 节要求降级可见，不许静默。
    if company is not None:
        for note in company.degradations:
            degradations.append(f"公司背调：{note}")

    # 4. 匹配
    with timed(logger, "matching", sink=timings, analysis=hash_id(analysis_id)):
        match = build_match(resume, jd)

    # 5. 生成
    partial = False
    with timed(logger, "generate", sink=timings, analysis=hash_id(analysis_id)):
        company_ctx = None
        if company is not None:
            company_ctx = {
                "resolved_name": company.company_resolved.name,
                "news": [n.model_dump() for n in company.soft_profile.news],
                "products": [p.model_dump() for p in company.soft_profile.products],
            }
        try:
            gen = _run_with_budget(
                "内容生成",
                lambda: generate(resume, jd, match, company_ctx),
                settings.timeout_ms("generate"),
                fallback="partial_report",
                force=settings.mock_force_timeout == "generate",
            )
        except ToolError as exc:
            if exc.code != TIMEOUT:
                raise
            # 02 第 4 节：单段超时不许让整份报告空白，出部分报告 + 失败原因 + 重试入口
            partial = True
            reason = "生成步骤超时（自我介绍/面试题/知识点未生成），可重试；匹配与公司背调结果仍然有效"
            degradations.append(reason)
            gen = GenResult(
                self_intro={
                    "30s": "（未生成：生成步骤超时，请重试）",
                    "60s": "（未生成：生成步骤超时，请重试）",
                    "120s": "（未生成：生成步骤超时，请重试）",
                    "anchors": [],
                    "degraded": True,
                    "note": reason,
                },
                questions=[],
                knowledge=[],
                action_plan={
                    "before_apply": ["生成步骤超时，投递前建议先按第 3 节匹配表逐条核对缺口"],
                    "before_interview": ["重试生成后再制定补知识顺序"],
                    "in_interview_defense": [],
                    "questions_to_ask": [],
                    "after_interview": ["重试生成后补充跟进清单"],
                },
                to_verify=[reason, "自我介绍锚点缺失：生成超时，需重试后补齐"],
                degradations=[reason],
            )

    company_name_final = (
        company.company_resolved.name if company is not None and company.company_resolved.name else "待确认公司"
    )
    role_short = jd.role_summary.split("。")[0]
    headline = (
        f"{company_name_final}｜{role_short}：整体判定 {match.verdict_tier}；"
        f"最大亮点是「{match.top_strength.split('（')[0]}」，最大缺口是「{match.top_gap.split('（')[0]}」。"
    )

    report_data = {
        "schema_version": "1.0",
        "analysis_id": analysis_id,
        "data_mode": "mock" if settings.is_mock else "live",
        "verdict": {
            "tier": match.verdict_tier,
            "headline": headline,
            "top_strength": match.top_strength,
            "top_gap": match.top_gap,
        },
        "match": {"dimensions": match.dimensions},
        "self_intro": gen.self_intro,
        "interview_questions": gen.questions,
        "knowledge": gen.knowledge,
        "action_plan": gen.action_plan,
        "sources_and_confidence": _sources_table(resume, jd, company),
        "to_verify": _to_verify_list(resume, company, gen.to_verify, gen.degradations, []),
        "company": company.model_dump() if company is not None else None,
        "jd": jd.model_dump(),
        "resume_meta": {
            "resume_hash": text_hash(str([e.model_dump() for e in resume.experiences])),
            "parsing_mode": resume.parsing_mode,
            "experience_count": len(resume.experiences),
        },
        "generated_at": _now(),
        "degradations": degradations + gen.degradations,
    }

    # 6. 校验 -> 一次修复 -> 仍失败则拒绝输出
    result = validate_report_full(
        report_data, resume.evidence_ids(), jd.all_ids(), resume=resume, company=company,
        data_mode=report_data["data_mode"], partial=partial,
    )
    warnings = result.messages("warning")
    if result.errors:
        logger.warning("validation errors before repair: %s", len(result.errors))
        report_data, repair_notes = _repair_questions(report_data, resume.evidence_ids(), jd.all_ids())
        report_data["to_verify"] = report_data["to_verify"] + repair_notes
        report_data["degradations"] = report_data["degradations"] + repair_notes
        result = validate_report_full(
            report_data, resume.evidence_ids(), jd.all_ids(), resume=resume, company=company,
            data_mode=report_data["data_mode"], partial=partial,
        )
        warnings = result.messages("warning")
    if result.errors:
        raise ToolError(
            code=EVIDENCE_INVALID,
            message="报告未通过证据校验，已停止输出（不允许带着不存在的证据引用交付）。",
            retryable=True,
            fallback="",
            detail={"errors": result.messages("error")},
        )

    try:
        structured = ReportStructured.model_validate(report_data)
    except Exception as exc:
        raise ToolError(
            code=EVIDENCE_INVALID,
            message="报告结构化结果不符合数据契约，已停止输出。",
            retryable=True,
            fallback="",
            detail={"reason": type(exc).__name__},
        ) from exc

    markdown = render_report(structured)
    filename = build_filename(structured)
    card = render_summary_card(structured, filename)

    timings["total"] = sum(v for v in timings.values())
    return AnalysisResult(
        analysis_id=analysis_id,
        structured=structured,
        markdown=markdown,
        filename=filename,
        card=card,
        timings=timings,
        degradations=structured.degradations,
        validation_warnings=warnings,
        resume=resume,
        jd=jd,
        company=company,
    )


def export_markdown(result: AnalysisResult, out_dir: str | Path) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / result.filename
    path.write_text(result.markdown, encoding="utf-8")
    return path
