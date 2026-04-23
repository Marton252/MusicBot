# ═══════════════════════════════════════════════════════════════════
# Discord Music Bot — Dockerfile
# Multi-stage: build React dashboard, then run Python bot
# ═══════════════════════════════════════════════════════════════════

# ─── Stage 1: Build the React dashboard ─────────────────────────
FROM node:25-slim AS dash-builder

WORKDIR /build
COPY dash-ui/package.json dash-ui/package-lock.json* ./
RUN npm install
COPY dash-ui/ ./
RUN npm run build

# ─── Stage 2: Python bot runtime ────────────────────────────────
FROM python:3.14-slim

# System dependencies for discord.py[voice] + yt-dlp
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libffi-dev \
    libsodium-dev \
    libopus-dev \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd --create-home --shell /bin/bash botuser

WORKDIR /app

# Install Python dependencies first (better layer caching)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy bot source code
COPY bot.py config.py generate_cert.py ./
COPY cogs/ ./cogs/
COPY services/ ./services/
COPY locales/ ./locales/

# Copy pre-built dashboard from stage 1
COPY --from=dash-builder /build/dist/ ./dash-ui/dist/

# Create directories for runtime data
RUN mkdir -p /app/certs /app/data && chown -R botuser:botuser /app

# Switch to non-root user
USER botuser

# Generate self-signed certs at build time (can be overridden via volume mount)
RUN python generate_cert.py

# Expose dashboard port
EXPOSE 25825

# Health check — verify the bot process is alive
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import os, urllib.request, ssl; urllib.request.urlopen(f'https://localhost:{os.environ.get(\"DASHBOARD_PORT\", 25825)}/', context=ssl._create_unverified_context())" || exit 1

# Run the bot (using --run directly, Docker handles restarts)
CMD ["python", "bot.py", "--run"]
