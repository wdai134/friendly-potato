# ── 文件清理 Agent Docker 镜像 ──
# 构建: docker build -t file-cleaner-agent .
# 运行: 见 docker-compose.yml

FROM python:3.12-slim AS builder

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── 运行时镜像 ──
FROM python:3.12-slim

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY agent/ ./agent/
COPY config/ ./config/
COPY main.py .

RUN mkdir -p /data/to-clean /data/quarantine /app/logs

ENV SCAN_DIR=/data/to-clean
ENV QUARANTINE_DIR=/data/quarantine
ENV LOG_LEVEL=INFO
ENV PYTHONUNBUFFERED=1

VOLUME ["/data/to-clean", "/data/quarantine", "/app/config", "/app/logs"]

ENTRYPOINT ["python", "main.py"]
CMD ["--scan-dir", "/data/to-clean"]
