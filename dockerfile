FROM python:3.11-slim

# System deps
RUN apt-get update && apt-get install -y \
    chromium-driver \
    chromium \
    && rm -rf /var/lib/apt/lists/*

# Set environment vars for Chromium
ENV CHROME_BIN=/usr/bin/chromium \
    CHROMEDRIVER_PATH=/usr/bin/chromedriver

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app
COPY . /app
WORKDIR /app

# Expose Streamlit port
EXPOSE 8501

# Run Streamlit
CMD streamlit run app.py --server.port=$PORT --server.address=0.0.0.0
