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
- `MODBUS_HOST`: Modbus TCP host (enables Modbus primary mode when set)
- `MODBUS_PORT`: Modbus TCP port (default 502)
- `MODBUS_UNIT_ID`: Modbus unit/slave id (default 1)
- `MODBUS_TIMEOUT_SECONDS`: Modbus request timeout (default 5)
- `MODBUS_POLLING_INTERVAL_SECONDS`: Modbus poll rate in seconds (default 1)
- `MODBUS_PUBLISH_INTERVAL_SECONDS`: MQTT publish rate for Modbus values (default 10)

When Modbus is enabled, these two values are read from Modbus and published as primary data source:
- `varta_ac_port_power_w` (register 1066, int16)
- `grid_power_total_w` (register 1078, int16)

If `MODBUS_PUBLISH_INTERVAL_SECONDS` is greater than `MODBUS_POLLING_INTERVAL_SECONDS`, the service publishes the mean over collected samples. If Modbus is unavailable, the service falls back to API values and publishes fallback/modbus status sensors so Home Assistant can alert on degraded mode.

## Home Assistant

Ensure MQTT integration is set up. Sensors will auto-discover under the device "Varta Battery".