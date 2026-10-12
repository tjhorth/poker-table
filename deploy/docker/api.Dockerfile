# The game engine + API. Build context is the repo root:
#   docker build -f deploy/docker/api.Dockerfile .
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY deploy/docker/api.requirements.txt .
RUN pip install -r api.requirements.txt

COPY engine/ engine/
COPY api/ api/
COPY web/overlay/ web/overlay/

# a non-root user, and one writable place for data (game summaries, tag DB)
RUN useradd --system --uid 10001 poker && mkdir -p /data && chown poker /data
USER poker

ENV POKER_HOST=0.0.0.0 \
    POKER_PORT=8000 \
    POKER_GAMES_DIR=/data/games \
    POKER_TAGS_DB=/data/tags.sqlite3

EXPOSE 8000
VOLUME ["/data"]

HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"

CMD ["python", "-m", "api"]
