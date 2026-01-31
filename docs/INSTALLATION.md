# Installation

## Standard Installation

```bash
# Clone repository
git clone <your-repo>
cd homeassistant_varta

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -e .

# Or for development
pip install -e ".[dev]"
```

## Configuration

1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` with your settings:
   - Varta battery IP and credentials
   - MQTT broker details
   - Device name and update interval

## Running

### Direct Execution
```bash
python -m varta_mqtt.service
```

### As Installed Package
```bash
varta-mqtt
```

### Docker
```bash
cd docker
docker-compose up -d
```

## Development

### Running Tests
```bash
pytest
pytest --cov=varta_mqtt --cov-report=html
```

### Project Structure
```
homeassistant_varta/
├── src/varta_mqtt/       # Main source code
│   ├── __init__.py
│   └── service.py        # Core service logic
├── tests/                # Test suite
│   ├── __init__.py
│   └── test_service.py
├── docker/               # Docker configuration
│   ├── Dockerfile
│   └── docker-compose.yml
├── docs/                 # Documentation
├── .env.example          # Example configuration
├── pyproject.toml        # Package configuration
├── requirements.txt      # Dependencies
└── README.md            # This file
```

## Monitoring

The service publishes the following status sensors to MQTT:

- **Service Status**: Current state (starting/online/error)
- **Login Status**: Authentication state (success/failed/expired/cooldown)
- **Last Update**: Timestamp of last successful data fetch
- **Error Count**: Number of errors encountered
- **Last Error**: Description of most recent error

These can be monitored in Home Assistant to track service health.
