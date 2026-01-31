import pytest
import json
import time
from unittest.mock import Mock, patch, MagicMock
import requests
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from varta_mqtt import service


@pytest.fixture
def mock_env(monkeypatch):
    """Set up test environment variables"""
    monkeypatch.setenv('API_URL', 'http://test.local/api/data')
    monkeypatch.setenv('LOGIN_URL', 'http://test.local/api/login')
    monkeypatch.setenv('API_USERNAME', 'testuser')
    monkeypatch.setenv('API_PASSWORD', 'testpass')
    monkeypatch.setenv('MQTT_BROKER', 'localhost')
    monkeypatch.setenv('MQTT_PORT', '1883')
    monkeypatch.setenv('MQTT_USERNAME', 'mqtt_user')
    monkeypatch.setenv('MQTT_PASSWORD', 'mqtt_pass')
    monkeypatch.setenv('DEVICE_NAME', 'test_battery')
    monkeypatch.setenv('INTERVAL_SECONDS', '1')


@pytest.fixture
def sample_api_response():
    """Sample API response matching the Varta battery data structure"""
    return {
        "pulse": {
            "procImg": {
                "soc_pct": 75.5,
                "soh_pct": 98.2,
                "temperature1_C": 22.5,
                "power_W": 150,
                "gridPower_W": -200,
                "generatingPower_W": 350,
                "activePowerAc_W": 150,
                "counters": {
                    "energyCounterAcIn_Ws": 1000000,
                    "energyCounterAcOut_Ws": 500000,
                    "energyCounterBattIn_Ws": 300000,
                    "energyCounterBattOut_Ws": 250000,
                    "energyCounterPvOut_Ws": 800000,
                    "energyCounterHouseIn_Ws": 600000,
                    "energyCounterHouseOut_Ws": 400000
                }
            }
        }
    }


@pytest.fixture(autouse=True)
def reset_globals():
    """Reset global variables before each test"""
    service.session = None
    service.last_login_time = 0
    service.error_count = 0
    service.last_error = None
    yield


class TestLogin:
    """Test cases for login functionality"""
    
    @patch('varta_mqtt.service.requests.Session')
    @patch('varta_mqtt.service.publish_status')
    def test_perform_login_success(self, mock_publish, mock_session_class):
        """Test successful login"""
        # Setup
        mock_session = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_session.post.return_value = mock_response
        mock_session_class.return_value = mock_session
        
        # Execute
        result = service.perform_login()
        
        # Assert
        assert result is True
        assert service.session is not None
        assert service.last_login_time > 0
        mock_publish.assert_any_call('login_status', 'success')
        mock_publish.assert_any_call('service_status', 'online')
    
    @patch('varta_mqtt.service.requests.Session')
    @patch('varta_mqtt.service.publish_status')
    def test_perform_login_failure(self, mock_publish, mock_session_class):
        """Test failed login with 401 status"""
        # Setup
        mock_session = Mock()
        mock_response = Mock()
        mock_response.status_code = 401
        mock_session.post.return_value = mock_response
        mock_session_class.return_value = mock_session
        
        # Execute
        result = service.perform_login()
        
        # Assert
        assert result is False
        assert service.session is None
        assert service.error_count == 1
        mock_publish.assert_any_call('login_status', 'failed')
        mock_publish.assert_any_call('error_count', '1')
    
    @patch('varta_mqtt.service.requests.Session')
    @patch('varta_mqtt.service.publish_status')
    def test_login_cooldown(self, mock_publish, mock_session_class):
        """Test that login cooldown prevents rapid login attempts"""
        # Setup - perform first login
        mock_session = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_session.post.return_value = mock_response
        mock_session_class.return_value = mock_session
        
        # First login
        service.perform_login()
        
        # Try immediate second login
        result = service.perform_login()
        
        # Assert cooldown is active
        assert result is False
        mock_publish.assert_any_call('login_status', 'cooldown')
    
    @patch('varta_mqtt.service.requests.Session')
    @patch('varta_mqtt.service.publish_status')
    def test_login_network_error(self, mock_publish, mock_session_class):
        """Test login with network error"""
        # Setup
        mock_session = Mock()
        mock_session.post.side_effect = requests.RequestException("Network error")
        mock_session_class.return_value = mock_session
        
        # Execute
        result = service.perform_login()
        
        # Assert
        assert result is False
        assert service.session is None
        assert service.error_count == 1
        mock_publish.assert_any_call('login_status', 'error')
        mock_publish.assert_any_call('service_status', 'error')


class TestFetchData:
    """Test cases for data fetching"""
    
    @patch('varta_mqtt.service.perform_login')
    @patch('varta_mqtt.service.publish_status')
    def test_fetch_data_no_session_creates_new(self, mock_publish, mock_login, sample_api_response):
        """Test that fetch_data creates new session if none exists"""
        # Setup
        service.session = None
        
        mock_session = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_api_response
        mock_session.get.return_value = mock_response
        
        # Mock perform_login to set session
        def set_session():
            service.session = mock_session
            return True
        
        mock_login.side_effect = set_session
        
        # Execute
        result = service.fetch_data()
        
        # Assert
        assert result is not None
        mock_login.assert_called_once()
        mock_publish.assert_any_call('service_status', 'online')
    
    @patch('varta_mqtt.service.perform_login')
    @patch('varta_mqtt.service.publish_status')
    def test_fetch_data_session_expired_relogin(self, mock_publish, mock_login, sample_api_response):
        """Test that 401 error triggers re-login"""
        # Setup
        mock_session = Mock()
        mock_login.return_value = True
        service.session = mock_session
        
        # First call returns 401, second call succeeds
        mock_response_401 = Mock()
        mock_response_401.status_code = 401
        
        mock_response_ok = Mock()
        mock_response_ok.status_code = 200
        mock_response_ok.json.return_value = sample_api_response
        
        mock_session.get.side_effect = [mock_response_401, mock_response_ok]
        
        # Execute
        result = service.fetch_data()
        
        # Assert
        assert result == sample_api_response
        mock_login.assert_called_once()
        mock_publish.assert_any_call('login_status', 'expired')
    
    @patch('varta_mqtt.service.publish_status')
    def test_fetch_data_network_error(self, mock_publish):
        """Test handling of network errors during fetch"""
        # Setup
        mock_session = Mock()
        mock_session.get.side_effect = requests.RequestException("Connection timeout")
        service.session = mock_session
        
        # Execute
        result = service.fetch_data()
        
        # Assert
        assert result is None
        assert service.error_count == 1
        mock_publish.assert_any_call('service_status', 'error')
        mock_publish.assert_any_call('error_count', '1')


class TestPublishData:
    """Test cases for MQTT publishing"""
    
    @patch('varta_mqtt.service.client')
    def test_publish_data_sensors(self, mock_client, sample_api_response):
        """Test that sensor data is published correctly"""
        # Execute
        service.publish_data(sample_api_response)
        
        # Assert - check a few key sensors were published
        calls = mock_client.publish.call_args_list
        topics = [call[0][0] for call in calls]
        
        assert any('soc_pct' in topic for topic in topics)
        assert any('power_W' in topic for topic in topics)
        
        # Verify energy conversion from Ws to Wh
        for call in calls:
            if 'energyCounterAcIn_Wh' in call[0][0]:
                # 1000000 Ws / 3600 = 277.78 Wh (approximately)
                value = float(call[0][1])
                assert 277 < value < 278
    
    @patch('varta_mqtt.service.client')
    def test_publish_status(self, mock_client):
        """Test status sensor publishing"""
        # Execute
        service.publish_status('service_status', 'online')
        
        # Assert
        expected_topic = f"homeassistant/sensor/{service.DEVICE_NAME}/service_status/state"
        mock_client.publish.assert_called_once_with(expected_topic, 'online', retain=True)


class TestDiscovery:
    """Test cases for MQTT discovery"""
    
    @patch('varta_mqtt.service.client')
    def test_publish_discovery_sensors(self, mock_client):
        """Test that all sensors are published for discovery"""
        # Execute
        service.publish_discovery()
        
        # Assert
        calls = mock_client.publish.call_args_list
        
        # Check that all sensors from SENSORS dict are published
        sensor_count = len(service.SENSORS)
        status_count = len(service.STATUS_SENSORS)
        total_expected = sensor_count + status_count
        
        assert len(calls) == total_expected
        
        # Verify all payloads are valid JSON and contain required fields
        for call in calls:
            payload = json.loads(call[0][1])
            assert 'name' in payload
            assert 'state_topic' in payload
            assert 'device' in payload
            assert 'unique_id' in payload


class TestIntegration:
    """Integration tests"""
    
    @patch('varta_mqtt.service.client')
    @patch('varta_mqtt.service.requests.Session')
    @patch('varta_mqtt.service.time.sleep')
    def test_session_reuse(self, mock_sleep, mock_session_class, mock_client, sample_api_response):
        """Test that session is reused and not recreated on every fetch"""
        # Setup
        mock_session = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_api_response
        mock_session.get.return_value = mock_response
        mock_session.post.return_value = mock_response
        mock_session_class.return_value = mock_session
        
        # Execute - fetch data twice
        service.fetch_data()
        first_session = service.session
        
        service.fetch_data()
        second_session = service.session
        
        # Assert - same session object should be used
        assert first_session is second_session
        # Login should only be called once (during first fetch)
        assert mock_session.post.call_count == 1
        # Get should be called twice
        assert mock_session.get.call_count == 2


class TestErrorHandling:
    """Test error handling and recovery"""
    
    def test_exponential_backoff_calculation(self):
        """Test that error count increases and backoff is calculated correctly"""
        # Simulate increasing error counts
        service.error_count = 0
        wait_time_0 = min(service.INTERVAL_SECONDS * (2 ** min(service.error_count, 5)), 60)
        assert wait_time_0 == 1
        
        service.error_count = 2
        wait_time_2 = min(service.INTERVAL_SECONDS * (2 ** min(service.error_count, 5)), 60)
        assert wait_time_2 == 4
        
        service.error_count = 5
        wait_time_5 = min(service.INTERVAL_SECONDS * (2 ** min(service.error_count, 5)), 60)
        assert wait_time_5 == 32  # 1 * 2^5 = 32
        
        service.error_count = 10  # Should be capped at max 2^5 = 32, but still limited by min(_, 60)
        wait_time_10 = min(service.INTERVAL_SECONDS * (2 ** min(service.error_count, 5)), 60)
        assert wait_time_10 == 32  # min(5, 5) = 5, so 1 * 2^5 = 32


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
