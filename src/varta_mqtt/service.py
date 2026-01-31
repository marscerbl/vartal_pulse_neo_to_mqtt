import os
import json
import time
import requests
from datetime import datetime
from paho.mqtt import client as mqtt_client
from dotenv import load_dotenv

load_dotenv()

# Load environment variables
API_URL = os.getenv('API_URL')
LOGIN_URL = os.getenv('LOGIN_URL')
API_USERNAME = os.getenv('API_USERNAME')
API_PASSWORD = os.getenv('API_PASSWORD')
MQTT_BROKER = os.getenv('MQTT_BROKER')
MQTT_PORT = int(os.getenv('MQTT_PORT', 1883))
MQTT_USERNAME = os.getenv('MQTT_USERNAME')
MQTT_PASSWORD = os.getenv('MQTT_PASSWORD')
DEVICE_NAME = os.getenv('DEVICE_NAME', 'varta_battery')
INTERVAL_SECONDS = int(os.getenv('INTERVAL_SECONDS', 1))

if not API_URL or not MQTT_BROKER:
    raise ValueError("API_URL and MQTT_BROKER must be set in .env")

# MQTT client setup
client = mqtt_client.Client()
client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
client.connect(MQTT_BROKER, MQTT_PORT)

# Global session management
session = None
last_login_time = 0
LOGIN_COOLDOWN = 60  # Minimum seconds between login attempts
error_count = 0
last_error = None

# Key fields to publish (from sample_data.json)
SENSORS = {
    'soc_pct': {'name': 'State of Charge', 'unit': '%', 'device_class': 'battery'},
    'soh_pct': {'name': 'State of Health', 'unit': '%', 'device_class': None},
    'temperature1_C': {'name': 'Temperature 1', 'unit': '°C', 'device_class': 'temperature'},
    'power_W': {'name': 'Power', 'unit': 'W', 'device_class': 'power'},
    'gridPower_W': {'name': 'Grid Power', 'unit': 'W', 'device_class': 'power'},
    'generatingPower_W': {'name': 'Generating Power', 'unit': 'W', 'device_class': 'power'},
    'activePowerAc_W': {'name': 'Active Power AC', 'unit': 'W', 'device_class': 'power'},
    'energyCounterAcIn_Wh': {'name': 'House Consumption Total', 'unit': 'Wh', 'device_class': 'energy'},
    'energyCounterAcOut_Wh': {'name': 'House Feed Total', 'unit': 'Wh', 'device_class': 'energy'},
    'energyCounterBattIn_Wh': {'name': 'Battery In Energy', 'unit': 'Wh', 'device_class': 'energy'},
    'energyCounterBattOut_Wh': {'name': 'Battery Out Energy', 'unit': 'Wh', 'device_class': 'energy'},
    'energyCounterPvOut_Wh': {'name': 'PV Generation Total', 'unit': 'Wh', 'device_class': 'energy'},
    'energyCounterHouseIn_Wh': {'name': 'Netzbezug Gesamt', 'unit': 'Wh', 'device_class': 'energy'},
    'energyCounterHouseOut_Wh': {'name': 'Netzeinspeisung Gesamt', 'unit': 'Wh', 'device_class': 'energy'},
}

# Status sensors for monitoring
STATUS_SENSORS = {
    'service_status': {'name': 'Service Status', 'icon': 'mdi:heart-pulse'},
    'last_update': {'name': 'Last Update', 'icon': 'mdi:clock-outline'},
    'error_count': {'name': 'Error Count', 'icon': 'mdi:alert-circle'},
    'last_error': {'name': 'Last Error', 'icon': 'mdi:alert'},
    'login_status': {'name': 'Login Status', 'icon': 'mdi:login'},
}

def perform_login():
    """Perform login and return True if successful"""
    global session, last_login_time, error_count, last_error
    
    current_time = time.time()
    if current_time - last_login_time < LOGIN_COOLDOWN:
        print(f"Login cooldown active. Next login possible in {LOGIN_COOLDOWN - (current_time - last_login_time):.0f}s")
        publish_status('login_status', 'cooldown')
        return False
    
    try:
        session = requests.Session()
        login_data = {'username': API_USERNAME, 'password': API_PASSWORD}
        login_response = session.post(LOGIN_URL, data=login_data, timeout=10)
        
        if login_response.status_code == 200:
            last_login_time = current_time
            print(f"Login successful at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            publish_status('login_status', 'success')
            publish_status('service_status', 'online')
            return True
        else:
            error_msg = f"Login failed: {login_response.status_code}"
            print(error_msg)
            last_error = error_msg
            error_count += 1
            publish_status('login_status', 'failed')
            publish_status('last_error', error_msg)
            publish_status('error_count', str(error_count))
            session = None
            return False
    except requests.RequestException as e:
        error_msg = f"Login error: {str(e)}"
        print(error_msg)
        last_error = error_msg
        error_count += 1
        publish_status('login_status', 'error')
        publish_status('last_error', error_msg)
        publish_status('error_count', str(error_count))
        publish_status('service_status', 'error')
        session = None
        return False

def fetch_data():
    """Fetch data from API, re-login if necessary"""
    global session, error_count, last_error
    
    # Initial login if no session exists
    if session is None:
        if LOGIN_URL and API_USERNAME and API_PASSWORD:
            if not perform_login():
                return None
        else:
            session = requests.Session()
    
    try:
        response = session.get(API_URL, timeout=10)
        
        # If 401/403, try to re-login once
        if response.status_code in [401, 403]:
            print("Session expired, attempting re-login...")
            publish_status('login_status', 'expired')
            if LOGIN_URL and API_USERNAME and API_PASSWORD:
                if perform_login():
                    response = session.get(API_URL, timeout=10)
                else:
                    return None
            else:
                return None
        
        response.raise_for_status()
        publish_status('service_status', 'online')
        publish_status('last_update', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        return response.json()
        
    except requests.RequestException as e:
        error_msg = f"API fetch error: {str(e)}"
        print(error_msg)
        last_error = error_msg
        error_count += 1
        publish_status('service_status', 'error')
        publish_status('last_error', error_msg)
        publish_status('error_count', str(error_count))
        return None

def publish_discovery():
    # Publish battery sensors
    for sensor_key, config in SENSORS.items():
        topic = f"homeassistant/sensor/{DEVICE_NAME}/{sensor_key}/config"
        payload = {
            "name": config['name'],
            "state_topic": f"homeassistant/sensor/{DEVICE_NAME}/{sensor_key}/state",
            "unit_of_measurement": config['unit'],
            "device_class": config['device_class'],
            "device": {
                "identifiers": [DEVICE_NAME],
                "name": "Varta Battery",
                "manufacturer": "Varta",
                "model": "Battery System"
            },
            "unique_id": f"{DEVICE_NAME}_{sensor_key}"
        }
        client.publish(topic, json.dumps(payload), retain=True)
    
    # Publish status sensors
    for sensor_key, config in STATUS_SENSORS.items():
        topic = f"homeassistant/sensor/{DEVICE_NAME}/{sensor_key}/config"
        payload = {
            "name": config['name'],
            "state_topic": f"homeassistant/sensor/{DEVICE_NAME}/{sensor_key}/state",
            "icon": config['icon'],
            "device": {
                "identifiers": [DEVICE_NAME],
                "name": "Varta Battery",
                "manufacturer": "Varta",
                "model": "Battery System"
            },
            "unique_id": f"{DEVICE_NAME}_{sensor_key}"
        }
        client.publish(topic, json.dumps(payload), retain=True)

def publish_status(sensor_key, value):
    """Publish status sensor update"""
    topic = f"homeassistant/sensor/{DEVICE_NAME}/{sensor_key}/state"
    client.publish(topic, str(value), retain=True)

def publish_data(data):
    pulse = data.get('pulse', {}).get('procImg', {})
    counters = pulse.get('counters', {})
    for sensor_key in SENSORS:
        if sensor_key.endswith('_Wh'):
            # Convert Ws to Wh
            ws_key = sensor_key.replace('_Wh', '_Ws')
            value = counters.get(ws_key, 0) / 3600
        else:
            value = pulse.get(sensor_key, 0)
        topic = f"homeassistant/sensor/{DEVICE_NAME}/{sensor_key}/state"
        client.publish(topic, str(value))

def main():
    publish_discovery()  # Publish discovery once on start
    publish_status('service_status', 'starting')
    publish_status('error_count', '0')
    
    while True:
        data = fetch_data()
        if data:
            publish_data(data)
        else:
            # Exponential backoff on errors (max 60 seconds)
            wait_time = min(INTERVAL_SECONDS * (2 ** min(error_count, 5)), 60)
            print(f"Waiting {wait_time}s before retry...")
            time.sleep(wait_time)
            continue
        
        time.sleep(INTERVAL_SECONDS)  # Fetch every INTERVAL_SECONDS; adjust as needed

if __name__ == "__main__":
    main()
