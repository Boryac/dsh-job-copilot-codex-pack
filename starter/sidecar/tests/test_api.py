"""API 集成测试：健康检查、三个工具端点、端到端、错误契约。"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import app.main as main_module


@pytest.fixture()
def client(settings, monkeypatch):
    monkeypatch.setattr(main_module, "settings", settings)
    return TestClient(main_module.app)


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["mode"] == "mock"


def test_tools_endpoint_declares_timeouts(client):
    body = client.get("/v1/tools").json()
    names = {t["name"] for t in body["tools"]}
    assert names == {"resume-structurer", "company-recon", "jd-decoder"}
    assert all(t["timeout_ms"] > 0 for t in body["tools"])


def test_resume_upload(client, bd_resume_path):
    with bd_resume_path.open("rb") as fh:
        resp = client.post(
            "/v1/resume/parse",
            files={"file": ("resume.txt", fh, "text/plain")},
            data={"resume_id": "case-1"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["schema_version"] == "1.0"
    assert [e["id"] for e in body["experiences"]] == ["exp_01", "exp_02"]


def test_resume_upload_rejects_missing_file(client):
    resp = client.post("/v1/resume/parse", data={"resume_id": "x"})
    assert resp.status_code == 422


def test_jd_decode(client, bd_jd_text):
    resp = client.post("/v1/jd/decode", json={"text": bd_jd_text})
    assert resp.status_code == 200
    assert resp.json()["must_have"]


def test_jd_url_failure_returns_error_contract(client):
    resp = client.post("/v1/jd/decode", json={"url": "https://example.com/jd"})
    assert resp.status_code == 400
    error = resp.json()["error"]
    assert error["code"] == "URL_FETCH_FAILED"
    assert error["fallback"] == "pasted_text_required"
    assert error["retryable"] is False


def test_company_basic(client):
    resp = client.post("/v1/company/recon", json={"company_name": "云栖生活"})
    assert resp.status_code == 200
    assert resp.json()["quota_consumed"]["tianyancha_calls"] == 2


def test_company_deep_estimate_has_no_calls(client):
    resp = client.post("/v1/company/deep/estimate", json={"company_name": "云栖生活"})
    body = resp.json()
    assert body["needs_confirmation"] is True
    assert body["estimate"]["calls"] > 0
    assert body["quota_consumed"] == {"tianyancha_calls": 0, "tianyancha_detail": [], "search_calls": 0}


def test_company_deep_without_confirm_has_no_calls(client):
    resp = client.post("/v1/company/recon", json={"company_name": "云栖生活", "depth": "deep"})
    body = resp.json()
    assert body["needs_confirmation"] is True
    assert body["quota_consumed"]["tianyancha_calls"] == 0


def test_analysis_end_to_end(client, bd_resume_path, bd_jd_text):
    resp = client.post(
        "/v1/analysis",
        json={
            "resume_path": str(bd_resume_path),
            "jd_text": bd_jd_text,
            "company_name": "云栖生活",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["card"]["verdict_tier"] in ("strong", "discussable", "gap")
    assert body["structured"]["schema_version"] == "1.0"
    assert "## 第 8 节" in body["markdown"]
    assert body["timings"]["total"] >= 0

    analysis_id = body["analysis_id"]
    again = client.get(f"/v1/analysis/{analysis_id}")
    assert again.status_code == 200
    report = client.get(f"/v1/analysis/{analysis_id}/report.md")
    assert report.status_code == 200
    assert "作战包报告" in report.text


def test_analysis_unknown_id_404(client):
    assert client.get("/v1/analysis/nope").status_code == 404


def test_analysis_export_writes_file(client, bd_resume_path, bd_jd_text, tmp_path):
    body = client.post(
        "/v1/analysis",
        json={"resume_path": str(bd_resume_path), "jd_text": bd_jd_text, "company_name": "云栖生活"},
    ).json()
    resp = client.post("/v1/report/export", json={"analysis_id": body["analysis_id"], "out_dir": str(tmp_path)})
    assert resp.status_code == 200
    path = resp.json()["path"]
    assert path.endswith(".md")
    assert (tmp_path / resp.json()["filename"]).exists()


def test_analysis_missing_resume_returns_error(client, bd_jd_text):
    resp = client.post(
        "/v1/analysis",
        json={"resume_path": "no-such-file.txt", "jd_text": bd_jd_text, "company_name": "云栖生活"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "PARSE_FAILED"
    assert "文本版简历" in resp.json()["error"]["message"]
