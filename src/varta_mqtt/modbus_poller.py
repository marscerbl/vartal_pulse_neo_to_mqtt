import logging
from typing import Any, Dict


logger = logging.getLogger(__name__)


class ModbusPoller:
    """Simple Modbus TCP poller for Varta power registers."""

    REGISTER_MAP = {
        "varta_ac_port_power_w": 1066,
        "grid_power_total_w": 1078,
    }

    def __init__(self, host: str, port: int = 502, unit_id: int = 1, timeout: float = 5.0):
        try:
            from pymodbus.client import ModbusTcpClient  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError(
                "pymodbus is required for Modbus support. Install dependencies including pymodbus."
            ) from exc

        self.host = host
        self.port = port
        self.unit_id = unit_id
        self.timeout = timeout
        self._client_type = ModbusTcpClient
        self.client: Any = None

    def connect(self) -> bool:
        """Ensure an active TCP connection to the Modbus endpoint."""
        if self.client is None:
            self.client = self._client_type(host=self.host, port=self.port, timeout=self.timeout)

        if self.client.connected:
            return True

        return bool(self.client.connect())

    def close(self) -> None:
        if self.client is not None:
            try:
                self.client.close()
            finally:
                self.client = None

    @staticmethod
    def _to_int16(value: int) -> int:
        """Convert unsigned 16-bit register value to signed int16."""
        if value >= 0x8000:
            return value - 0x10000
        return value

    def _read_int16_register(self, address: int) -> int:
        if not self.connect():
            raise ConnectionError("Modbus connection failed")

        assert self.client is not None
        try:
            response = self.client.read_holding_registers(address=address, count=1, slave=self.unit_id)
        except TypeError:
            # Older pymodbus versions use "unit" instead of "slave".
            response = self.client.read_holding_registers(address=address, count=1, unit=self.unit_id)
        if response.isError():
            raise RuntimeError(f"Modbus read error at address {address}: {response}")

        if not hasattr(response, "registers") or len(response.registers) < 1:
            raise RuntimeError(f"No register data returned for address {address}")

        return self._to_int16(int(response.registers[0]))

    def poll_values(self) -> Dict[str, int]:
        """Poll all required power values from Modbus."""
        values: Dict[str, int] = {}
        for sensor_key, address in self.REGISTER_MAP.items():
            values[sensor_key] = self._read_int16_register(address)
        return values
