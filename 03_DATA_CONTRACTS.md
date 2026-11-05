# 03_DATA_CONTRACTS — 数据契约（改 Schema 先改这里）

> 本文件是三个工具输出的唯一事实来源。所有 Pydantic 模型、TypeScript 类型、
> 校验器、测试固件都必须与这里一致。不一致 = bug，不是“文档滞后”。

## 通用规则

- 所有 ID 由解析步骤生成，生成步骤不许自创。简历经历 `exp_01...`，JD 要求 `jd_01...`。
- 所有 LLM 推断字段必须带 `inferred: true` 或放在 `soft_profile` 里；硬数据字段不许出现推断值。
- 所有时间用 ISO 8601；金额用“元”为单位并标注币种；不确定的字段用 `null` + `note`，不许编一个看起来合理的值。
- 版本字段：每个工具输出带 `schema_version: "1.0"`，破坏性变更必须升版本并在 PROGRESS.md 记录。

## 3.1 resume-structurer 输出

```json
{
  "schema_version": "1.0",
  "parsing_mode": "smartresume | fallback",
  "basic_info": {"name": null, "title": null, "location": null, "links": []},
  "education": [{"school": "...", "major": "...", "degree": "...", "period": "..."}],
  "experiences": [
    {
      "id": "exp_01",
      "company": "...",
      "role": "...",
      "period": "...",
      "bullets": ["..."],
      "metrics": [{"value": "...", "context": "..."}]
    }
  ],
  "projects": [{"id": "proj_01", "name": "...", "bullets": [...], "metrics": [...]}],
  "skills": ["..."],
  "parsing_notes": ["图片页 OCR 置信度低，已标注", "..."]
}
```

校验要点：
- `experiences[].id` 唯一且连续；`bullets` 必须来自原文改写，不得新增公司、岗位、时间、核心数字。
- `parsing_mode` 为 `fallback` 时，报告里必须在显眼处标注解析方式。
- 姓名、电话、邮箱等 PII 只出现在本结构体内，不进入日志与搜索请求。

## 3.2 company-recon 输出

```json
{
  "schema_version": "1.0",
  "company_input": "用户输入的公司名称",
  "company_resolved": {
    "name": "工商注册全称",
    "unified_credit_code": null,
    "disambiguation": {"candidates": [], "chosen_reason": "...", "needs_user_confirm": false}
  },
  "hard_data": {
    "founded_at": {"value": null, "verified": true, "source": "tianyancha_mcp"},
    "registered_capital": {"value": null, "verified": true, "source": "tianyancha_mcp"},
    "legal_representative": {"value": null, "verified": true, "source": "tianyancha_mcp"},
    "business_scope": {"value": null, "verified": true, "source": "tianyancha_mcp"}
  },
  "soft_profile": {
    "products": [{"name": "...", "users": null, "revenue_model": null, "relation_to_role": "...", "source_urls": []}],
    "news": [{"title": "...", "date": null, "url": "...", "summary": "..."}],
    "financing": [{"round": null, "date": null, "amount": null, "source_urls": []}],
    "hiring_signals": ["..."],
    "inferred": true,
    "source_urls": []
  },
  "deep_data": null,
  "depth_used": "basic | deep",
  "quota_consumed": {"tianyancha_calls": 0, "tianyancha_detail": [], "search_calls": 0},
  "fetched_at": "2026-01-01T00:00:00+08:00"
}
```

校验要点：
- `depth_used: deep` 时 `deep_data` 才可非空，且必须有调用前的费用预估记录（见 `05_COMPANY_RECON_SPEC.md`）。
- `hard_data` 里任何 `verified: false` 的字段不许在报告正文里写成确定事实，只能进“待核实清单”。
- `soft_profile.source_urls` 必须真实可访问（测试里抽查），LLM 不许自编 URL。

## 3.3 jd-decoder 输出

```json
{
  "schema_version": "1.0",
  "source_type": "pasted_text | url",
  "must_have": [{"id": "jd_01", "text": "...", "type": "hard"}],
  "nice_to_have": [{"id": "jd_02", "text": "...", "type": "soft"}],
  "responsibilities": [{"id": "jd_03", "text": "..."}],
  "hidden_priorities": [{"text": "...", "evidence_sentence_ids": ["jd_01"], "inferred": true}],
  "red_flags": [{"text": "...", "evidence_sentence_ids": [], "inferred": true}],
  "role_summary": "..."
}
```

校验要点：
- `must_have / nice_to_have / responsibilities` 的 `text` 必须能在 JD 原文里找到对应句子或关键词，找不到 = 解析失败。
- `hidden_priorities / red_flags` 永远是推断，必须带 `inferred: true`，不许混进 must_have。

## 3.4 job-fit-orchestrator 输出（报告结构化版）

```json
{
  "schema_version": "1.0",
  "analysis_id": "uuid",
  "verdict": {"tier": "strong | discussable | gap", "headline": "...", "top_strength": "...", "top_gap": "..."},
  "match": {
    "dimensions": [
      {"name": "硬性条件", "tier": "strong | discussable | gap", "evidence_refs": ["exp_01", "jd_01"], "note": "..."},
      {"name": "职责匹配", "tier": "...", "evidence_refs": [], "note": "..."},
      {"name": "履历证据", "tier": "...", "evidence_refs": [], "note": "..."},
      {"name": "加分项", "tier": "...", "evidence_refs": [], "note": "..."}
    ]
  },
  "self_intro": {"30s": "...", "60s": "...", "120s": "...", "anchors": ["exp_01"]},
  "interview_questions": [
    {
      "id": "q_01",
      "category": "动机 | 经历深挖 | 岗位认知 | 协作与稳定性",
      "question": "...",
      "focus": "...",
      "evidence_ref": "exp_01",
      "star_answer": {"situation": "...", "task": "...", "action": "...", "result": "..."},
      "follow_up": "...",
      "pitfall": "...",
      "knowledge_refs": ["k_01"]
    }
  ],
  "knowledge": [{"id": "k_01", "level": "must | bonus | frequent", "term": "...", "definition": "...", "resume_example_ref": "exp_01", "likely_follow_up": "..."}],
  "action_plan": {"before_apply": [], "before_interview": [], "in_interview_defense": [], "questions_to_ask": [], "after_interview": []},
  "sources_and_confidence": [{"item": "...", "source": "...", "confidence": "verified | inferred | unverified"}],
  "to_verify": ["..."]
}
```

校验要点（由 `starter/sidecar/app/validator.py` 强制执行）：
- `interview_questions` 每道必须有 `evidence_ref`，且该 ID 必须真实存在于简历或 JD 结构里。
- `self_intro.anchors` 至少 3 条，且每条对应简历里的量化成果。
- `knowledge[].resume_example_ref` 为空时，该知识点必须标注为“通用知识、无简历例证”，不许假装来自简历。
