"""简历解析：SmartResume 适配器 + fallback 规则解析（08 第 5 节选项 1）。

为什么 fallback 是默认路径：
- SmartResume 真实后端要求 ≥8GB 内存 / ≥10GB 存储 / 可选 CUDA（T1.1 已核验 README），
  MVP 不把 GPU 作硬依赖。
- 两条路径的输出必须是同一个 Schema（03 第 3.1 节），切换只改 parsing_mode，不改报告结构。

证据约束：
- 公司、岗位、时间、核心数字只能来自原文，规则解析只做"切分 + 归类"，不做扩写。
- 姓名只进 basic_info，电话与邮箱结构上不落库（basic_info 没有这两个字段），日志只记哈希。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from ..config import Settings
from ..errors import PARSE_FAILED, ToolError
from ..mockdata import MOCK_SCHEME  # noqa: F401  (保持 mock 语义常量在同处定义)
from ..schemas import ResumeStructured
from .text_extract import ExtractionResult, extract_text

SECTION_KEYWORDS = {
    "education": ("教育背景", "教育经历", "学历背景", "教育"),
    "work": ("工作经历", "实习经历", "职业经历", "工作经验", "实习经验"),
    "project": ("项目经历", "项目经验", "实践经历"),
    "skill": ("技能", "专业技能", "技能证书", "技能特长"),
}

DATE_RANGE_RE = re.compile(
    r"(\d{4}\s*[.\-/年]\s*\d{1,2})\s*[-–—~至]\s*(\d{4}\s*[.\-/年]\s*\d{1,2}|至今|现在|今)"
)
# 单位表要覆盖简历里真实出现的量词。早期只收了"人/家/条"这类，
# 导致"3 版改写建议""30 位同学试用""4.2 分"这些明确成果被判成"无量化成果"，
# 进而把自我介绍锚点压到 3 条以下（A4 会因此降级）。
METRIC_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(%|％|万|亿|人|家|条|场|倍|个|天|小时|分钟|元|次|份|组|张"
    r"|版|位|名|篇|页|款|项|套|台|轮|届|所|城|店|户|单|笔|秒|分|月|周|年|日)"
)
PHONE_RE = re.compile(r"1[3-9]\d[\d\-\s]{7,11}")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
URL_RE = re.compile(r"https?://[^\s，。；、）)]+")
BULLET_PREFIX_RE = re.compile(r"^\s*(?:[-–—•·*]|\d{1,2}[.、)]\s+|[（(]\d{1,2}[）)])\s*")
SPLIT_RE = re.compile(r"\s{2,}|\t+|\s*[|｜]\s*")


def _is_section_header(line: str) -> str | None:
    stripped = line.strip().strip("：:")
    for key, words in SECTION_KEYWORDS.items():
        for word in words:
            if stripped == word or (stripped.startswith(word) and len(stripped) <= len(word) + 2):
                return key
    return None


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip(" -–—•·*|\t")


def _extract_metrics(bullets: list[str]) -> list[dict]:
    metrics: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for bullet in bullets:
        for match in METRIC_RE.finditer(bullet):
            raw_num, unit = match.group(1), match.group(2).replace("％", "%")
            value = f"{raw_num}{unit}"
            key = (value, bullet)
            if key in seen:
                continue
            seen.add(key)
            metrics.append({"value": value, "context": bullet})
    return metrics


def _split_header(rest: str) -> tuple[str | None, str | None]:
    parts = [p for p in SPLIT_RE.split(rest.strip()) if p.strip()]
    if len(parts) >= 2:
        return _clean(parts[0]), _clean(parts[1])
    if len(parts) == 1 and " " in parts[0]:
        left, right = parts[0].rsplit(" ", 1)
        return _clean(left), _clean(right)
    return (_clean(parts[0]) if parts else None), None


@dataclass
class _Block:
    header: str
    period: str | None = None
    name: str | None = None
    role: str | None = None
    bullets: list[str] = field(default_factory=list)


def _parse_blocks(lines: list[str]) -> list[_Block]:
    """把一段经历/项目文本切成块：块头 = 含时间区间或"公司 + 岗位"的短行。"""
    blocks: list[_Block] = []
    current: _Block | None = None
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        date_match = DATE_RANGE_RE.search(line)
        # 顺序很重要：日期区间行必须先于列表项判断，否则 "2025.07-2025.09 ..." 会被当成编号列表
        if date_match:
            rest = (line[: date_match.start()] + " " + line[date_match.end():]).strip()
            left, right = _split_header(rest)
            current = _Block(
                header=line,
                period=f"{date_match.group(1).replace(' ', '')}-{date_match.group(2).replace(' ', '')}",
                name=left,
                role=right,
            )
            blocks.append(current)
            continue
        is_bullet = bool(BULLET_PREFIX_RE.match(line))
        if is_bullet:
            if current is None:
                continue
            current.bullets.append(_clean(BULLET_PREFIX_RE.sub("", line)))
            continue
        # 没有时间区间的短行：如果上一块已经有 bullet，视为新块头（无 period）
        if current is None or (len(line) <= 42 and current.bullets):
            left, right = _split_header(line)
            current = _Block(header=line, name=left, role=right)
            blocks.append(current)
            continue
        if current is not None:
            current.bullets.append(_clean(line))
    return blocks


class FallbackResumeParser:
    """规则解析：只归类与切分，不扩写、不补数字。"""

    name = "fallback"

    def parse(self, extraction: ExtractionResult, resume_id: str = "") -> dict:
        text = extraction.text or ""
        lines = [ln for ln in text.splitlines()]
        notes: list[str] = list(extraction.notes)

        # 1. 切段落
        sections: dict[str, list[str]] = {k: [] for k in SECTION_KEYWORDS}
        head: list[str] = []
        current_key: str | None = None
        for line in lines:
            key = _is_section_header(line)
            if key:
                current_key = key
                continue
            if current_key:
                sections[current_key].append(line)
            else:
                head.append(line)

        # 2. basic_info（电话/邮箱只用于识别，不写入结构）
        name = None
        title = None
        location = None
        links: list[str] = []
        for line in head:
            stripped = line.strip()
            if not stripped:
                continue
            if name is None and not _is_section_header(stripped):
                candidate = re.sub(r"[（(].*?[）)]", "", stripped).strip()
                if (
                    candidate
                    and len(candidate) <= 16
                    and not PHONE_RE.search(candidate)
                    and not EMAIL_RE.search(candidate)
                    and not any(k in candidate for k in ("简历", "求职", "应聘", "@"))
                ):
                    name = candidate
            if "求职意向" in stripped or "意向岗位" in stripped or "应聘岗位" in stripped:
                title = re.split(r"[：:]", stripped, maxsplit=1)[-1].strip() or None
            for kw in ("现居", "居住地", "所在城市", "城市"):
                if kw in stripped:
                    location = re.split(r"[：:]", stripped, maxsplit=1)[-1].strip() or None
            links.extend(URL_RE.findall(stripped))
            if EMAIL_RE.search(stripped) or PHONE_RE.search(stripped):
                notes.append("已识别到联系方式，按隐私规范仅用于解析判断，不写入结构化结果")

        # 3. 教育
        education = []
        for line in sections["education"]:
            date_match = DATE_RANGE_RE.search(line)
            parts = [p for p in SPLIT_RE.split(line.strip()) if p.strip()]
            if date_match:
                rest = (line[: date_match.start()] + "  " + line[date_match.end():]).strip()
                parts = [p for p in SPLIT_RE.split(rest) if p.strip()]
            if not parts or (len(parts) == 1 and not date_match):
                continue
            if len(parts) == 1 and " " in parts[0]:
                parts = parts[0].split()
            education.append(
                {
                    "school": _clean(parts[0]) if parts else None,
                    "major": _clean(parts[1]) if len(parts) > 1 else None,
                    "degree": _clean(parts[2]) if len(parts) > 2 else None,
                    "period": (
                        f"{date_match.group(1).replace(' ', '')}-{date_match.group(2).replace(' ', '')}"
                        if date_match
                        else None
                    ),
                }
            )

        # 4. 工作/实习经历
        experiences = []
        for idx, block in enumerate(_parse_blocks(sections["work"]), start=1):
            if not block.bullets:
                continue
            experiences.append(
                {
                    "id": f"exp_{idx:02d}",
                    "company": block.name,
                    "role": block.role,
                    "period": block.period,
                    "bullets": block.bullets,
                    "metrics": _extract_metrics(block.bullets),
                }
            )
        if not experiences:
            notes.append("未识别到工作/实习经历段落，相关结论将标注为无证据")

        # 5. 项目
        projects = []
        for idx, block in enumerate(_parse_blocks(sections["project"]), start=1):
            if not block.bullets:
                continue
            projects.append(
                {
                    "id": f"proj_{idx:02d}",
                    "name": block.name or block.header,
                    "bullets": block.bullets,
                    "metrics": _extract_metrics(block.bullets),
                }
            )

        # 6. 技能
        skills: list[str] = []
        for line in sections["skill"]:
            for token in re.split(r"[、，,；;/]| {2,}", line.strip()):
                token = _clean(token)
                if token and len(token) <= 24 and not _is_section_header(token):
                    skills.append(token)

        if extraction.is_scanned:
            notes.append("扫描件/图片简历：字段可能缺失，报告中标记为待核实")

        return {
            "schema_version": "1.0",
            "parsing_mode": "fallback",
            "basic_info": {"name": name, "title": title, "location": location, "links": links},
            "education": education,
            "experiences": experiences,
            "projects": projects,
            "skills": skills,
            "parsing_notes": notes,
            "data_mode": "mock",
        }


class SmartResumeBackend:
    """SmartResume 适配器：只按上游 README 的公开签名调用，不复制上游代码。"""

    name = "smartresume"

    # 上游 README / 08_ENVIRONMENT 第 5 节给出的最低要求。本机不满足，因此真实解析**未实测**，
    # 只按契约写了字段映射；这一条在 v2 Phase 0 必须复核（见 docs/ENV_FEASIBILITY.md）。
    HARDWARE_MIN = {
        "ram_gb": 8,
        "disk_gb": 10,
        "gpu": "非必需但强烈建议（CUDA）；OCR + 本地 LLM 推理在无 GPU 时耗时不可接受",
        "verified": False,
    }

    def __init__(self, settings: Settings):
        self.settings = settings

    def unavailable_reason(self) -> str:
        """为什么没走 SmartResume。空串表示可用。"""
        if self.settings.is_mock:
            return "Mock 模式不加载 SmartResume 本地模型，按设计走 fallback 解析"
        try:
            import smartresume  # noqa: F401
        except Exception as exc:
            return f"未安装 smartresume 包（{type(exc).__name__}），已走 fallback 解析"
        return ""

    def available(self) -> bool:
        return not self.unavailable_reason()

    def parse(self, path: Path, resume_id: str, extract_types: list[str]) -> dict:
        from smartresume import ResumeAnalyzer  # 上游 README: from smartresume import ResumeAnalyzer

        analyzer = ResumeAnalyzer(init_ocr=True, init_llm=True)
        raw = analyzer.pipeline(cv_path=str(path), resume_id=resume_id, extract_types=extract_types)
        if not isinstance(raw, dict):
            raise ToolError(
                code=PARSE_FAILED,
                message="SmartResume 返回类型不是 dict，已降级为 fallback 解析。",
                retryable=True,
                fallback="fallback",
            )
        return self._normalize(raw)

    def _normalize(self, raw: dict) -> dict:
        """把上游字段映射到 03 契约。字段名是**按契约推测的映射**，未实测（见 FORK_LOCK 1.1）。"""
        work = raw.get("work_experience") or raw.get("experiences") or []
        experiences = []
        for idx, item in enumerate(work, start=1):
            bullets = item.get("bullets") or item.get("description") or []
            if isinstance(bullets, str):
                bullets = [bullets]
            experiences.append(
                {
                    "id": f"exp_{idx:02d}",
                    "company": item.get("company") or item.get("company_name"),
                    "role": item.get("role") or item.get("position") or item.get("title"),
                    "period": item.get("period") or item.get("duration"),
                    "bullets": [str(b) for b in bullets],
                    "metrics": item.get("metrics") or _extract_metrics([str(b) for b in bullets]),
                }
            )
        projects = []
        for idx, item in enumerate(raw.get("projects") or [], start=1):
            bullets = item.get("bullets") or item.get("description") or []
            if isinstance(bullets, str):
                bullets = [bullets]
            projects.append(
                {
                    "id": f"proj_{idx:02d}",
                    "name": item.get("name") or item.get("title"),
                    "bullets": [str(b) for b in bullets],
                    "metrics": item.get("metrics") or _extract_metrics([str(b) for b in bullets]),
                }
            )
        return {
            "schema_version": "1.0",
            "parsing_mode": "smartresume",
            "basic_info": raw.get("basic_info") or {"name": None, "title": None, "location": None, "links": []},
            "education": raw.get("education") or [],
            "experiences": experiences,
            "projects": projects,
            "skills": raw.get("skills") or [],
            "parsing_notes": ["SmartResume 后端解析；字段映射按契约实现，真实效果未实测（见 docs/FORK_LOCK.md）"],
            "data_mode": "live",
        }


EXTRACT_TYPES_DEFAULT = ["basic_info", "education", "work_experience", "projects", "skills"]


def parse_resume(
    file_path: str | Path,
    settings: Settings,
    resume_id: str = "",
    extract_types: list[str] | None = None,
) -> ResumeStructured:
    """解析入口：优先 SmartResume，失败/不可用则 fallback，最后统一过 Schema 校验。"""
    path = Path(file_path)
    extraction = extract_text(path)
    backend = SmartResumeBackend(settings)
    fallback = FallbackResumeParser()

    data: dict | None = None
    if backend.available():
        try:
            data = backend.parse(path, resume_id or path.stem, extract_types or EXTRACT_TYPES_DEFAULT)
        except Exception:  # 上游任何异常都不许冒泡成 500
            data = None

    if data is None:
        if not extraction.text.strip():
            # 没有任何可用文本：返回空结构 + 明确说明，而不是编内容
            data = {
                "schema_version": "1.0",
                "parsing_mode": "fallback",
                "basic_info": {"name": None, "title": None, "location": None, "links": []},
                "education": [],
                "experiences": [],
                "projects": [],
                "skills": [],
                "parsing_notes": extraction.notes + ["未能提取到任何文本，结构化结果为空，请改用文本版简历"],
                "data_mode": "mock" if settings.is_mock else "live",
            }
        else:
            data = fallback.parse(extraction, resume_id)
            if not settings.is_mock:
                data["data_mode"] = "live"
        # 把"为什么没走 SmartResume"写进解析说明：用户看到的是 fallback 结果，
        # 但报告里必须能解释这不是模型解析，避免把规则解析说成模型能力。
        reason = backend.unavailable_reason()
        if reason:
            data.setdefault("parsing_notes", []).append(reason)

    try:
        return ResumeStructured.model_validate(data)
    except Exception as exc:
        # 结构不合契约时不许向上传：退回 fallback，再不行就报 PARSE_FAILED
        if data.get("parsing_mode") == "smartresume" and extraction.text.strip():
            try:
                return ResumeStructured.model_validate(fallback.parse(extraction, resume_id))
            except Exception:
                pass
        raise ToolError(
            code=PARSE_FAILED,
            message="简历结构化结果不符合数据契约，已停止向上游返回。",
            retryable=True,
            fallback="",
            detail={"reason": type(exc).__name__},
        ) from exc
