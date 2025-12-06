import os
import json
import time
import requests
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

# Key fields to publish (from sample_data.json)
SENSORS = {
    'soc_pct': {'name': 'State of Charge', 'unit': '%', 'device_class': 'battery'},
    'soh_pct': {'name': 'State of Health', 'unit': '%', 'device_class': None},
    'temperature1_C': {'name': 'Temperature 1', 'unit': '°C', 'device_class': 'temperature'},
    'power_W': {'name': 'Power', 'unit': 'W', 'device_class': 'power'},
    'gridPower_W': {'name': 'Grid Power', 'unit': 'W', 'device_class': 'power'},
    'generatingPower_W': {'name': 'Generating Power', 'unit': 'W', 'device_class': 'power'},
    'activePowerAc_W': {'name': 'Active Power AC', 'unit': 'W', 'device_class': 'power'},
    'energyCounterAcIn_Wh': {'name': 'Netzbezug Gesamt', 'unit': 'Wh', 'device_class': 'energy'},
    'energyCounterAcOut_Wh': {'name': 'Netzeinspeisung Gesamt', 'unit': 'Wh', 'device_class': 'energy'},
    'energyCounterBattIn_Wh': {'name': 'Battery In Energy', 'unit': 'Wh', 'device_class': 'energy'},
    'energyCounterBattOut_Wh': {'name': 'Battery Out Energy', 'unit': 'Wh', 'device_class': 'energy'},
    'energyCounterPvOut_Wh': {'name': 'PV Generation Total', 'unit': 'Wh', 'device_class': 'energy'},
    'energyCounterHouseIn_Wh': {'name': 'House Consumption Total', 'unit': 'Wh', 'device_class': 'energy'},
    'energyCounterHouseOut_Wh': {'name': 'House Feed Total', 'unit': 'Wh', 'device_class': 'energy'},
}

def fetch_data():
    try:
        session = requests.Session()
        if LOGIN_URL and API_USERNAME and API_PASSWORD:
            login_data = {'username': API_USERNAME, 'password': API_PASSWORD}
            login_response = session.post(LOGIN_URL, data=login_data)
            if login_response.status_code != 200:
                print(f"Login failed with status {login_response.status_code}: {login_response.text}")
                return None
        response = session.get(API_URL)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"API fetch error: {e}")
        return None

def publish_discovery():
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
    while True:
        data = fetch_data()
        if data:
            publish_data(data)
        time.sleep(INTERVAL_SECONDS)  # Fetch every INTERVAL_SECONDS; adjust as needed

if __name__ == "__main__":
    main()