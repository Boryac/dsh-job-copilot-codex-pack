"""Sidecar HTTP API（Lane B）：DSH 插件只做声明与转发，重活都在这里。

端点：
  GET  /health                      健康检查 + 当前模式 + 降级模块
  POST /v1/resume/parse             简历解析（文件上传）
  POST /v1/jd/decode                JD 拆解（粘贴文本主路径，URL 辅助）
  POST /v1/company/recon            公司背调（basic / deep，deep 未确认只返回预估）
  POST /v1/company/deep/estimate    deep 预估卡片（零调用）
  POST /v1/analysis                 端到端：解析 -> 匹配 -> 生成 -> 校验 -> 报告
  GET  /v1/analysis/{id}            取回结构化结果
  GET  /v1/analysis/{id}/report.md  取回 Markdown 报告
  POST /v1/report/export            把报告落盘并返回路径

所有出参都过 Pydantic 校验；失败统一走错误契约（02 第 6 节）。
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from .config import load_settings
from .errors import EVIDENCE_INVALID, NOT_CONFIGURED, TIMEOUT, UPSTREAM_ERROR, ToolError
from .orchestrator.service import AnalysisResult, export_markdown, run_analysis
from .parsers.jd import decode_jd
from .parsers.resume import parse_resume
from .recon.service import company_recon
from .schemas import CompanyRecon, DeepEstimate, JdDecoded, ResumeStructured

APP_VERSION = "1.0.0"
settings = load_settings()
app = FastAPI(title="dsh-job-sidecar", version=APP_VERSION)

_ANALYSES: dict[str, AnalysisResult] = {}


def _payload(result) -> dict:
    if hasattr(result, "model_dump"):
        return result.model_dump(by_alias=True)
    return dict(result)


@app.exception_handler(ToolError)
async def tool_error_handler(_request, exc: ToolError):
    from fastapi.responses import JSONResponse

    status = 504 if exc.code == TIMEOUT else 422 if exc.code in (EVIDENCE_INVALID,) else 400
    if exc.code == UPSTREAM_ERROR:
        status = 502
    if exc.code == NOT_CONFIGURED:
        status = 503
    return JSONResponse(status_code=status, content={"error": exc.to_dict()})


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "version": APP_VERSION,
        "mode": settings.app_mode,
        "degraded_modules": settings.degraded_modules(),
        "cache_days": settings.company_cache_days,
    }


@app.post("/v1/resume/parse")
async def parse_resume_endpoint(
    file: UploadFile = File(...),
    resume_id: str = Form(""),
    extract_types: str = Form(""),
) -> dict:
    suffix = Path(file.filename or "").suffix.lower() or ".txt"
    tmp_dir = Path(tempfile.mkdtemp(prefix="dsh-resume-"))
    target = tmp_dir / f"upload{suffix}"
    try:
        with target.open("wb") as fh:
            shutil.copyfileobj(file.file, fh)
        types = [t.strip() for t in extract_types.split(",") if t.strip()] or None
        parsed: ResumeStructured = parse_resume(target, settings, resume_id=resume_id or "upload", extract_types=types)
        return _payload(parsed)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


class JdRequest(BaseModel):
    text: str | None = None
    url: str | None = None


@app.post("/v1/jd/decode")
def decode_jd_endpoint(req: JdRequest) -> dict:
    decoded: JdDecoded = decode_jd(req.text, settings, jd_url=req.url)
    return _payload(decoded)


class CompanyRequest(BaseModel):
    company_name: str
    depth: str = "basic"
    confirmed_deep: bool = False
    role_keywords: list[str] = Field(default_factory=list)


@app.post("/v1/company/recon")
def company_recon_endpoint(req: CompanyRequest) -> dict:
    result = company_recon(
        req.company_name,
        settings,
        depth=req.depth,
        confirmed_deep=req.confirmed_deep,
        role_keywords=req.role_keywords,
    )
    return _payload(result)


@app.post("/v1/company/deep/estimate")
def deep_estimate_endpoint(req: CompanyRequest) -> dict:
    result = company_recon(req.company_name, settings, depth="deep", confirmed_deep=False,
                           role_keywords=req.role_keywords)
    if not isinstance(result, DeepEstimate):  # 理论上不会发生，防御性处理
        raise HTTPException(status_code=500, detail="deep 预估返回类型异常")
    return _payload(result)


class AnalysisRequest(BaseModel):
    resume_path: str
    jd_text: str | None = None
    jd_url: str | None = None
    company_name: str
    depth: str = "basic"
    confirmed_deep: bool = False


@app.post("/v1/analysis")
def analysis_endpoint(req: AnalysisRequest) -> dict:
    result = run_analysis(
        req.resume_path,
        req.jd_text,
        req.company_name,
        settings,
        depth=req.depth,
        confirmed_deep=req.confirmed_deep,
        jd_url=req.jd_url,
    )
    _ANALYSES[result.analysis_id] = result
    return {
        "analysis_id": result.analysis_id,
        "card": result.card,
        "structured": _payload(result.structured),
        "markdown": result.markdown,
        "filename": result.filename,
        "timings": result.timings,
        "degradations": result.degradations,
        "validation_warnings": result.validation_warnings,
    }


@app.get("/v1/analysis/{analysis_id}")
def get_analysis(analysis_id: str) -> dict:
    result = _ANALYSES.get(analysis_id)
    if result is None:
        raise HTTPException(status_code=404, detail="analysis_id 不存在或服务已重启")
    return {
        "analysis_id": result.analysis_id,
        "card": result.card,
        "structured": _payload(result.structured),
        "timings": result.timings,
    }


@app.get("/v1/analysis/{analysis_id}/report.md", response_class=PlainTextResponse)
def get_report(analysis_id: str) -> str:
    result = _ANALYSES.get(analysis_id)
    if result is None:
        raise HTTPException(status_code=404, detail="analysis_id 不存在或服务已重启")
    return result.markdown


class ExportRequest(BaseModel):
    analysis_id: str
    out_dir: str = "reports"


@app.post("/v1/report/export")
def export_endpoint(req: ExportRequest) -> dict:
    result = _ANALYSES.get(req.analysis_id)
    if result is None:
        raise HTTPException(status_code=404, detail="analysis_id 不存在或服务已重启")
    path = export_markdown(result, req.out_dir)
    return {"path": str(path), "filename": path.name}


@app.get("/v1/tools")
def list_tools() -> dict:
    """给 DSH 插件层做契约自检用：声明三个工具的名字和超时预算。"""
    return {
        "tools": [
            {"name": "resume-structurer", "timeout_ms": settings.timeout_ms("resume_structurer")},
            {"name": "company-recon", "timeout_ms": settings.timeout_ms("company_recon")},
            {"name": "jd-decoder", "timeout_ms": settings.timeout_ms("jd_decoder")},
        ],
        "schema_version": "1.0",
        "mode": settings.app_mode,
    }
