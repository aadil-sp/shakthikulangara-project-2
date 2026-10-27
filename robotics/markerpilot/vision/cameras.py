"""Cross-platform camera discovery and threaded capture (Windows, Linux, macOS)."""

import glob
import logging
import os
import platform
import re
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import List, Optional, Tuple, Union

import cv2
import numpy as np

log = logging.getLogger("markerpilot.cameras")
SYSTEM = platform.system()


@dataclass
class CameraInfo:
    source: Union[int, str]   # Device index or stream URL
    name: str
    width: int = 0
    height: int = 0

    @property
    def label(self) -> str:
        res = f" · {self.width}×{self.height}" if self.width else ""
        return f"{self.name}{res}"


def _backend() -> int:
    if SYSTEM == "Windows":
        return cv2.CAP_DSHOW
    if SYSTEM == "Darwin":
        return cv2.CAP_AVFOUNDATION
    if SYSTEM == "Linux":
        return cv2.CAP_V4L2
    return cv2.CAP_ANY


def _linux_devices() -> List[Tuple[int, str]]:
    devices = []
    for path in sorted(glob.glob("/dev/video*"), key=lambda p: int(re.sub(r"\D", "", p) or 0)):
        idx = int(re.sub(r"\D", "", path) or 0)
        name = f"Camera {idx}"
        try:
            with open(f"/sys/class/video4linux/video{idx}/name") as f:
                name = f.read().strip() or name
        except OSError:
            pass
        devices.append((idx, name))
    return devices


def _mac_names() -> List[str]:
    try:
        out = subprocess.run(["system_profiler", "SPCameraDataType"], capture_output=True,
                             text=True, timeout=6).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return [line.strip().rstrip(":") for line in out.splitlines()
            if line.startswith("    ") and not line.startswith("      ") and line.strip().endswith(":")]


def _windows_names() -> List[str]:
    cmd = ("Get-CimInstance Win32_PnPEntity | Where-Object { $_.PNPClass -in 'Camera','Image' } "
           "| Select-Object -ExpandProperty Name")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True,
                             text=True, timeout=8, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]


def open_capture(source: Union[int, str]) -> cv2.VideoCapture:
    if isinstance(source, str):
        return cv2.VideoCapture(source)
    cap = cv2.VideoCapture(source, _backend())
    if not cap.isOpened():
        cap.release()
        cap = cv2.VideoCapture(source)
    return cap


def _probe(index: int) -> Optional[Tuple[int, int]]:
    cap = open_capture(index)
    try:
        if not cap.isOpened():
            return None
        for _ in range(5):
            ok, frame = cap.read()
            if ok and frame is not None and frame.size:
                return frame.shape[1], frame.shape[0]
            time.sleep(0.05)
        return None
    finally:
        cap.release()


def list_cameras(max_index: int = 10) -> List[CameraInfo]:
    """Return every camera that actually delivers frames."""
    cameras: List[CameraInfo] = []
    if SYSTEM == "Linux":
        candidates = _linux_devices()
    else:
        names = _mac_names() if SYSTEM == "Darwin" else _windows_names() if SYSTEM == "Windows" else []
        candidates = [(i, names[i] if i < len(names) else f"Camera {i}") for i in range(max_index)]

    misses = 0
    for idx, name in candidates:
        res = _probe(idx)
        if res:
            cameras.append(CameraInfo(idx, f"[{idx}] {name}", *res))
            misses = 0
        else:
            misses += 1
            # Indices are contiguous on Windows/macOS; stop after a run of gaps
            if SYSTEM != "Linux" and misses >= 3:
                break
    log.info("Found %d camera(s)", len(cameras))
    return cameras


class CameraSource:
    """Grabs frames on a background thread so the UI never blocks on the camera."""

    def __init__(self, source: Union[int, str], width: int = 1280, height: int = 720):
        self.source = source
        self.width, self.height = width, height
        self._frame: Optional[np.ndarray] = None
        self._stamp = 0.0
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self.fps = 0.0
        self.error = ""
        self._cap: Optional[cv2.VideoCapture] = None

    def start(self) -> None:
        # macOS only allows camera permission requests from the main thread, so
        # the device is opened here and the thread only reads frames
        self._cap = self._open()
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _open(self) -> Optional[cv2.VideoCapture]:
        cap = open_capture(self.source)
        if not cap.isOpened():
            self.error = f"Cannot open camera {self.source}"
            cap.release()
            return None
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.error = ""
        return cap

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)

    def read(self) -> Tuple[Optional[np.ndarray], float]:
        with self._lock:
            return self._frame, self._stamp

    def _loop(self) -> None:
        cap = self._cap
        frames, t0 = 0, time.time()
        while self._running:
            if cap is None or not cap.isOpened():
                if SYSTEM == "Darwin":
                    self.error = self.error or "Camera unavailable - allow camera access, then pick the camera again"
                    time.sleep(0.5)
                    continue
                cap = self._open()
                if cap is None:
                    time.sleep(1.0)
                    continue
            ok, frame = cap.read()
            if not ok or frame is None:
                self.error = "Camera stopped sending frames - reconnecting"
                cap.release()
                cap = None
                time.sleep(0.5)
                continue
            with self._lock:
                self._frame, self._stamp = frame, time.time()
            frames += 1
            if time.time() - t0 >= 1.0:
                self.fps = frames / (time.time() - t0)
                frames, t0 = 0, time.time()
        if cap is not None:
            cap.release()


def quiet_opencv_logs() -> None:
    os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")
    os.environ.setdefault("OPENCV_VIDEOIO_PRIORITY_OBSENSOR", "0")
    try:
        cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_ERROR)
    except AttributeError:
        pass
