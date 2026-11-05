"""JD 拆解：粘贴文本为主路径，URL 为辅。

规则（03 第 3.3 节 / 05 第 5 节 / 11 第 1 节）：
- must_have / nice_to_have / responsibilities 的 text 必须能在原文里找到对应句子，找不到 = PARSE_FAILED。
- hidden_priorities / red_flags 永远是推断，结构上强制 inferred=true。
- URL 抓取失败必须明确提示用户粘贴，不许用残缺内容静默继续。
"""
from __future__ import annotations

import re
import urllib.error
import urllib.request

from ..config import Settings
from ..errors import INVALID_INPUT, PARSE_FAILED, URL_FETCH_FAILED, ToolError
from ..schemas import JdDecoded

RESP_HEADERS = ("岗位职责", "工作职责", "职责描述", "职位职责", "你将负责", "工作内容", "主要职责")
REQ_HEADERS = ("任职要求", "岗位要求", "职位要求", "任职资格", "我们希望你", "任职条件", "岗位需求")
# 加分项必须是独立段落：之前没有这组标题，"加分项：" 被当成纯标题行跳过，
# 段内条目因为含"经验"被归进 must_have，等于把加分项当成硬性要求，硬性条件档位被压低。
NICE_HEADERS = ("加分项", "加分条件", "优先条件", "额外加分", "以下条件优先", "nice to have")

RESP_CUES = ("负责", "推动", "协同", "维护", "搭建", "输出", "跟进", "落地", "完成")
REQ_CUES = ("以上学历", "熟练", "具备", "掌握", "熟悉", "经验", "能力", "优先", "专业")

NICE_CUES = ("优先", "加分", "更好", "plus")

# 这些是 JD 的元信息行，不是"要求"，混进 must_have 会污染匹配
META_PREFIXES = (
    "岗位名称", "职位名称", "工作地点", "薪资范围", "薪资", "招聘人数", "学历要求",
    "经验要求", "公司名称", "所属部门", "汇报对象", "职位类别", "工作性质", "到岗时间", "岗位级别",
)

NUM_PREFIX_RE = re.compile(r"^\s*(?:\d+[.、)）]|[（(]\d+[）)]|[-–—•·*])\s*")
MIN_ITEM_CHARS = 4


def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def _sentences(text: str) -> list[str]:
    """先按行切，再按中文句号/分号切，保留可追溯到原文的短句。"""
    out: list[str] = []
    for line in (text or "").splitlines():
        line = NUM_PREFIX_RE.sub("", line.strip())
        if not line:
            continue
        for piece in re.split(r"[。；;]", line):
            piece = piece.strip(" ，,、")
            if len(piece) >= MIN_ITEM_CHARS:
                out.append(piece)
    return out


def _classify(pieces: list[str]) -> tuple[list[str], list[str], list[str]]:
    """返回 (must, nice, responsibilities)，保持原文顺序。"""
    must: list[str] = []
    nice: list[str] = []
    resp: list[str] = []
    section: str | None = None
    for raw in (p.strip() for p in pieces):
        if not raw:
            continue
        if any(h in raw for h in RESP_HEADERS) and len(raw) <= len("岗位职责：") + 12:
            section = "resp"
            continue
        if any(h in raw.lower() for h in NICE_HEADERS) and len(raw) <= len("加分项：") + 12:
            section = "nice"
            continue
        if any(h in raw for h in REQ_HEADERS) and len(raw) <= len("任职要求：") + 12:
            section = "req"
            continue
        if raw.endswith("：") or raw.endswith(":"):
            continue  # 纯标题行
        if any(raw.startswith(p) for p in META_PREFIXES) and len(raw) <= 40:
            continue  # 元信息（岗位名称/地点/薪资…）不是任职要求
        is_resp = any(cue in raw for cue in RESP_CUES) and not any(c in raw for c in ("以上学历", "优先"))
        is_req = any(cue in raw for cue in REQ_CUES)
        # "2 年以上经验，有 OTA 行业经验者优先" 这种句子，年限是硬门槛，不能因为句尾"优先"
        # 就整句降级成加分项 —— 那会让报告把硬性要求写成"加分项"，属于事实错误。
        hard_threshold = bool(re.search(r"以上学历|\d+\s*年以上|应届|届别", raw))
        soft = any(c in raw for c in NICE_CUES) and not hard_threshold
        if section == "nice":
            nice.append(raw)
        elif section == "resp":
            resp.append(raw)
        elif section == "req":
            (nice if soft else must).append(raw)
        elif is_req and not is_resp:
            (nice if soft else must).append(raw)
        elif is_resp:
            resp.append(raw)
        elif raw:
            must.append(raw)
    return must, nice, resp


def _hidden_priorities(must: list[str], resp: list[str], ids: dict[str, str]) -> list[dict]:
    out: list[dict] = []
    joined_resp = "；".join(resp)
    joined_req = "；".join(must)
    if "抗压" in joined_req and ("月度" in joined_resp or "目标" in joined_resp):
        ev = [ids[t] for t in resp if "目标" in t][:2] + [ids[t] for t in must if "抗压" in t][:1]
        out.append({"text": "JD 同时强调月度目标与抗压能力，实际考核偏结果导向，可能伴随高频外勤", "evidence_sentence_ids": ev})
    if "资源" in joined_req:
        ev = [ids[t] for t in must if "资源" in t][:2]
        out.append({"text": "明确提到资源，说明公司更希望候选人带来现成商户/客户渠道，而不只是执行能力", "evidence_sentence_ids": ev})
    if "数据" in joined_resp:
        ev = [ids[t] for t in resp if "数据" in t][:2]
        out.append({"text": "职责里出现数据分析要求，说明该岗位不只是跑客户，还要能自己看数、讲清经营结论", "evidence_sentence_ids": ev})
    if len(resp) >= 4 and "协同" in joined_resp:
        out.append({"text": "职责横跨拓展、运营、市场协同，岗位边界可能较宽，需确认 KPI 归属", "evidence_sentence_ids": [ids[t] for t in resp[:3]]})
    return out


def _red_flags(text: str, must: list[str], resp: list[str], ids: dict[str, str]) -> list[dict]:
    out: list[dict] = []
    joined = "；".join(must)
    if re.search(r"(\d+)\s*年以上", joined):
        ev = [ids[t] for t in must if re.search(r"(\d+)\s*年以上", t)]
        out.append({"text": "明确要求工作年限，应届或实习转正候选人可能被卡简历关，需提前确认是否接受等价实习经历", "evidence_sentence_ids": ev})
    if "薪资" in text and "提成" not in text:
        out.append({"text": "JD 给了薪资区间但未说明提成与 KPI 权重，收入结构存在不确定性，建议面试确认", "evidence_sentence_ids": []})
    if "抗压" in joined:
        out.append({"text": "把抗压写进硬性要求，通常意味着加班或强考核，需在面试中确认实际工作节奏", "evidence_sentence_ids": [ids[t] for t in must if "抗压" in t]})
    if "面议" in text:
        out.append({"text": "薪资面议，薪酬透明度低", "evidence_sentence_ids": []})
    return out


def _role_summary(title: str | None, location: str | None, resp: list[str]) -> str:
    head = " / ".join([x for x in (title, location) if x]) or "未标注岗位名称"
    core = "；".join(resp[:2]) if resp else "JD 未给出明确职责"
    return f"{head}。核心职责：{core}"


def decode_pasted_text(text: str, settings: Settings) -> JdDecoded:
    if not text or len(_normalize(text)) < 20:
        raise ToolError(
            code=INVALID_INPUT,
            message="JD 文本太短（少于 20 字），无法拆解。请粘贴完整的岗位描述。",
            retryable=True,
            fallback="",
        )

    pieces = _sentences(text)
    must, nice, resp = _classify(pieces)

    if not must and not resp:
        raise ToolError(
            code=PARSE_FAILED,
            message="未从 JD 中识别出职责或要求段落，请确认粘贴的是完整 JD。",
            retryable=True,
            fallback="",
        )

    ids: dict[str, str] = {}
    counter = 0
    must_items, nice_items, resp_items, sentences = [], [], [], []
    for item_text in must:
        counter += 1
        jid = f"jd_{counter:02d}"
        ids[item_text] = jid
        must_items.append({"id": jid, "text": item_text, "type": "hard"})
        sentences.append({"id": jid, "text": item_text})
    for item_text in nice:
        counter += 1
        jid = f"jd_{counter:02d}"
        ids[item_text] = jid
        nice_items.append({"id": jid, "text": item_text, "type": "soft"})
        sentences.append({"id": jid, "text": item_text})
    for item_text in resp:
        counter += 1
        jid = f"jd_{counter:02d}"
        ids[item_text] = jid
        resp_items.append({"id": jid, "text": item_text})
        sentences.append({"id": jid, "text": item_text})

    # 可追溯性自检：每条 text 必须能在原文里找到（去空白后子串或高重合）
    source = _normalize(text)
    for item in must_items + nice_items + resp_items:
        needle = _normalize(item["text"])
        if not needle:
            raise ToolError(code=PARSE_FAILED, message="JD 拆解产生了空条目，已停止。", retryable=True)
        if needle not in source:
            overlap = len(set(needle) & set(source)) / max(len(set(needle)), 1)
            if overlap < 0.9:
                raise ToolError(
                    code=PARSE_FAILED,
                    message="JD 拆解出的条目无法追溯到原文，已停止（防止编造要求）。",
                    retryable=True,
                    fallback="",
                    detail={"item": item["id"]},
                )

    title = None
    location = None
    for line in text.splitlines():
        if "岗位名称" in line or "职位名称" in line:
            title = re.split(r"[：:]", line, maxsplit=1)[-1].strip() or None
        if "工作地点" in line:
            location = re.split(r"[：:]", line, maxsplit=1)[-1].strip() or None

    return JdDecoded.model_validate(
        {
            "schema_version": "1.0",
            "source_type": "pasted_text",
            "must_have": must_items,
            "nice_to_have": nice_items,
            "responsibilities": resp_items,
            "hidden_priorities": _hidden_priorities(must, resp, ids),
            "red_flags": _red_flags(text, must, resp, ids),
            "role_summary": _role_summary(title, location, resp),
            "sentences": sentences,
            "data_mode": "mock" if settings.is_mock else "live",
        }
    )


def fetch_url_text(url: str, settings: Settings, timeout_ms: int = 10_000) -> str:
    if not re.match(r"^https?://", url or ""):
        raise ToolError(code=INVALID_INPUT, message="URL 必须以 http:// 或 https:// 开头。", retryable=False)
    if settings.is_mock:
        raise ToolError(
            code=URL_FETCH_FAILED,
            message="Mock 模式不抓取外网 URL（避免开发期产生真实请求）。请直接粘贴 JD 文本，这是主路径。",
            retryable=False,
            fallback="pasted_text_required",
        )
    req = urllib.request.Request(url, headers={"User-Agent": "dsh-job-sidecar/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout_ms / 1000) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise ToolError(
            code=URL_FETCH_FAILED,
            message=f"JD 链接抓取失败（{type(exc).__name__}），可能遇到登录墙或反爬。请改为粘贴 JD 文本。",
            retryable=True,
            fallback="pasted_text_required",
        ) from exc
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", "\n", text)
    text = re.sub(r"&nbsp;?", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    if len(_normalize(text)) < 40:
        raise ToolError(
            code=URL_FETCH_FAILED,
            message="链接抓到的正文过少（可能需要登录或页面由脚本渲染）。请改为粘贴 JD 文本。",
            retryable=False,
            fallback="pasted_text_required",
        )
    return text.strip()


def decode_jd(
    jd_text: str | None,
    settings: Settings,
    jd_url: str | None = None,
) -> JdDecoded:
    """粘贴文本优先；只有没给文本时才走 URL，且 URL 失败就报错让用户粘贴。"""
    if jd_text and len(_normalize(jd_text)) >= 20:
        return decode_pasted_text(jd_text, settings)
    if jd_url:
        text = fetch_url_text(jd_url, settings)
        decoded = decode_pasted_text(text, settings)
        return decoded.model_copy(update={"source_type": "url"})
    raise ToolError(
        code=INVALID_INPUT,
        message="没有收到可用的 JD 内容。请粘贴 JD 文本（推荐），或提供可公开访问的 JD 链接。",
        retryable=True,
        fallback="pasted_text_required",
    )
