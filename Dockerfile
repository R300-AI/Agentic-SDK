FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=10

WORKDIR /app

COPY pyproject.toml README.md ./
COPY agentic_sdk ./agentic_sdk
COPY dashboard ./dashboard
COPY examples ./examples

RUN pip install --no-cache-dir .

# Cloud Run 透過 $PORT 注入；__main__ 已支援。
CMD ["python", "-m", "agentic_sdk.gateway"]
