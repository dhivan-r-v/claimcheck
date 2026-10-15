# Stages: base (deps + code) -> eval (Nebius Serverless Job) and app (web server).
# The web server stage MUST stay last: hosts that build without a target (Render) use the final stage.

FROM python:3.13-slim AS base

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

# --- Evaluation job image (ghcr.io/dhivan-r-v/claimcheck:eval) -------------------------------
# Runs the labelled test set as a Nebius Serverless Job and prints the report to the job logs.
FROM base AS eval
COPY --chown=app:app eval/ eval/
COPY --chown=app:app samples/ samples/
ENTRYPOINT ["python", "eval/run_eval.py"]
CMD ["--category", "zero_day"]

# --- Web app (ghcr.io/dhivan-r-v/claimcheck:latest, Render, Nebius Endpoint): keep last ------
FROM base AS app

# Listens on $PORT when the host sets one (Render), otherwise 8000 (Nebius, local).
ENV PORT=8000
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/api/health')"

# Keys come from the environment (NEBIUS_API_KEY, TAVILY_API_KEY), never from the image.
CMD ["sh", "-c", "exec uvicorn claimcheck.app:app --host 0.0.0.0 --port \"$PORT\" --proxy-headers --forwarded-allow-ips '*'"]
