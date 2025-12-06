# Varta Battery MQTT Service

This Python service fetches battery data from an API and publishes it to an MQTT broker for Home Assistant autodiscovery.

## Setup

### Local Run
1. Install dependencies: `pip install -r requirements.txt`
2. Configure `.env` with your API and MQTT details.
3. Run the service: `python battery_mqtt_service.py`

### Docker Run
1. Build and run with Docker Compose: `docker-compose up -d`
2. Edit `.env` as needed (mounted as volume, no rebuild required).
3. Stop: `docker-compose down`

### Pre-built Docker Image
A Docker image is automatically built and pushed to GitHub Container Registry on releases.
- Pull: `docker pull ghcr.io/marscerbl/vartal_pulse_neo_to_mqtt:latest`
- Use in docker-compose by changing `build: .` to `image: ghcr.io/marscerbl/vartal_pulse_neo_to_mqtt:latest`

## Configuration

Edit `.env` to set:
- `API_URL`: The API endpoint returning JSON like `sample_data.json`
- `LOGIN_URL`: The login endpoint for session-based auth (e.g., http://192.168.88.61/cgi/login)
- `API_USERNAME`/`API_PASSWORD`: Credentials for login form
- `MQTT_BROKER`: MQTT broker address
- `MQTT_PORT`: MQTT port (default 1883)
- `MQTT_USERNAME`/`MQTT_PASSWORD`: MQTT credentials if required
- `DEVICE_NAME`: Unique device name for HA
- `INTERVAL_SECONDS`: Polling interval in seconds (default 1)

## Home Assistant

Ensure MQTT integration is set up. Sensors will auto-discover under the device "Varta Battery".