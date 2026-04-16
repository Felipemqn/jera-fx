FROM python:3.12-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Python deps
COPY pyproject.toml .
RUN pip install --no-cache-dir .

# App code
COPY src/ src/
COPY config/ config/
COPY alembic/ alembic/
COPY alembic.ini .
COPY apps/ apps/
COPY scripts/ scripts/

# Scripts must be executable
RUN chmod +x scripts/*.sh

# Expose API + client + investment ports
EXPOSE 8000 3000 3001

# Default: run API
CMD ["uvicorn", "jera_fx_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
