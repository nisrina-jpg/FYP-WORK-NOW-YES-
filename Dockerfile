# ── Base image ──────────────────────────────────────────────────────────────
FROM python:3.12-slim

# ── System deps needed by Playwright's Chromium ──────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libxkbcommon0 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    fonts-liberation \
    wget \
    ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# ── Working dir ──────────────────────────────────────────────────────────────
WORKDIR /app

# ── Install Python deps ───────────────────────────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Install only Chromium (skip Firefox & WebKit to save space) ───────────────
RUN playwright install chromium

# ── Copy source ───────────────────────────────────────────────────────────────
COPY main.py .

# ── Expose port & start ───────────────────────────────────────────────────────
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
