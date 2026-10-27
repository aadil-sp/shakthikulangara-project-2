"""Configuration with JSON persistence in the user's home folder."""

import json
import logging
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

log = logging.getLogger("markerpilot.config")

CONFIG_DIR = Path.home() / ".markerpilot"
CONFIG_FILE = CONFIG_DIR / "config.json"


@dataclass
class VisionConfig:
    dictionary: str = "DICT_4X4_50"
    car_marker_id: int = 0          # Marker on top of the car
    goal_marker_id: int = -1        # -1 = any other marker is a goal
    marker_size_cm: float = 5.0     # Printed side length of the car marker
    heading_offset_deg: float = 0.0  # 180 if the marker is mounted backwards
    frame_width: int = 1280
    frame_height: int = 720
    mirror_view: bool = False       # Flip the camera image horizontally


@dataclass
class ControlConfig:
    mode: str = "classic"           # "classic" or "rl"
    speed: float = 0.7              # 0..1 overall speed limit
    max_pwm: int = 255
    min_pwm: int = 70               # PWM where the motors just start turning
    arrive_cm: float = 4.0          # Goal reached inside this radius
    brake_cm: float = 30.0          # Start slowing down inside this distance
    pivot_deg: float = 55.0         # Turn on the spot above this heading error
    kp_turn: float = 1.4
    kd_turn: float = 0.12
    slew_per_s: float = 3.0         # Max change of normalised command per second
    invert_throttle: bool = False
    invert_steering: bool = False
    auto_polarity: bool = True      # Detect reversed motor wiring automatically
    follow_goal_marker: bool = True
    rl_learn_online: bool = False


@dataclass
class ObstacleConfig:
    enabled: bool = True
    warn_cm: float = 35.0
    stop_cm: float = 15.0


@dataclass
class LinkConfig:
    mode: str = "sim"               # "sim" or "serial"
    serial_port: str = ""           # Empty = auto-detect ESP32 gateway
    baudrate: int = 115200
    send_hz: float = 20.0
    timeout_s: float = 1.0


@dataclass
class AppConfig:
    vision: VisionConfig = field(default_factory=VisionConfig)
    control: ControlConfig = field(default_factory=ControlConfig)
    obstacle: ObstacleConfig = field(default_factory=ObstacleConfig)
    link: LinkConfig = field(default_factory=LinkConfig)
    last_camera: str = "sim"

    def save(self, path: Path = CONFIG_FILE) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(asdict(self), indent=2))
        except OSError as e:
            log.warning("Could not save config: %s", e)

    @classmethod
    def load(cls, path: Path = CONFIG_FILE) -> "AppConfig":
        cfg = cls()
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError):
            return cfg
        for section in fields(cls):
            value = data.get(section.name)
            current = getattr(cfg, section.name)
            if isinstance(value, dict) and hasattr(current, "__dataclass_fields__"):
                for f in fields(current):
                    if f.name in value and isinstance(value[f.name], type(getattr(current, f.name))):
                        setattr(current, f.name, value[f.name])
            elif value is not None and isinstance(value, type(current)):
                setattr(cfg, section.name, value)
        return cfg
