"""Links to the car.

SerialGatewayLink talks to the ESP32-C3 USB gateway, which relays over ESP-NOW:
  PC -> gateway : "D,<left_pwm>,<right_pwm>\\n"   (-255..255)
                  "G,<cm>\\n"                     car's on-board collision guard, 0 = off
                  "B\\n"                          beep on the car
  gateway -> PC : "T,<l_cm>,<f_cm>,<r_cm>,<battery_v>[,<flags>,<car_rssi>,<gw_rssi>,<rtt_ms>,<pwm_l>,<pwm_r>]\\n"
                  "S,<car_ok>,<loss_pct>,<telemetry_hz>,<channel>\\n"   once a second
The fields in [] come from the v2 firmware; v1 lines (first four only) still parse.
Any other line from the gateway is shown in the app log.
"""

import logging
import queue
import sys
import threading
import time
from dataclasses import dataclass
from typing import List, Optional, Tuple

log = logging.getLogger("markerpilot.link")

# USB vendor IDs of common ESP32 boards / USB-serial chips
ESP_VIDS = {0x303A: "Espressif USB", 0x10C4: "CP210x", 0x1A86: "CH340", 0x0403: "FTDI"}


# Telemetry flag bits (v2 firmware)
F_GUARD = 1
F_FAULT_L, F_FAULT_F, F_FAULT_R = 2, 4, 8
F_LINKED = 16


@dataclass
class Telemetry:
    left_cm: float
    front_cm: float
    right_cm: float
    battery_v: float
    stamp: float
    flags: int = 0
    car_rssi: Optional[int] = None     # dBm the car hears the gateway at
    gw_rssi: Optional[int] = None      # dBm the gateway hears the car at
    rtt_ms: Optional[float] = None     # command -> acknowledged in telemetry
    pwm: Optional[Tuple[int, int]] = None

    @property
    def sonar(self) -> Tuple[float, float, float]:
        return self.left_cm, self.front_cm, self.right_cm

    @property
    def guard_holding(self) -> bool:
        return bool(self.flags & F_GUARD)

    @property
    def sonar_faults(self) -> List[str]:
        return [n for n, b in (("left", F_FAULT_L), ("front", F_FAULT_F), ("right", F_FAULT_R)) if self.flags & b]


@dataclass
class LinkStatus:
    car_ok: bool
    loss_pct: int
    telemetry_hz: float
    channel: int
    stamp: float


class Link:
    name = "link"

    def __init__(self):
        self.messages: "queue.Queue[str]" = queue.Queue()
        self.telemetry: Optional[Telemetry] = None
        self.status: Optional[LinkStatus] = None
        self.tx_count = 0
        self.rx_count = 0

    def connect(self) -> bool:
        return True

    def close(self) -> None:
        pass

    def send(self, left: int, right: int) -> None:
        raise NotImplementedError

    def beep(self) -> None:
        pass

    def set_guard(self, cm: int) -> None:
        """On-board collision guard on the car (front sonar), 0 = off."""
        pass

    def radio_summary(self) -> str:
        t, s = self.telemetry, self.status
        if t is None or t.car_rssi is None:
            return "—"
        parts = [f"car {t.car_rssi} dBm", f"gw {t.gw_rssi} dBm"]
        if t.rtt_ms:
            parts.append(f"{t.rtt_ms:.0f} ms")
        if s is not None:
            parts.append(f"loss {s.loss_pct}%")
        return " · ".join(parts)

    def fresh_telemetry(self, timeout_s: float) -> Optional[Telemetry]:
        t = self.telemetry
        return t if t is not None and time.time() - t.stamp < timeout_s else None

    def connected(self, timeout_s: float) -> bool:
        return self.fresh_telemetry(timeout_s) is not None


GATEWAY_VID = 0x303A   # ESP32-C3 native USB: the MarkerPilot gateway


def _kind(p) -> str:
    """'gateway', 'usb-serial' or 'other'. Falls back to the device name when
    the OS doesn't report USB IDs (pyserial on some macOS setups)."""
    vid, name = p.vid or -1, p.device.lower()
    if vid == GATEWAY_VID or (vid == -1 and ("usbmodem" in name or "ttyacm" in name)):
        return "gateway"
    if vid in ESP_VIDS or any(k in name for k in ("usbserial", "slab_usbtouart", "wchusbserial", "ttyusb")):
        return "usb-serial"
    return "other"


def list_serial_ports() -> List[Tuple[str, str]]:
    """(device, description), the gateway first. Other USB-serial chips are
    usually the car's own programming cable, which is not the radio link."""
    try:
        from serial.tools import list_ports
    except ImportError:
        return []
    ports = []
    for p in list_ports.comports():
        if p.device.startswith("/dev/cu.Bluetooth") or "Bluetooth" in (p.description or ""):
            continue
        if sys.platform == "darwin" and p.device.startswith("/dev/tty."):
            continue          # macOS lists each port twice; the cu. one is right for us
        kind = _kind(p)
        if kind == "gateway":
            rank, desc = 0, f"{p.device} · ESP32-C3 gateway"
        elif kind == "usb-serial":
            rank, desc = 1, f"{p.device} · USB-serial (car cable, not the gateway)"
        elif sys.platform == "darwin":
            continue          # Bluetooth headphones, debug ports...
        else:
            rank, desc = 2, f"{p.device} · {p.description if p.description not in (None, 'n/a') else 'serial'}"
        ports.append((rank, p.device, desc))
    ports.sort()
    return [(d, desc) for _, d, desc in ports]


def find_gateway_port() -> Optional[str]:
    """The ESP32-C3 gateway's port, or None if it isn't plugged in."""
    try:
        from serial.tools import list_ports
    except ImportError:
        return None
    for p in list_ports.comports():
        if _kind(p) == "gateway":
            return p.device
    return None


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

    def _write(self, text: str) -> bool:
        if self._ser is None:
            return False
        try:
            with self._lock:
                self._ser.write(text.encode())
            return True
        except Exception as e:
            self.messages.put(f"Serial write failed: {e}")
            self._running = False
            self._ser = None
            return False

    def send(self, left: int, right: int) -> None:
        if self._write(f"D,{int(left)},{int(right)}\n"):
            self.tx_count += 1

    def beep(self) -> None:
        self._write("B\n")

    def set_guard(self, cm: int) -> None:
        self._write(f"G,{max(0, min(100, int(cm)))}\n")

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
            try:
                vals = [float(p) for p in line[2:].split(",")]
            except ValueError:
                return
            if len(vals) < 4:
                return
            t = Telemetry(vals[0], vals[1], vals[2], vals[3], time.time())
            if len(vals) >= 10:
                t.flags = int(vals[4])
                t.car_rssi, t.gw_rssi = int(vals[5]), int(vals[6])
                t.rtt_ms = vals[7]
                t.pwm = (int(vals[8]), int(vals[9]))
            self.telemetry = t
            self.rx_count += 1
        elif line.startswith("S,"):
            try:
                ok, loss, hz, ch = line[2:].split(",")[:4]
                self.status = LinkStatus(ok == "1", int(loss), float(hz), int(ch), time.time())
            except ValueError:
                return
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
