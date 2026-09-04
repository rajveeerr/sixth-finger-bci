# Inference server image for a Hugging Face Docker Space (port 7860) or any container host.
# Build from the repository root:  docker build -f server/Dockerfile -t sixthfinger-server .
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv

RUN useradd --create-home --uid 1000 app
WORKDIR /home/app/server

COPY server/pyproject.toml server/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY server/app ./app
COPY web/public/demo ./bundle

USER app
ENV PATH="/home/app/server/.venv/bin:$PATH" \
    BUNDLE_DIR=/home/app/server/bundle \
    PORT=7860
EXPOSE 7860
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
