# Use Python 3.12 slim image
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY battery_mqtt_service.py .
COPY .env .

# Run the service
CMD ["python", "battery_mqtt_service.py"]