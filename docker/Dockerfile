# Use Python 3.12 slim image
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ ./src/

# Set PYTHONPATH
ENV PYTHONPATH=/app/src

# Run the service
CMD ["python", "-m", "varta_mqtt.service"]
