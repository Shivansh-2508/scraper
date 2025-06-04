FROM python:3.11-slim

# Install system dependencies for Playwright
RUN apt-get update && apt-get install -y \
    # Essential system packages
    wget \
    curl \
    gnupg \
    ca-certificates \
    # Required for Playwright browsers
    libnss3 \
    libnspr4 \
    libatk-bridge2.0-0 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm1 \
    libxss1 \
    libasound2 \
    libgtk-3-0 \
    libgdk-pixbuf2.0-0 \
    # For font rendering
    fonts-liberation \
    fonts-dejavu-core \
    fontconfig \
    # Clean up
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install system dependencies for browsers
RUN playwright install-deps

# Install browsers in system location (as root)
RUN PLAYWRIGHT_BROWSERS_PATH=/usr/lib/playwright playwright install chromium firefox webkit

# Copy application code
COPY . .

# Create non-root user for security but keep browsers accessible
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app

# Set environment variables for system browser location
ENV PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/usr/lib/playwright

# Switch to non-root user
USER appuser

# Expose Streamlit port
EXPOSE 8501

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

# Run Streamlit
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]