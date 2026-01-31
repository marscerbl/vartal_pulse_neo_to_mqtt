# Varta Battery MQTT Service

This Python service fetches battery data from a Varta battery system API and publishes it to an MQTT broker for Home Assistant autodiscovery.

## Features

✅ **Session Management**: Reuses login sessions to prevent API overload  
✅ **Auto Re-login**: Automatically handles expired sessions  
✅ **Login Cooldown**: 60-second cooldown prevents rapid login attempts  
✅ **Error Handling**: Exponential backoff on errors (max 60s)  
✅ **Status Monitoring**: MQTT status sensors for service health  
✅ **Home Assistant Integration**: Auto-discovery for all sensors  

## Quick Start

### Using Docker (Recommended)

```bash
# Clone repository
git clone <your-repo>
cd homeassistant_varta

# Configure environment
cp .env.example .env
# Edit .env with your settings

# Start service
cd docker
docker-compose up -d
```

### Local Installation

```bash
# Install package
pip install -e .

# Configure
cp .env.example .env
# Edit .env

# Run service
varta-mqtt
```

For detailed installation and configuration instructions, see [docs/INSTALLATION.md](docs/INSTALLATION.md).

## Project Structure

```
homeassistant_varta/
├── src/varta_mqtt/       # Main source code
│   ├── __init__.py
│   └── service.py        # Core service logic
├── tests/                # Test suite
│   └── test_service.py
├── docker/               # Docker configuration
│   ├── Dockerfile
│   └── docker-compose.yml
├── docs/                 # Documentation
├── .env.example          # Example configuration
├── pyproject.toml        # Package configuration
└── requirements.txt      # Dependencies
```

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