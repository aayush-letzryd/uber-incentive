FROM mcr.microsoft.com/playwright/python:v1.50.0-jammy

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source files
COPY gcp_incentives_job.py .
COPY storage_state.json* .

CMD ["python", "gcp_incentives_job.py"]
