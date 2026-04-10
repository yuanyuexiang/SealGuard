# ============================================
# Stage 1: Builder
# ============================================
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

WORKDIR /app

# Install dependencies first (cached layer)
COPY pyproject.toml uv.lock ./
RUN uv venv /app/.venv \
    && uv export --frozen --no-dev --format requirements-txt -o /tmp/requirements.txt \
    && uv pip install --python /app/.venv/bin/python -r /tmp/requirements.txt

# Copy source
COPY . .

# ============================================
# Stage 2: Runtime
# ============================================
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS runtime

WORKDIR /app

# OpenCV runtime libs (fix: ImportError libGL.so.1)
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user first
RUN groupadd --system app && useradd --system --gid app --create-home --home-dir /home/app app

# Copy only runtime files and set ownership at copy-time (avoid chown duplicate layer)
COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --from=builder --chown=app:app /app/app /app/app
COPY --from=builder --chown=app:app /app/artifacts /app/artifacts

# Ensure runtime upload root exists and is writable
RUN mkdir -p /app/runtime/uploads/orders /app/runtime/uploads/templates && chown -R app:app /app/runtime

# Drop privileges
USER app

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Expose port
EXPOSE 8000

# Run application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
