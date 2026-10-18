# Двойник в контуре банка: один образ с интерфейсом и сервисом.
# Сборка интерфейса не требует сети во время работы: все файлы раздаются самим сервисом.
FROM node:24-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
COPY examples/ /app/examples/
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DVOINIK_HOST=0.0.0.0 \
    DVOINIK_PORT=8501 \
    DVOINIK_STORAGE_PATH=/data/experiments.sqlite3
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY dvoinik/ ./dvoinik/
COPY serve.py manage.py cli.py llm_check.py benchmark.py app.py ./
COPY benchmarks/ ./benchmarks/
COPY examples/ ./examples/
COPY --from=frontend /app/frontend/dist ./frontend/dist
RUN useradd --create-home --uid 10001 dvoinik && mkdir -p /data && chown dvoinik /data
USER dvoinik
VOLUME ["/data"]
EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/', timeout=4)"
CMD ["python", "serve.py"]
