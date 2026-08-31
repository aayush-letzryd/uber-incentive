FROM mcr.microsoft.com/playwright/python:v1.50.0-jammy

WORKDIR /app

# Set non-interactive and UTF-8
ENV PYTHONUNBUFFERED=1
ENV PYTHONIOENCODING=utf-8
ENV DEBIAN_FRONTEND=noninteractive

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code and credentials
COPY . .

# Run the complete cloud orchestrator
CMD ["python", "cloud_runner.py"]
