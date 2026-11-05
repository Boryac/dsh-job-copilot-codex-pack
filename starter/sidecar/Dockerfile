# sidecar 镜像：Mock 模式零外部依赖即可跑通全部链路。
# 构建：docker compose -f starter/docker-compose.yml up --build
# 说明：不装 GPU / 模型权重；SmartResume 是可选适配器，未装时自动走 fallback 解析。
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_MODE=mock

WORKDIR /srv

# 先装依赖，利用层缓存：改代码不用重装包
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# 非 root 运行；缓存目录交给应用自己建
RUN useradd --create-home --uid 10001 sidecar \
    && mkdir -p /srv/.cache \
    && chown -R sidecar:sidecar /srv
USER sidecar

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
