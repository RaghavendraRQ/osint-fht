##############################################
# Stage 1 – Build dependencies
##############################################
FROM python:3.11-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential git curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements.txt .

RUN pip install --no-cache-dir --prefix=/install \
        torch==2.5.1+cpu \
        --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir --prefix=/install \
        torch-scatter torch-sparse \
        -f https://data.pyg.org/whl/torch-2.5.1+cpu.html && \
    pip install --no-cache-dir --prefix=/install \
        torch-geometric==2.6.1

RUN pip install --no-cache-dir --prefix=/install -r requirements.txt || true

##############################################
# Stage 2 – Runtime
##############################################
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        git curl && \
    rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local

RUN pip install --no-cache-dir sherlock-project maigret || true

WORKDIR /app

COPY config.py run.py check_setup.py ./
COPY src/ src/
COPY data/ data/

RUN mkdir -p data/results data/neo4j data/models

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/status || exit 1

CMD ["python", "run.py", "--host", "0.0.0.0", "--port", "8000"]
