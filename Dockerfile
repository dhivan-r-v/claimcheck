FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY claimcheck/ claimcheck/
COPY static/ static/

RUN useradd --create-home app
USER app

# Listens on $PORT when the host sets one (Render), otherwise 8000 (Nebius, local).
ENV PORT=8000
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/api/health')"

# Keys come from the environment (NEBIUS_API_KEY, TAVILY_API_KEY), never from the image.
CMD ["sh", "-c", "exec uvicorn claimcheck.app:app --host 0.0.0.0 --port \"$PORT\" --proxy-headers --forwarded-allow-ips '*'"]
