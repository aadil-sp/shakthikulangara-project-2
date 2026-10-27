"""Links to the car.

SerialGatewayLink talks to the ESP32-C3 USB gateway, which relays over ESP-NOW:
  PC -> gateway : "D,<left_pwm>,<right_pwm>\\n"        (-255..255)
  gateway -> PC : "T,<left_cm>,<front_cm>,<right_cm>,<battery_v>\\n"
Any other line from the gateway is shown in the app log.
"""

import logging
import queue
import threading
import time
from dataclasses import dataclass
from typing import List, Optional, Tuple

log = logging.getLogger("markerpilot.link")

# USB vendor IDs of common ESP32 boards / USB-serial chips
ESP_VIDS = {0x303A: "Espressif USB", 0x10C4: "CP210x", 0x1A86: "CH340", 0x0403: "FTDI"}


@dataclass
class Telemetry:
    left_cm: float
    front_cm: float
    right_cm: float
    battery_v: float
    stamp: float

    @property
    def sonar(self) -> Tuple[float, float, float]:
        return self.left_cm, self.front_cm, self.right_cm


class Link:
    name = "link"

    def __init__(self):
        self.messages: "queue.Queue[str]" = queue.Queue()
        self.telemetry: Optional[Telemetry] = None
        self.tx_count = 0
        self.rx_count = 0

    def connect(self) -> bool:
        return True

    def close(self) -> None:
        pass

    def send(self, left: int, right: int) -> None:
        raise NotImplementedError

    def fresh_telemetry(self, timeout_s: float) -> Optional[Telemetry]:
        t = self.telemetry
        return t if t is not None and time.time() - t.stamp < timeout_s else None

    def connected(self, timeout_s: float) -> bool:
        return self.fresh_telemetry(timeout_s) is not None


def list_serial_ports() -> List[Tuple[str, str]]:
    """(device, description), ESP32-looking ports first."""
    try:
        from serial.tools import list_ports
    except ImportError:
        return []
    ports = []
    for p in list_ports.comports():
        if p.device.startswith("/dev/cu.Bluetooth") or "Bluetooth" in (p.description or ""):
            continue
        hint = ESP_VIDS.get(p.vid or -1)
        desc = f"{p.device} · {hint or p.description or 'serial'}"
        ports.append((0 if hint else 1, p.device, desc))
    ports.sort()
    return [(d, desc) for _, d, desc in ports]


def find_gateway_port() -> Optional[str]:
    ports = list_serial_ports()
    try:
        from serial.tools import list_ports
        for p in list_ports.comports():
            if (p.vid or -1) in ESP_VIDS:
                return p.device
    except ImportError:
        pass
    return ports[0][0] if ports else None


class SerialGatewayLink(Link):
    name = "ESP-NOW gateway"

    def __init__(self, port: str = "", baudrate: int = 115200):
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self._ser = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def connect(self) -> bool:
        import serial
        port = self.port or find_gateway_port()
        if not port:
            self.messages.put("No serial port found - plug in the ESP32-C3 gateway")
            return False
        try:
            self._ser = serial.Serial(port, self.baudrate, timeout=0.1, write_timeout=0.2)
        except (serial.SerialException, OSError) as e:
            self.messages.put(f"Cannot open {port}: {e}")
            return False
        self.port = port
        self._running = True
        self._thread = threading.Thread(target=self._reader, daemon=True)
        self._thread.start()
        self.messages.put(f"Opened gateway on {port}")
        return True

    def close(self) -> None:
        self._running = False
        if self._ser is not None:
            try:
                self.send(0, 0)
                self._ser.close()
            except Exception:
                pass
        self._ser = None

    def send(self, left: int, right: int) -> None:
        if self._ser is None:
            return
        try:
            with self._lock:
                self._ser.write(f"D,{int(left)},{int(right)}\n".encode())
            self.tx_count += 1
        except Exception as e:
            self.messages.put(f"Serial write failed: {e}")
            self._running = False
            self._ser = None

    def _reader(self) -> None:
        buf = b""
        while self._running and self._ser is not None:
            try:
                chunk = self._ser.read(256)
            except Exception as e:
                self.messages.put(f"Gateway disconnected: {e}")
                self._ser = None
                break
            if not chunk:
                continue
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                self._handle(line.decode(errors="replace").strip())

    def _handle(self, line: str) -> None:
        if not line:
            return
        if line.startswith("T,"):
            parts = line[2:].split(",")
            try:
                vals = [float(p) for p in parts[:4]]
            except ValueError:
                return
            if len(vals) == 4:
                self.telemetry = Telemetry(vals[0], vals[1], vals[2], vals[3], time.time())
                self.rx_count += 1
        else:
            self.messages.put(f"[gateway] {line}")


class SimLink(Link):
    name = "Simulator"

    def __init__(self, car):
        super().__init__()
        self.car = car

    def send(self, left: int, right: int) -> None:
        self.car.command(left, right)
        self.tx_count += 1

    def poll(self) -> None:
        l, f, r = self.car.sonar()
        self.telemetry = Telemetry(l, f, r, 7.4, time.time())
        self.rx_count += 1
