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
client = mqtt_client.Client(callback_api_version=mqtt_client.CallbackAPIVersion.VERSION2)
client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
client.connect(MQTT_BROKER, MQTT_PORT)

# Global session management
session = None
last_login_time = 0
LOGIN_COOLDOWN = 60  # Minimum seconds between login attempts
error_count = 0
last_error = None

# Key fields to publish (clean names; no backward-compatibility required)
SENSORS = {
    # Battery Status
    'state_of_charge_pct': {'name': 'State of Charge', 'unit': '%', 'device_class': 'battery', 'path': 'pulse.procImg', 'source_key': 'soc_pct'},
    'state_of_health_pct': {'name': 'State of Health', 'unit': '%', 'device_class': None, 'path': 'pulse.procImg', 'source_key': 'soh_pct'},
    'battery_cycles': {'name': 'Battery Cycles', 'unit': 'cycles', 'device_class': None, 'path': 'pulse.procImg', 'source_key': 'cycles'},
    'energy_capacity_wh': {'name': 'Energy Capacity', 'unit': 'Wh', 'device_class': 'energy', 'path': 'pulse.procImg', 'source_key': 'energyCapacity_Wh'},

    # Temperature
    'temperature_1_c': {'name': 'Temperature 1', 'unit': '°C', 'device_class': 'temperature', 'path': 'pulse.procImg', 'source_key': 'temperature1_C'},

    # Power
    'battery_power_w': {'name': 'Battery Power', 'unit': 'W', 'device_class': 'power', 'path': 'pulse.procImg', 'source_key': 'power_W'},
    'grid_power_total_w': {'name': 'Grid Power Total', 'unit': 'W', 'device_class': 'power', 'path': 'pulse.procImg', 'source_key': 'gridPower_W'},
    'varta_ac_port_power_w': {'name': 'Varta AC Port Active Power', 'unit': 'W', 'device_class': 'power', 'path': 'pulse.procImg', 'source_key': 'activePowerAc_W'},
    'grid_power_l1_w': {'name': 'Grid Power L1', 'unit': 'W', 'device_class': 'power', 'path': 'pulse.procImg', 'source_key': 'gridAppPowerL1_W'},
    'grid_power_l2_w': {'name': 'Grid Power L2', 'unit': 'W', 'device_class': 'power', 'path': 'pulse.procImg', 'source_key': 'gridAppPowerL2_W'},
    'grid_power_l3_w': {'name': 'Grid Power L3', 'unit': 'W', 'device_class': 'power', 'path': 'pulse.procImg', 'source_key': 'gridAppPowerL3_W'},
    'max_charge_power_w': {'name': 'Max Charge Power', 'unit': 'W', 'device_class': 'power', 'path': 'pulse.procImg', 'source_key': 'maxChargePower_W'},
    'max_discharge_power_w': {'name': 'Max Discharge Power', 'unit': 'W', 'device_class': 'power', 'path': 'pulse.procImg', 'source_key': 'maxDischargePower_W'},

    # Grid Info
    'grid_voltage_v': {'name': 'Grid Voltage', 'unit': 'V', 'device_class': 'voltage', 'path': 'pulse.procImg', 'source_key': 'gridVoltage_V'},
    'grid_frequency_hz': {'name': 'Grid Frequency', 'unit': 'Hz', 'device_class': 'frequency', 'path': 'pulse.procImg', 'source_key': 'gridFrequency_Hz'},
    'grid_apparent_power_va': {'name': 'Grid Apparent Power', 'unit': 'VA', 'device_class': 'apparent_power', 'path': 'pulse.procImg', 'source_key': 'gridApparentPower_W'},
    'grid_reactive_power_var': {'name': 'Grid Reactive Power', 'unit': 'var', 'device_class': 'reactive_power', 'path': 'pulse.procImg', 'source_key': 'gridReactivePower_W'},

    # Energy Counters
    'grid_to_battery_charged_total_wh': {
        'name': 'Grid to Battery Charged (AC side) Total',
        'unit': 'Wh',
        'device_class': 'energy',
        'path': 'counters',
        'source_key': 'energyCounterAcIn_Ws',
        'conversion': 'ws_to_wh'
    },
    'battery_to_ac_discharged_total_wh': {
        'name': 'Battery to AC Discharged (AC side) Total',
        'unit': 'Wh',
        'device_class': 'energy',
        'path': 'counters',
        'source_key': 'energyCounterAcOut_Ws',
        'conversion': 'ws_to_wh'
    },
    'battery_charged_total_wh': {
        'name': 'Battery Charged (DC side) Total',
        'unit': 'Wh',
        'device_class': 'energy',
        'path': 'counters',
        'source_key': 'energyCounterBattIn_Ws',
        'conversion': 'ws_to_wh'
    },
    'battery_discharged_total_wh': {
        'name': 'Battery Discharged (DC side) Total',
        'unit': 'Wh',
        'device_class': 'energy',
        'path': 'counters',
        'source_key': 'energyCounterBattOut_Ws',
        'conversion': 'ws_to_wh'
    },
    'grid_import_total_wh': {
        'name': 'Grid Import (House Meter) Total',
        'unit': 'Wh',
        'device_class': 'energy',
        'path': 'counters',
        'source_key': 'energyCounterHouseIn_Ws',
        'conversion': 'ws_to_wh'
    },
    'grid_export_total_wh': {
        'name': 'Grid Export (House Meter) Total',
        'unit': 'Wh',
        'device_class': 'energy',
        'path': 'counters',
        'source_key': 'energyCounterHouseOut_Ws',
        'conversion': 'ws_to_wh'
    },

    # System Counters
    'active_hours': {
        'name': 'Active Hours',
        'unit': 'h',
        'device_class': None,
        'path': 'counters',
        'source_key': 'countActiveMinutes_m',
        'conversion': 'minutes_to_hours'
    },
    'system_starts': {'name': 'System Starts', 'unit': 'starts', 'device_class': None, 'path': 'counters', 'source_key': 'countNrOfSysStarts'},

    # Battery Module Details (bmAct)
    'battery_voltage_v': {'name': 'Battery Voltage', 'unit': 'V', 'device_class': 'voltage', 'path': 'pulse.bmAct', 'source_key': 'batteryVoltage_cV', 'conversion': 'centivolt_to_volt'},
    'battery_current_a': {'name': 'Battery Current', 'unit': 'A', 'device_class': 'current', 'path': 'pulse.bmAct', 'source_key': 'batteryCurrent_dA', 'conversion': 'deciamp_to_amp'},
    'battery_temp_c': {'name': 'Battery Temperature', 'unit': '°C', 'device_class': 'temperature', 'path': 'pulse.bmAct', 'source_key': 'batteryTemp_dC', 'conversion': 'decideg_to_deg'},
    'avg_cell_voltage_mv': {'name': 'Avg Cell Voltage', 'unit': 'mV', 'device_class': 'voltage', 'path': 'pulse.bmAct', 'source_key': 'avgCellVoltage_mV'},
    'max_cell_voltage_mv': {'name': 'Max Cell Voltage', 'unit': 'mV', 'device_class': 'voltage', 'path': 'pulse.bmAct', 'source_key': 'maxCellVoltage_mV'},
    'min_cell_voltage_mv': {'name': 'Min Cell Voltage', 'unit': 'mV', 'device_class': 'voltage', 'path': 'pulse.bmAct', 'source_key': 'minCellVoltage_mV'},
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
        data = response.json()
        print(f"✓ Data fetched successfully at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        publish_status('service_status', 'online')
        publish_status('last_update', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        return data
        
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
    pulse = data.get('pulse', {})
    procImg = pulse.get('procImg', {})
    counters = procImg.get('counters', {})
    bmAct = pulse.get('bmAct', {})
    
    # Log wichtige Werte
    soc = procImg.get('soc_pct', 0)
    power = procImg.get('power_W', 0)
    grid_power = procImg.get('gridPower_W', 0)
    print(f"  → SOC: {soc}% | Battery: {power}W | Grid: {grid_power}W")
    
    for sensor_key, config in SENSORS.items():
        path = config.get('path', 'pulse.procImg')
        source_key = config.get('source_key', sensor_key)
        conversion = config.get('conversion')
        
        # Bestimme Datenquelle basierend auf Pfad
        if path == 'counters':
            source = counters
        elif path == 'pulse.bmAct':
            source = bmAct
        else:  # pulse.procImg
            source = procImg
        
        raw_value = source.get(source_key, 0)

        if conversion == 'ws_to_wh':
            value = raw_value / 3600
        elif conversion == 'minutes_to_hours':
            value = raw_value / 60
        elif conversion == 'centivolt_to_volt':
            value = raw_value / 100
        elif conversion == 'deciamp_to_amp':
            value = raw_value / 10
        elif conversion == 'decideg_to_deg':
            value = raw_value / 10
        else:
            value = raw_value
        
        topic = f"homeassistant/sensor/{DEVICE_NAME}/{sensor_key}/state"
        client.publish(topic, str(value))
    
    print(f"  → Published {len(SENSORS)} sensors to MQTT")

def main():
    print("="*60)
    print(f"Varta MQTT Service started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"API: {API_URL}")
    print(f"MQTT Broker: {MQTT_BROKER}:{MQTT_PORT}")
    print(f"Update Interval: {INTERVAL_SECONDS}s")
    print("="*60)
    
    publish_discovery()  # Publish discovery once on start
    publish_status('service_status', 'starting')
    publish_status('error_count', '0')
    print(f"Published discovery for {len(SENSORS)} sensors + {len(STATUS_SENSORS)} status sensors")
    print(f"Starting data collection loop...\n")
    
    while True:
        data = fetch_data()
        if data:
            publish_data(data)
        else:
            # Exponential backoff on errors (max 60 seconds)
            wait_time = min(INTERVAL_SECONDS * (2 ** min(error_count, 5)), 60)
            print(f"⚠ Error occurred. Waiting {wait_time}s before retry... (Error #{error_count})")
            time.sleep(wait_time)
            continue
        
        time.sleep(INTERVAL_SECONDS)  # Fetch every INTERVAL_SECONDS; adjust as needed

if __name__ == "__main__":
    main()
