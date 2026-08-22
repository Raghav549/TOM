FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TOM_HOST=0.0.0.0 \
    TOM_PORT=8787

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY tom ./tom

# The default container is a remote-TTS client. GPU/local Qwen dependencies belong
# on the dedicated model host and are installed with the voice-qwen-local extra.
RUN python -m pip install --no-cache-dir --upgrade pip \
  && pip install --no-cache-dir '.[browser,voice,voice-qwen]' \
  && playwright install --with-deps chromium

EXPOSE 8787

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8787/health', timeout=3).read()"

CMD ["sh", "-c", "uvicorn tom.api.app:app --host 0.0.0.0 --port ${PORT:-8787}"]
