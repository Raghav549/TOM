FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TOM_HOST=0.0.0.0 \
    TOM_PORT=8787

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY tom ./tom

RUN python -m pip install --no-cache-dir --upgrade pip \
  && pip install --no-cache-dir '.[browser,voice,voice-qwen]' \
  && playwright install --with-deps chromium

EXPOSE 8787

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8787/health', timeout=3).read()"

CMD ["uvicorn", "tom.api.app:app", "--host", "0.0.0.0", "--port", "8787"]
