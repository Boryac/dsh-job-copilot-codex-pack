"""数据契约的 Pydantic 模型，与插件层 TypeScript 类型（src/contracts.ts）一一对应。

规则：
- 字段名、枚举值、ID 格式必须与 03 一致；不一致 = bug，不是"文档滞后"。
- 硬数据字段结构上不允许出现 inferred 字段（extra="forbid"），从根上杜绝推断写进 hard_data。
- 所有 LLM 生成的推断字段用 Literal[True] 强制 `inferred: true`，漏了就校验失败。
"""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION = "1.0"
EXP_ID_RE = re.compile(r"^exp_\d{2,3}$")
PROJ_ID_RE = re.compile(r"^proj_\d{2,3}$")
JD_ID_RE = re.compile(r"^jd_\d{2,3}$")
Q_ID_RE = re.compile(r"^q_\d{2,3}$")
K_ID_RE = re.compile(r"^k_\d{2,3}$")

Tier = Literal["strong", "discussable", "gap"]
Depth = Literal["basic", "deep"]
DataMode = Literal["mock", "live"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, str_strip_whitespace=True)


# --------------------------------------------------------------------------- 3.1 简历


class Metric(StrictModel):
    value: str
    context: str


class BasicInfo(StrictModel):
    name: str | None = None
    title: str | None = None
    location: str | None = None
    links: list[str] = Field(default_factory=list)


class EducationItem(StrictModel):
    school: str | None = None
    major: str | None = None
    degree: str | None = None
    period: str | None = None


class Experience(StrictModel):
    id: str
    company: str | None = None
    role: str | None = None
    period: str | None = None
    bullets: list[str] = Field(default_factory=list)
    metrics: list[Metric] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def _check_id(cls, v: str) -> str:
        if not EXP_ID_RE.match(v):
            raise ValueError(f"经历 ID 必须形如 exp_01，实际 {v!r}")
        return v


class Project(StrictModel):
    id: str
    name: str | None = None
    bullets: list[str] = Field(default_factory=list)
    metrics: list[Metric] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def _check_id(cls, v: str) -> str:
        if not PROJ_ID_RE.match(v):
            raise ValueError(f"项目 ID 必须形如 proj_01，实际 {v!r}")
        return v


class ResumeStructured(StrictModel):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    parsing_mode: Literal["smartresume", "fallback"]
    basic_info: BasicInfo
    education: list[EducationItem] = Field(default_factory=list)
    experiences: list[Experience] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    parsing_notes: list[str] = Field(default_factory=list)
    data_mode: DataMode = "mock"

    @model_validator(mode="after")
    def _ids_unique_and_continuous(self) -> "ResumeStructured":
        ids = [e.id for e in self.experiences]
        if len(set(ids)) != len(ids):
            raise ValueError("经历 ID 必须唯一")
        expected = [f"exp_{i:02d}" for i in range(1, len(ids) + 1)]
        if ids != expected:
            raise ValueError(f"经历 ID 必须连续，期望 {expected}，实际 {ids}")
        pids = [p.id for p in self.projects]
        if len(set(pids)) != len(pids):
            raise ValueError("项目 ID 必须唯一")
        return self

    def experience_ids(self) -> set[str]:
        return {e.id for e in self.experiences}

    def project_ids(self) -> set[str]:
        return {p.id for p in self.projects}

    def evidence_ids(self) -> set[str]:
        return self.experience_ids() | self.project_ids()

    def metrics_map(self) -> dict[str, list[Metric]]:
        out: dict[str, list[Metric]] = {e.id: list(e.metrics) for e in self.experiences}
        for p in self.projects:
            out[p.id] = list(p.metrics)
        return out


# --------------------------------------------------------------------- 3.2 公司背调


class DisambiguationCandidate(StrictModel):
    name: str
    unified_credit_code: str | None = None
    region: str | None = None
    legal_representative: str | None = None
    match_reason: str = ""
    score: float | None = None


class Disambiguation(StrictModel):
    candidates: list[DisambiguationCandidate] = Field(default_factory=list)
    chosen_reason: str = ""
    needs_user_confirm: bool = False


class CompanyResolved(StrictModel):
    name: str | None = None
    unified_credit_code: str | None = None
    disambiguation: Disambiguation = Field(default_factory=Disambiguation)


class HardField(StrictModel):
    """硬数据字段：结构上只有 value/verified/source，没有 inferred 的位置。"""

    value: str | int | float | None = None
    verified: bool = False
    source: str = ""


class HardData(StrictModel):
    founded_at: HardField = Field(default_factory=HardField)
    registered_capital: HardField = Field(default_factory=HardField)
    legal_representative: HardField = Field(default_factory=HardField)
    business_scope: HardField = Field(default_factory=HardField)
    registered_address: HardField | None = None
    status: HardField | None = None

    def fields(self) -> dict[str, HardField]:
        out = {
            "founded_at": self.founded_at,
            "registered_capital": self.registered_capital,
            "legal_representative": self.legal_representative,
            "business_scope": self.business_scope,
        }
        if self.registered_address is not None:
            out["registered_address"] = self.registered_address
        if self.status is not None:
            out["status"] = self.status
        return out


class Product(StrictModel):
    name: str
    users: str | None = None
    revenue_model: str | None = None
    relation_to_role: str | None = None
    source_urls: list[str] = Field(default_factory=list)


class NewsItem(StrictModel):
    title: str
    date: str | None = None
    url: str = ""
    summary: str = ""


class FinancingItem(StrictModel):
    round: str | None = None
    date: str | None = None
    amount: str | None = None
    source_urls: list[str] = Field(default_factory=list)


class SoftProfile(StrictModel):
    products: list[Product] = Field(default_factory=list)
    news: list[NewsItem] = Field(default_factory=list)
    financing: list[FinancingItem] = Field(default_factory=list)
    hiring_signals: list[str] = Field(default_factory=list)
    inferred: Literal[True] = True
    source_urls: list[str] = Field(default_factory=list)


class QuotaDetail(StrictModel):
    api: str
    calls: int = 0
    cost: float = 0.0
    at: str = ""
    mock: bool = True


class QuotaConsumed(StrictModel):
    tianyancha_calls: int = 0
    tianyancha_detail: list[QuotaDetail] = Field(default_factory=list)
    search_calls: int = 0


class CacheMeta(StrictModel):
    hit: bool = False
    fetched_at: str | None = None
    # 缓存版本：让"这条结果是哪个版本的逻辑产出的"可被审计，旧版本命中不了新逻辑
    version: str | None = None


class CompanyRecon(StrictModel):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    company_input: str
    company_resolved: CompanyResolved
    hard_data: HardData
    soft_profile: SoftProfile
    deep_data: dict | None = None
    depth_used: Depth = "basic"
    quota_consumed: QuotaConsumed = Field(default_factory=QuotaConsumed)
    fetched_at: str = ""
    data_mode: DataMode = "mock"
    cache: CacheMeta = Field(default_factory=CacheMeta)
    degradations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _deep_needs_data(self) -> "CompanyRecon":
        if self.depth_used == "deep" and self.deep_data is None:
            raise ValueError("depth_used=deep 时 deep_data 不许为空")
        return self


class DeepEstimate(StrictModel):
    """deep 路径的预估卡片（05 第 3 节）：确认前零调用。"""

    needs_confirmation: Literal[True] = True
    company_input: str
    fields: list[str] = Field(default_factory=list)
    estimate: dict = Field(default_factory=dict)
    quota_consumed: QuotaConsumed = Field(default_factory=QuotaConsumed)
    idempotency_key: str = ""
    note: str = ""


# ------------------------------------------------------------------------ 3.3 JD


class JdItem(StrictModel):
    id: str
    text: str
    type: Literal["hard", "soft"]

    @field_validator("id")
    @classmethod
    def _check_id(cls, v: str) -> str:
        if not JD_ID_RE.match(v):
            raise ValueError(f"JD ID 必须形如 jd_01，实际 {v!r}")
        return v


class JdResponsibility(StrictModel):
    id: str
    text: str

    @field_validator("id")
    @classmethod
    def _check_id(cls, v: str) -> str:
        if not JD_ID_RE.match(v):
            raise ValueError(f"JD ID 必须形如 jd_01，实际 {v!r}")
        return v


class JdInference(StrictModel):
    text: str
    evidence_sentence_ids: list[str] = Field(default_factory=list)
    inferred: Literal[True] = True


class JdSentence(StrictModel):
    id: str
    text: str


class JdDecoded(StrictModel):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    source_type: Literal["pasted_text", "url"]
    must_have: list[JdItem] = Field(default_factory=list)
    nice_to_have: list[JdItem] = Field(default_factory=list)
    responsibilities: list[JdResponsibility] = Field(default_factory=list)
    hidden_priorities: list[JdInference] = Field(default_factory=list)
    red_flags: list[JdInference] = Field(default_factory=list)
    role_summary: str = ""
    sentences: list[JdSentence] = Field(default_factory=list)
    data_mode: DataMode = "mock"

    @model_validator(mode="after")
    def _ids_unique(self) -> "JdDecoded":
        ids = [i.id for i in self.must_have] + [i.id for i in self.nice_to_have] + [
            i.id for i in self.responsibilities
        ]
        if len(set(ids)) != len(ids):
            raise ValueError("JD 要求 ID 必须全局唯一")
        return self

    def requirement_ids(self) -> set[str]:
        return {i.id for i in self.must_have} | {i.id for i in self.nice_to_have}

    def all_ids(self) -> set[str]:
        return self.requirement_ids() | {i.id for i in self.responsibilities}


# ------------------------------------------------------------- 3.4 报告结构化版

DIMENSION_NAMES = ("硬性条件", "职责匹配", "履历证据", "加分项")
CATEGORIES = ("动机", "经历深挖", "岗位认知", "协作与稳定性")


class Verdict(StrictModel):
    tier: Tier
    headline: str
    top_strength: str
    top_gap: str


class Dimension(StrictModel):
    name: Literal["硬性条件", "职责匹配", "履历证据", "加分项"]
    tier: Tier
    evidence_refs: list[str] = Field(default_factory=list)
    note: str = ""
    # 该维度下方展开的证据行（JD 要求 | 简历证据 | 差距 | 可能追问）
    rows: list[dict] = Field(default_factory=list)


class MatchBlock(StrictModel):
    dimensions: list[Dimension] = Field(default_factory=list)


class StarAnswer(StrictModel):
    situation: str = ""
    task: str = ""
    action: str = ""
    result: str = ""


class InterviewQuestion(StrictModel):
    id: str
    category: Literal["动机", "经历深挖", "岗位认知", "协作与稳定性"]
    question: str
    focus: str
    evidence_ref: str
    star_answer: StarAnswer = Field(default_factory=StarAnswer)
    follow_up: str = ""
    pitfall: str = ""
    knowledge_refs: list[str] = Field(default_factory=list)
    evidence_status: Literal["verified", "degraded"] = "verified"

    @field_validator("id")
    @classmethod
    def _check_id(cls, v: str) -> str:
        if not Q_ID_RE.match(v):
            raise ValueError(f"面试题 ID 必须形如 q_01，实际 {v!r}")
        return v


class SelfIntro(StrictModel):
    s30: str = Field(alias="30s")
    s60: str = Field(alias="60s")
    s120: str = Field(alias="120s")
    anchors: list[str] = Field(default_factory=list)
    degraded: bool = False
    note: str | None = None


class KnowledgeItem(StrictModel):
    id: str
    level: Literal["must", "bonus", "frequent"]
    term: str
    definition: str
    resume_example_ref: str | None = None
    likely_follow_up: str = ""

    @field_validator("id")
    @classmethod
    def _check_id(cls, v: str) -> str:
        if not K_ID_RE.match(v):
            raise ValueError(f"知识点 ID 必须形如 k_01，实际 {v!r}")
        return v


class ActionPlan(StrictModel):
    before_apply: list[str] = Field(default_factory=list)
    before_interview: list[str] = Field(default_factory=list)
    in_interview_defense: list[str] = Field(default_factory=list)
    questions_to_ask: list[str] = Field(default_factory=list)
    after_interview: list[str] = Field(default_factory=list)


class SourceItem(StrictModel):
    item: str
    source: str
    confidence: Literal["verified", "inferred", "unverified"]
    fetched_at: str | None = None


class ResumeMeta(StrictModel):
    resume_hash: str
    parsing_mode: Literal["smartresume", "fallback"]
    experience_count: int = 0


class ReportStructured(StrictModel):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    analysis_id: str
    data_mode: DataMode = "mock"
    verdict: Verdict
    match: MatchBlock
    self_intro: SelfIntro
    interview_questions: list[InterviewQuestion] = Field(default_factory=list)
    knowledge: list[KnowledgeItem] = Field(default_factory=list)
    action_plan: ActionPlan = Field(default_factory=ActionPlan)
    sources_and_confidence: list[SourceItem] = Field(default_factory=list)
    to_verify: list[str] = Field(default_factory=list)
    company: CompanyRecon | None = None
    jd: JdDecoded | None = None
    resume_meta: ResumeMeta | None = None
    generated_at: str = ""
    degradations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _four_dimensions(self) -> "ReportStructured":
        names = [d.name for d in self.match.dimensions]
        if sorted(names) != sorted(DIMENSION_NAMES):
            raise ValueError(f"人岗匹配必须且只能是四维 {DIMENSION_NAMES}，实际 {names}")
        return self

    def jd_and_exp_refs(self) -> tuple[set[str], set[str]]:
        exp_ids = set()
        jd_ids = set()
        if self.resume_meta is None:
            return exp_ids, jd_ids
        return exp_ids, jd_ids


class SummaryCard(StrictModel):
    """DSH 内的摘要卡片（04 第 0 节），不是完整报告。"""

    analysis_id: str
    verdict_tier: Tier
    headline: str
    top_strength: str
    top_gap: str
    recommended_action: str
    company_name: str | None = None
    depth: Depth = "basic"
    parsing_mode: str | None = None
    generated_at: str = ""
    report_filename: str = ""
    sections: list[dict] = Field(default_factory=list)
    degradations: list[str] = Field(default_factory=list)
    data_mode: DataMode = "mock"
