# ============================================
# Stage 1: Builder
# ============================================
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

WORKDIR /app

# Install dependencies first (cached layer)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Copy source
COPY . .

# ============================================
# Stage 2: Runtime
# ============================================
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS runtime

WORKDIR /app

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
