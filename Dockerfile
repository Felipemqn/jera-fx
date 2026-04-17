FROM python:3.12-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Copy everything needed for install (hatch needs src/ + readme for metadata)
COPY pyproject.toml .
COPY README_START_HERE.md .
COPY src/ src/

# Python deps
RUN pip install --no-cache-dir .

# Remaining app files
COPY config/ config/
COPY data/ data/
COPY alembic/ alembic/
COPY alembic.ini .
COPY apps/ apps/
COPY scripts/ scripts/

# Scripts must be executable
RUN chmod +x scripts/*.sh

EXPOSE 8000

CMD ["uvicorn", "jera_fx_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
