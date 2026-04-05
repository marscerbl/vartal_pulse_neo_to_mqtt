import json
import os
import threading
import time
from datetime import datetime
from typing import Any, Dict, Optional, cast

import requests
from dotenv import load_dotenv
from paho.mqtt import client as mqtt_client

from varta_mqtt.modbus_poller import ModbusPoller

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

MODBUS_HOST = os.getenv('MODBUS_HOST')
MODBUS_PORT = int(os.getenv('MODBUS_PORT', 502))
MODBUS_UNIT_ID = int(os.getenv('MODBUS_UNIT_ID', 1))
MODBUS_TIMEOUT_SECONDS = float(os.getenv('MODBUS_TIMEOUT_SECONDS', 5))
MODBUS_POLLING_INTERVAL_SECONDS = int(os.getenv('MODBUS_POLLING_INTERVAL_SECONDS', 1))
MODBUS_PUBLISH_INTERVAL_SECONDS = int(os.getenv('MODBUS_PUBLISH_INTERVAL_SECONDS', 10))
MODBUS_ENABLED = bool(MODBUS_HOST)

if not API_URL or not MQTT_BROKER:
    raise ValueError("API_URL and MQTT_BROKER must be set in .env")

API_URL = cast(str, API_URL)
MQTT_BROKER = cast(str, MQTT_BROKER)

if MODBUS_ENABLED and MODBUS_PUBLISH_INTERVAL_SECONDS < MODBUS_POLLING_INTERVAL_SECONDS:
    raise ValueError(
        "MODBUS_PUBLISH_INTERVAL_SECONDS must be >= MODBUS_POLLING_INTERVAL_SECONDS"
    )

# MQTT client setup
client = mqtt_client.Client()
client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
client.connect(MQTT_BROKER, MQTT_PORT)

# Global state
mqtt_lock = threading.Lock()
api_data_lock = threading.Lock()
session = None
last_login_time = 0
LOGIN_COOLDOWN = 60
error_count = 0
last_error = None
latest_api_data: Optional[Dict[str, Any]] = None
modbus_error_count = 0
last_modbus_error = ''
fallback_active = False

MODBUS_PRIMARY_SENSORS = {'varta_ac_port_power_w', 'grid_power_total_w'}

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
    'modbus_status': {'name': 'Modbus Status', 'icon': 'mdi:connection'},
    'modbus_error_count': {'name': 'Modbus Error Count', 'icon': 'mdi:alert-circle-outline'},
    'last_modbus_error': {'name': 'Last Modbus Error', 'icon': 'mdi:alert-octagon-outline'},
    'fallback_active': {'name': 'Fallback Active', 'icon': 'mdi:swap-horizontal-bold'},
    'data_source_grid_power': {'name': 'Grid Power Data Source', 'icon': 'mdi:source-branch'},
    'data_source_battery_active_power': {'name': 'Battery Active Power Data Source', 'icon': 'mdi:source-branch'},
}


def safe_publish(topic: str, payload: str, retain: bool = False) -> None:
    with mqtt_lock:
        client.publish(topic, payload, retain=retain)


def publish_status(sensor_key: str, value: Any) -> None:
    topic = f"homeassistant/sensor/{DEVICE_NAME}/{sensor_key}/state"
    safe_publish(topic, str(value), retain=True)


def extract_sensor_value(data: Dict[str, Any], sensor_key: str) -> float:
    config = SENSORS[sensor_key]
    pulse = data.get('pulse', {})
    proc_img = pulse.get('procImg', {})
    counters = proc_img.get('counters', {})
    bm_act = pulse.get('bmAct', {})

    path = config.get('path', 'pulse.procImg')
    source_key = config.get('source_key', sensor_key)
    conversion = config.get('conversion')

    if path == 'counters':
        source = counters
    elif path == 'pulse.bmAct':
        source = bm_act
    else:
        source = proc_img

    raw_value = source.get(source_key, 0)

    if conversion == 'ws_to_wh':
        return raw_value / 3600
    if conversion == 'minutes_to_hours':
        return raw_value / 60
    if conversion == 'centivolt_to_volt':
        return raw_value / 100
    if conversion == 'deciamp_to_amp':
        return raw_value / 10
    if conversion == 'decideg_to_deg':
        return raw_value / 10
    return raw_value


def publish_discovery() -> None:
    for sensor_key, config in SENSORS.items():
        topic = f"homeassistant/sensor/{DEVICE_NAME}/{sensor_key}/config"
        payload = {
            'name': config['name'],
            'state_topic': f"homeassistant/sensor/{DEVICE_NAME}/{sensor_key}/state",
            'unit_of_measurement': config['unit'],
            'device_class': config['device_class'],
            'device': {
                'identifiers': [DEVICE_NAME],
                'name': 'Varta Battery',
                'manufacturer': 'Varta',
                'model': 'Battery System',
            },
            'unique_id': f"{DEVICE_NAME}_{sensor_key}",
        }
        safe_publish(topic, json.dumps(payload), retain=True)

    for sensor_key, config in STATUS_SENSORS.items():
        topic = f"homeassistant/sensor/{DEVICE_NAME}/{sensor_key}/config"
        payload = {
            'name': config['name'],
            'state_topic': f"homeassistant/sensor/{DEVICE_NAME}/{sensor_key}/state",
            'icon': config['icon'],
            'device': {
                'identifiers': [DEVICE_NAME],
                'name': 'Varta Battery',
                'manufacturer': 'Varta',
                'model': 'Battery System',
            },
            'unique_id': f"{DEVICE_NAME}_{sensor_key}",
        }
        safe_publish(topic, json.dumps(payload), retain=True)


def perform_login() -> bool:
    global session, last_login_time, error_count, last_error

    current_time = time.time()
    if current_time - last_login_time < LOGIN_COOLDOWN:
        print(f"Login cooldown active. Next login possible in {LOGIN_COOLDOWN - (current_time - last_login_time):.0f}s")
        publish_status('login_status', 'cooldown')
        return False

    try:
        if not LOGIN_URL:
            publish_status('login_status', 'disabled')
            return False

        session = requests.Session()
        login_data = {'username': API_USERNAME, 'password': API_PASSWORD}
        login_response = session.post(LOGIN_URL, data=login_data, timeout=10)

        if login_response.status_code == 200:
            last_login_time = current_time
            print(f"Login successful at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            publish_status('login_status', 'success')
            publish_status('service_status', 'online')
            return True

        error_msg = f"Login failed: {login_response.status_code}"
        print(error_msg)
        last_error = error_msg
        error_count += 1
        publish_status('login_status', 'failed')
        publish_status('last_error', error_msg)
        publish_status('error_count', str(error_count))
        session = None
        return False
    except requests.RequestException as exc:
        error_msg = f"Login error: {exc}"
        print(error_msg)
        last_error = error_msg
        error_count += 1
        publish_status('login_status', 'error')
        publish_status('last_error', error_msg)
        publish_status('error_count', str(error_count))
        publish_status('service_status', 'error')
        session = None
        return False


def fetch_data() -> Optional[Dict[str, Any]]:
    global session, error_count, last_error
    api_url = API_URL or ''

    if session is None:
        if LOGIN_URL and API_USERNAME and API_PASSWORD:
            if not perform_login():
                return None
        else:
            session = requests.Session()

    try:
        assert session is not None
        response = session.get(api_url, timeout=10)
        if response.status_code in [401, 403]:
            print('Session expired, attempting re-login...')
            publish_status('login_status', 'expired')
            if LOGIN_URL and API_USERNAME and API_PASSWORD:
                if perform_login():
                    assert session is not None
                    response = session.get(api_url, timeout=10)
                else:
                    return None
            else:
                return None

        response.raise_for_status()
        data = response.json()
        publish_status('service_status', 'online')
        publish_status('last_update', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        return data
    except requests.RequestException as exc:
        error_msg = f"API fetch error: {exc}"
        print(error_msg)
        last_error = error_msg
        error_count += 1
        publish_status('service_status', 'error')
        publish_status('last_error', error_msg)
        publish_status('error_count', str(error_count))
        return None


def publish_data(data: Dict[str, Any]) -> None:
    for sensor_key in SENSORS:
        if MODBUS_ENABLED and sensor_key in MODBUS_PRIMARY_SENSORS:
            continue

        value = extract_sensor_value(data, sensor_key)
        topic = f"homeassistant/sensor/{DEVICE_NAME}/{sensor_key}/state"
        safe_publish(topic, str(value))


def _publish_power_value(sensor_key: str, value: float) -> None:
    topic = f"homeassistant/sensor/{DEVICE_NAME}/{sensor_key}/state"
    safe_publish(topic, str(value))


def _publish_modbus_source_status(use_fallback: bool) -> None:
    publish_status('fallback_active', 'true' if use_fallback else 'false')
    if use_fallback:
        publish_status('data_source_grid_power', 'api')
        publish_status('data_source_battery_active_power', 'api')
        publish_status('modbus_status', 'offline')
    else:
        publish_status('data_source_grid_power', 'modbus')
        publish_status('data_source_battery_active_power', 'modbus')
        publish_status('modbus_status', 'online')

    publish_status('modbus_error_count', str(modbus_error_count))
    if last_modbus_error:
        publish_status('last_modbus_error', last_modbus_error)


def _get_api_fallback_values() -> Dict[str, float]:
    with api_data_lock:
        if latest_api_data is None:
            return {}
        return {
            'varta_ac_port_power_w': extract_sensor_value(latest_api_data, 'varta_ac_port_power_w'),
            'grid_power_total_w': extract_sensor_value(latest_api_data, 'grid_power_total_w'),
        }


def _publish_averaged_modbus_values(samples: Dict[str, list]) -> bool:
    published_any = False

    for sensor_key in MODBUS_PRIMARY_SENSORS:
        sensor_samples = samples.get(sensor_key, [])
        if not sensor_samples:
            continue

        avg_value = sum(sensor_samples) / len(sensor_samples)
        _publish_power_value(sensor_key, avg_value)
        published_any = True

    return published_any


def run_modbus_loop() -> None:
    global modbus_error_count, last_modbus_error, fallback_active

    assert MODBUS_HOST is not None
    poller = ModbusPoller(
        host=MODBUS_HOST,
        port=MODBUS_PORT,
        unit_id=MODBUS_UNIT_ID,
        timeout=MODBUS_TIMEOUT_SECONDS,
    )

    samples = {key: [] for key in MODBUS_PRIMARY_SENSORS}
    next_publish = time.monotonic() + MODBUS_PUBLISH_INTERVAL_SECONDS

    while True:
        try:
            values = poller.poll_values()
            for sensor_key, value in values.items():
                if sensor_key in samples:
                    samples[sensor_key].append(value)
        except Exception as exc:  # pylint: disable=broad-except
            modbus_error_count += 1
            last_modbus_error = str(exc)

        now = time.monotonic()
        if now >= next_publish:
            published_modbus = _publish_averaged_modbus_values(samples)
            use_fallback = not published_modbus

            if use_fallback:
                fallback_values = _get_api_fallback_values()
                if fallback_values:
                    for sensor_key, value in fallback_values.items():
                        _publish_power_value(sensor_key, value)
                fallback_active = True
            else:
                fallback_active = False

            _publish_modbus_source_status(use_fallback=fallback_active)
            samples = {key: [] for key in MODBUS_PRIMARY_SENSORS}
            next_publish = now + MODBUS_PUBLISH_INTERVAL_SECONDS

        time.sleep(MODBUS_POLLING_INTERVAL_SECONDS)


def run_api_loop() -> None:
    global latest_api_data

    while True:
        data = fetch_data()
        if data:
            with api_data_lock:
                latest_api_data = data
            publish_data(data)
        else:
            wait_time = min(INTERVAL_SECONDS * (2 ** min(error_count, 5)), 60)
            print(f"Error occurred. Waiting {wait_time}s before retry... (Error #{error_count})")
            time.sleep(wait_time)
            continue

        time.sleep(INTERVAL_SECONDS)


def main() -> None:
    print('=' * 60)
    print(f"Varta MQTT Service started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"API: {API_URL}")
    print(f"MQTT Broker: {MQTT_BROKER}:{MQTT_PORT}")
    print(f"API Update Interval: {INTERVAL_SECONDS}s")
    if MODBUS_ENABLED:
        print(f"Modbus: {MODBUS_HOST}:{MODBUS_PORT} (unit_id={MODBUS_UNIT_ID})")
        print(f"Modbus Polling Interval: {MODBUS_POLLING_INTERVAL_SECONDS}s")
        print(f"Modbus Publish Interval: {MODBUS_PUBLISH_INTERVAL_SECONDS}s")
    else:
        print('Modbus disabled (set MODBUS_HOST to enable)')
    print('=' * 60)

    publish_discovery()
    publish_status('service_status', 'starting')
    publish_status('error_count', '0')
    publish_status('modbus_error_count', '0')
    publish_status('fallback_active', 'false')

    if MODBUS_ENABLED:
        modbus_thread = threading.Thread(target=run_modbus_loop, daemon=True, name='modbus-loop')
        modbus_thread.start()

    run_api_loop()


if __name__ == '__main__':
    main()
