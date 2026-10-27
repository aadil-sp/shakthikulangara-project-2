"""MarkerPilot desktop app (PyQt6)."""

import math
import queue
import sys
import threading
import time
from typing import List, Optional

import cv2
import numpy as np
from PyQt6.QtCore import QPoint, QRect, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QImage, QKeySequence, QPixmap, QShortcut
from PyQt6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout, QInputDialog,
                             QLabel, QMainWindow, QPlainTextEdit, QProgressBar, QPushButton, QScrollArea, QSlider,
                             QSplitter, QVBoxLayout, QWidget)

from markerpilot import APP_NAME, __version__
from markerpilot.comm.links import SerialGatewayLink, SimLink, find_gateway_port, list_serial_ports
from markerpilot.config import AppConfig
from markerpilot.control.rl import QAgent
from markerpilot.engine import Engine
from markerpilot.sim.world import SimWorld
from markerpilot.vision import overlays
from markerpilot.vision import cameras
from markerpilot.vision.cameras import CameraSource, list_cameras

STYLE = """
* { font-size: 13px; color: #e8ebf4; }
QMainWindow, QWidget#root { background: #0d111c; }
QScrollArea, QWidget#side { background: #121828; border: none; }
QLabel#title { font-size: 18px; font-weight: 700; }
QLabel#sub { color: #8b93ad; font-size: 11px; }
QLabel#section { color: #7dd3fc; font-size: 11px; font-weight: 700; letter-spacing: 1px; padding-top: 10px; }
QLabel#value { font-weight: 600; }
QLabel#pill { border-radius: 9px; padding: 2px 10px; font-weight: 700; font-size: 11px; }
QComboBox, QPushButton { background: #1b2338; border: 1px solid #2a3452; border-radius: 7px; padding: 6px 10px; }
QComboBox:hover, QPushButton:hover { border-color: #3b82f6; }
QComboBox QAbstractItemView { background: #1b2338; selection-background-color: #2563eb; }
QPushButton#estop { background: #dc2626; border: none; font-size: 17px; font-weight: 800; padding: 14px; }
QPushButton#estop:checked { background: #f59e0b; color: #111; }
QPushButton#primary { background: #2563eb; border: none; font-weight: 600; }
QCheckBox { spacing: 8px; }
QSlider::groove:horizontal { height: 6px; background: #2a3452; border-radius: 3px; }
QSlider::handle:horizontal { background: #3b82f6; width: 16px; margin: -6px 0; border-radius: 8px; }
QProgressBar { background: #1b2338; border: none; border-radius: 4px; height: 10px; text-align: center; font-size: 10px; }
QProgressBar::chunk { border-radius: 4px; background: #22c55e; }
QPlainTextEdit { background: #090c14; border: none; font-family: Menlo, Consolas, monospace; font-size: 11px; color: #a9b3cc; }
QSplitter::handle { background: #1b2338; }
"""


class VideoView(QLabel):
    clicked = pyqtSignal(float, float, object, object)   # frame x, y, button, modifiers

    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(480, 270)
        self.setStyleSheet("background:#05070c;")
        self._frame_size = (1280, 720)
        self._shown = QRect()

    def show_frame(self, img: np.ndarray) -> None:
        h, w = img.shape[:2]
        self._frame_size = (w, h)
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        qimg = QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888)
        pix = QPixmap.fromImage(qimg).scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                             Qt.TransformationMode.SmoothTransformation)
        x = (self.width() - pix.width()) // 2
        y = (self.height() - pix.height()) // 2
        self._shown = QRect(x, y, pix.width(), pix.height())
        self.setPixmap(pix)

    def mousePressEvent(self, e):
        p: QPoint = e.position().toPoint()
        if not self._shown.contains(p) or self._shown.width() == 0:
            return
        fx = (p.x() - self._shown.x()) / self._shown.width() * self._frame_size[0]
        fy = (p.y() - self._shown.y()) / self._shown.height() * self._frame_size[1]
        self.clicked.emit(fx, fy, e.button(), e.modifiers())


def bar(color: str = "#22c55e") -> QProgressBar:
    b = QProgressBar()
    b.setTextVisible(False)
    b.setFixedHeight(10)
    b.setStyleSheet(f"QProgressBar::chunk {{ background: {color}; border-radius: 4px; }}")
    return b


class MainWindow(QMainWindow):
    def __init__(self, cfg: AppConfig, args):
        super().__init__()
        self.cfg = cfg
        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.resize(1440, 860)
        self.engine = Engine(cfg)
        self.world = SimWorld(cfg.vision.frame_width, cfg.vision.frame_height, cfg.vision.dictionary,
                              cfg.vision.car_marker_id, cfg.vision.marker_size_cm)
        self.camera: Optional[CameraSource] = None
        self.source = "sim"
        self.link = SimLink(self.world.car)
        self._t_prev = time.monotonic()
        self._last_send = 0.0
        self._last_panel = 0.0
        self._keys = set()
        self._fps, self._fps_n, self._fps_t = 0.0, 0, time.monotonic()
        self._cams_result: Optional[list] = None
        self._cams_found: Optional[queue.Queue] = None
        self._train_thread: Optional[threading.Thread] = None
        self._train_msgs: "queue.Queue[str]" = queue.Queue()
        self._out = None

        self._build_ui()
        self._build_shortcuts()
        self.log(f"{APP_NAME} {__version__} ready. RL policy: {self.engine.policy_source}")
        self.log("Click on the video to send the car there. Shift+click adds waypoints, right-click clears.")
        self.refresh_cameras()
        self.refresh_ports()

        if args is not None and getattr(args, "camera", None) is not None and not args.sim:
            src = int(args.camera) if str(args.camera).isdigit() else args.camera
            self.open_camera(src)
        if args is not None and getattr(args, "port", None):
            self.cfg.link.serial_port = args.port

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(30)

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        root = QWidget(objectName="root")
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        left = QSplitter(Qt.Orientation.Vertical)
        self.video = VideoView()
        self.video.clicked.connect(self.on_video_click)
        left.addWidget(self.video)
        self.console = QPlainTextEdit(readOnly=True)
        self.console.setMaximumBlockCount(500)
        left.addWidget(self.console)
        left.setSizes([700, 150])
        outer.addWidget(left, 1)

        side = QWidget(objectName="side")
        lay = QVBoxLayout(side)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(6)
        scroll = QScrollArea()
        scroll.setWidget(side)
        scroll.setWidgetResizable(True)
        scroll.setFixedWidth(360)
        outer.addWidget(scroll)

        head = QHBoxLayout()
        tbox = QVBoxLayout()
        tbox.addWidget(QLabel(APP_NAME, objectName="title"))
        tbox.addWidget(QLabel("ArUco overhead-camera navigation", objectName="sub"))
        head.addLayout(tbox)
        head.addStretch()
        self.link_pill = QLabel("SIM", objectName="pill")
        head.addWidget(self.link_pill)
        lay.addLayout(head)

        def section(text):
            lay.addWidget(QLabel(text.upper(), objectName="section"))

        section("Camera")
        row = QHBoxLayout()
        self.cam_combo = QComboBox()
        self.cam_combo.activated.connect(self.on_camera_chosen)
        row.addWidget(self.cam_combo, 1)
        b = QPushButton("⟳")
        b.setToolTip("Search for cameras again")
        b.clicked.connect(self.refresh_cameras)
        row.addWidget(b)
        lay.addLayout(row)
        self.mirror_cb = QCheckBox("Mirror camera image")
        self.mirror_cb.setChecked(self.cfg.vision.mirror_view)
        self.mirror_cb.toggled.connect(lambda v: setattr(self.cfg.vision, "mirror_view", v))
        lay.addWidget(self.mirror_cb)

        section("Robot link")
        row = QHBoxLayout()
        self.port_combo = QComboBox()
        self.port_combo.activated.connect(self.on_port_chosen)
        row.addWidget(self.port_combo, 1)
        b = QPushButton("⟳")
        b.setToolTip("Search for serial ports again")
        b.clicked.connect(self.refresh_ports)
        row.addWidget(b)
        lay.addLayout(row)

        self.estop_btn = QPushButton("EMERGENCY STOP  (Space)", objectName="estop", checkable=True)
        self.estop_btn.toggled.connect(self.on_estop)
        lay.addWidget(self.estop_btn)
        row = QHBoxLayout()
        b = QPushButton("Clear path (C)")
        b.clicked.connect(self.engine.clear_path)
        row.addWidget(b)
        b = QPushButton("Flip marker 180°")
        b.clicked.connect(self.on_flip)
        row.addWidget(b)
        lay.addLayout(row)

        section("Navigation")
        row = QHBoxLayout()
        row.addWidget(QLabel("Brain"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Classic controller", "classic")
        self.mode_combo.addItem("Reinforcement learning", "rl")
        self.mode_combo.setCurrentIndex(1 if self.cfg.control.mode == "rl" else 0)
        self.mode_combo.currentIndexChanged.connect(self.on_mode)
        row.addWidget(self.mode_combo, 1)
        lay.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(QLabel("Speed"))
        self.speed = QSlider(Qt.Orientation.Horizontal)
        self.speed.setRange(20, 100)
        self.speed.setValue(int(self.cfg.control.speed * 100))
        self.speed.valueChanged.connect(self.on_speed)
        row.addWidget(self.speed, 1)
        self.speed_lbl = QLabel(f"{self.speed.value()}%")
        row.addWidget(self.speed_lbl)
        lay.addLayout(row)

        def check(text, obj, attr, tip=""):
            cb = QCheckBox(text)
            cb.setChecked(getattr(obj, attr))
            cb.setToolTip(tip)
            cb.toggled.connect(lambda v: setattr(obj, attr, v))
            lay.addWidget(cb)
            return cb

        check("Follow goal marker", self.cfg.control, "follow_goal_marker", "Drive to any marker that is not the car")
        check("Obstacle avoidance (ultrasonic)", self.cfg.obstacle, "enabled")
        self.auto_pol_cb = check("Auto-detect motor direction", self.cfg.control, "auto_polarity",
                                 "Watches the camera and fixes reversed motor wiring by itself")
        self.inv_t_cb = check("Invert throttle (motors reversed)", self.cfg.control, "invert_throttle")
        self.inv_s_cb = check("Invert steering (left/right swapped)", self.cfg.control, "invert_steering")
        self.learn_cb = check("RL: keep learning while driving", self.cfg.control, "rl_learn_online")

        section("Live telemetry")
        grid = QGridLayout()
        grid.setVerticalSpacing(4)
        self.t_labels = {}
        rows = [("pose", "Position"), ("heading", "Heading"), ("speed", "Speed"), ("target", "To target"),
                ("status", "Doing"), ("fps", "Camera / loop"), ("radio", "Radio")]
        for i, (key, text) in enumerate(rows):
            grid.addWidget(QLabel(text), i, 0)
            lbl = QLabel("—", objectName="value")
            lbl.setWordWrap(True)
            grid.addWidget(lbl, i, 1)
            self.t_labels[key] = lbl
        lay.addLayout(grid)

        grid = QGridLayout()
        self.bars = {}
        for i, (key, text, color) in enumerate([("pwm_l", "Left motor", "#3b82f6"), ("pwm_r", "Right motor", "#3b82f6"),
                                                 ("s_l", "Sonar left", "#22c55e"), ("s_f", "Sonar front", "#22c55e"),
                                                 ("s_r", "Sonar right", "#22c55e")]):
            grid.addWidget(QLabel(text), i, 0)
            b = bar(color)
            grid.addWidget(b, i, 1)
            lbl = QLabel("—")
            lbl.setFixedWidth(56)
            grid.addWidget(lbl, i, 2)
            self.bars[key] = (b, lbl)
        lay.addLayout(grid)

        section("Reinforcement learning")
        self.rl_lbl = QLabel("—")
        self.rl_lbl.setWordWrap(True)
        lay.addWidget(self.rl_lbl)
        self.train_btn = QPushButton("Train RL in simulator (≈2 min)", objectName="primary")
        self.train_btn.clicked.connect(self.on_train)
        lay.addWidget(self.train_btn)

        section("Simulator")
        row = QHBoxLayout()
        for text, fn in (("Reset car", self.world.reset_car), ("Obstacles", self.world.random_obstacles),
                         ("Clear", self.world.clear_obstacles)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            row.addWidget(b)
        lay.addLayout(row)
        tip = QLabel("Ctrl/Cmd+click moves the goal marker. Keys: WASD drive by hand, "
                     "Space stop, C clear, F11 full screen.", objectName="sub")
        tip.setWordWrap(True)
        lay.addWidget(tip)
        lay.addStretch()

    def _build_shortcuts(self) -> None:
        QShortcut(QKeySequence("Space"), self, activated=self.estop_btn.toggle)
        QShortcut(QKeySequence("C"), self, activated=self.engine.clear_path)
        QShortcut(QKeySequence("F11"), self, activated=self.toggle_fullscreen)
        QShortcut(QKeySequence("Escape"), self, activated=self.showNormal)

    # -------------------------------------------------------------- helpers
    def log(self, msg: str) -> None:
        self.console.appendPlainText(time.strftime("%H:%M:%S  ") + msg)

    def toggle_fullscreen(self) -> None:
        self.showNormal() if self.isFullScreen() else self.showFullScreen()

    def refresh_cameras(self) -> None:
        self.cam_combo.clear()
        self.cam_combo.addItem("Simulator (virtual camera)", "sim")
        self.cam_combo.addItem("Searching for cameras…", None)
        self.cam_combo.addItem("Add network / phone camera URL…", "url")

        self._cams_found = queue.Queue()

        def worker():
            try:
                self._cams_result = list_cameras(on_found=self._cams_found.put)
            except Exception as e:     # never let discovery kill the app
                self._cams_result = []
                self._train_msgs.put(f"Camera search failed: {e}")
            if cameras.ACCESS_ERROR:
                self._train_msgs.put(cameras.ACCESS_ERROR)
        # On macOS the search runs in a helper process, so a thread is safe everywhere
        threading.Thread(target=worker, daemon=True).start()

    def _add_camera(self, c) -> None:
        """List one camera as soon as the search finds it."""
        if self.cam_combo.findData(c.source) >= 0:
            return
        searching = self.cam_combo.findData(None)
        pos = searching if searching >= 0 else self.cam_combo.count() - 1
        self.cam_combo.insertItem(pos, f"📷 {c.label}", c.source)
        searching = self.cam_combo.findData(None)
        if searching >= 0:
            n = self.cam_combo.count() - 3
            self.cam_combo.setItemText(searching, f"Searching for more cameras… ({n} found)")

    def _fill_cameras(self, cams: List) -> None:
        for c in cams:
            self._add_camera(c)
        idx = self.cam_combo.findData(None)
        if idx >= 0:
            self.cam_combo.removeItem(idx)
        self.log(f"Found {len(cams)} camera(s)" + (": " + ", ".join(c.label for c in cams) if cams else ""))
        current = self.cam_combo.findData(self.source)
        self.cam_combo.setCurrentIndex(max(0, current))

    def refresh_ports(self) -> None:
        self.port_combo.clear()
        self.port_combo.addItem("Simulator car", "sim")
        self.port_combo.addItem("Vision only (no robot)", "none")
        for dev, desc in list_serial_ports():
            self.port_combo.addItem(f"🔌 {desc}", dev)
        current = "sim" if isinstance(self.link, SimLink) else getattr(self.link, "port", "none") or "none"
        self.port_combo.setCurrentIndex(max(0, self.port_combo.findData(current)))

    def open_camera(self, src) -> None:
        if self.camera:
            self.camera.stop()
            self.camera = None
        if src == "sim":
            self.source = "sim"
            self._set_link("sim")
            self.log("Using the simulator camera")
            return
        if cameras.ACCESS_ERROR and isinstance(src, int):
            self.log(cameras.ACCESS_ERROR)
            return
        self.camera = CameraSource(src, self.cfg.vision.frame_width, self.cfg.vision.frame_height)
        self.camera.start()
        self.source = src
        self.engine.localizer.reset()
        self.log(f"Opened camera {src}")
        if isinstance(self.link, SimLink):
            # Real camera: connect the gateway straight away if it's plugged in
            port = find_gateway_port() or "none"
            self._set_link(port)
            if port != "none":
                self.log(f"Connected to the gateway on {port}")

    def _set_link(self, which) -> None:
        if not isinstance(self.link, SimLink):
            self.link.close()
        if which == "sim":
            self.link = SimLink(self.world.car)
        elif which == "none":
            from markerpilot.comm.links import Link
            self.link = Link()
            self.link.send = lambda l, r: None
        else:
            link = SerialGatewayLink(which, self.cfg.link.baudrate)
            if link.connect():
                self.cfg.link.serial_port = which
                link.set_guard(self.cfg.link.guard_cm)
            self.link = link
        self.refresh_ports()

    # -------------------------------------------------------------- events
    def on_camera_chosen(self, index: int) -> None:
        data = self.cam_combo.itemData(index)
        if data is None:
            return
        if data == "url":
            url, ok = QInputDialog.getText(self, "Network camera",
                                           "Stream URL (e.g. http://192.168.1.5:8080/video from an IP-camera phone app):")
            if ok and url.strip():
                self.cam_combo.insertItem(self.cam_combo.count() - 1, f"🌐 {url.strip()}", url.strip())
                self.cam_combo.setCurrentIndex(self.cam_combo.count() - 2)
                self.open_camera(url.strip())
            return
        self.open_camera(data)

    def on_port_chosen(self, index: int) -> None:
        data = self.port_combo.itemData(index)
        if data == "sim" and self.source != "sim":
            self.log("The simulator car only works with the simulator camera")
            self.cam_combo.setCurrentIndex(0)
            self.open_camera("sim")
            return
        if data not in ("sim", "none") and self.source == "sim":
            self.log("Pick your real camera too - the simulator camera cannot see the real car")
        self._set_link(data)

    def on_video_click(self, x: float, y: float, button, mods) -> None:
        if button == Qt.MouseButton.RightButton:
            self.engine.clear_path()
            return
        ctrl = mods & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier)
        if ctrl and self.source == "sim":
            self.world.set_goal_px(x, y)
            self.engine.clear_path()
            return
        append = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        self.engine.add_waypoint(x, y, append)

    def on_estop(self, on: bool) -> None:
        self.engine.set_estop(on)
        self.link.send(0, 0)
        self.log("EMERGENCY STOP" if on else "Emergency stop released")

    def on_flip(self) -> None:
        v = self.cfg.vision
        v.heading_offset_deg = (v.heading_offset_deg + 180.0) % 360.0
        self.engine.localizer.reset()
        self.log(f"Marker heading offset is now {v.heading_offset_deg:.0f}°")

    def on_mode(self, _i: int) -> None:
        self.cfg.control.mode = self.mode_combo.currentData()
        self.engine.clear_path() if False else self.engine._new_target()
        self.log(f"Brain: {self.mode_combo.currentText()}")

    def on_speed(self, v: int) -> None:
        self.cfg.control.speed = v / 100.0
        self.speed_lbl.setText(f"{v}%")

    def on_train(self) -> None:
        if self._train_thread and self._train_thread.is_alive():
            return
        self.train_btn.setEnabled(False)
        self.train_btn.setText("Training…")

        def worker():
            from markerpilot.sim.env import evaluate, train
            agent = QAgent()
            agent.q = self.engine.agent.q.copy()
            agent, curve = train(3000, seed=int(time.time()) % 10000, agent=agent, check_every=500,
                                 progress=lambda i, s, b, e: self._train_msgs.put(f"RL training {i} episodes: score {s:.3f} (best {b:.3f})"))
            stats = evaluate("rl", 200, agent=agent)
            agent.save(meta={"success_rate": stats["success_rate"], "mean_time_s": stats["mean_time_s"]})
            self.engine.agent.q = agent.q
            self._train_msgs.put(f"RL training done: success {stats['success_rate'] * 100:.1f}%, "
                                 f"mean {stats['mean_time_s']:.2f}s - saved and loaded")
            self._train_msgs.put("__done__")
        self._train_thread = threading.Thread(target=worker, daemon=True)
        self._train_thread.start()

    def keyPressEvent(self, e):
        if not e.isAutoRepeat() and e.key() in (Qt.Key.Key_W, Qt.Key.Key_A, Qt.Key.Key_S, Qt.Key.Key_D):
            self._keys.add(e.key())
            self._update_manual()
        super().keyPressEvent(e)

    def keyReleaseEvent(self, e):
        if not e.isAutoRepeat() and e.key() in self._keys:
            self._keys.discard(e.key())
            self._update_manual()
        super().keyReleaseEvent(e)

    def _update_manual(self) -> None:
        if not self._keys:
            self.engine.manual = None
            return
        v = (Qt.Key.Key_W in self._keys) - (Qt.Key.Key_S in self._keys)
        w = (Qt.Key.Key_D in self._keys) - (Qt.Key.Key_A in self._keys)
        self.engine.manual = (0.8 * v, 0.7 * w)

    # -------------------------------------------------------------- main loop
    def tick(self) -> None:
        now = time.monotonic()
        dt = min(0.1, now - self._t_prev)
        self._t_prev = now

        while self._cams_found is not None and not self._cams_found.empty():
            self._add_camera(self._cams_found.get())
        if self._cams_result is not None:
            cams, self._cams_result = self._cams_result, None
            self._fill_cameras(cams)
        while not self._train_msgs.empty():
            msg = self._train_msgs.get()
            if msg == "__done__":
                self.train_btn.setEnabled(True)
                self.train_btn.setText("Train RL in simulator (≈2 min)")
            else:
                self.log(msg)
        while not self.link.messages.empty():
            self.log(self.link.messages.get())
        for msg in self.engine.events:
            self.log(msg)
        self.engine.events.clear()

        if self.source == "sim":
            self.world.step(dt)
            frame = self.world.frame()
        else:
            frame, _ = self.camera.read() if self.camera else (None, 0)
            if frame is not None and self.cfg.vision.mirror_view:
                frame = cv2.flip(frame, 1)

        if isinstance(self.link, SimLink):
            self.link.poll()
        tele = self.link.fresh_telemetry(self.cfg.link.timeout_s)
        sonar = tele.sonar if tele else None

        out = self.engine.process(frame, now, sonar)
        self._out = out
        if isinstance(self.link, SimLink) or now - self._last_send >= 1.0 / self.cfg.link.send_hz:
            self._last_send = now
            self.link.send(*out.pwm)

        if frame is None:
            canvas = np.full((self.cfg.vision.frame_height, self.cfg.vision.frame_width, 3), 12, np.uint8)
            msg = self.camera.error if self.camera and self.camera.error else "Waiting for camera…"
            overlays.status_banner(canvas, msg, warn=True)
            self.video.show_frame(canvas)
        else:
            img = frame.copy()
            overlays.draw(img, out, self.engine.waypoints, self.engine.trail, self.cfg.vision.car_marker_id,
                          self.engine.localizer.px_per_cm or 6.0, sonar, self.cfg.obstacle.warn_cm, self.cfg.obstacle.stop_cm)
            overlays.status_banner(img, out.status.upper(), warn=self.engine.estop or "lost" in out.status)
            self.video.show_frame(img)

        self._fps_n += 1
        if now - self._fps_t >= 1.0:
            self._fps = self._fps_n / (now - self._fps_t)
            self._fps_n, self._fps_t = 0, now
        if now - self._last_panel > 0.1:
            self._last_panel = now
            self.update_panels(out, tele)

    def update_panels(self, out, tele) -> None:
        ppc = self.engine.localizer.px_per_cm or 6.0
        p = out.pose
        L = self.t_labels
        if p is not None:
            L["pose"].setText(f"x {p.x / ppc:6.1f} cm   y {p.y / ppc:6.1f} cm")
            L["heading"].setText(f"{math.degrees(p.theta):6.1f}°   turning {math.degrees(p.omega):5.0f}°/s")
            L["speed"].setText(f"{abs(p.v) / ppc:5.1f} cm/s")
        else:
            for k in ("pose", "heading", "speed"):
                L[k].setText("car marker not visible")
        L["target"].setText(f"{out.dist_cm:5.1f} cm, {math.degrees(out.heading_err):5.0f}°" if out.target else "no target")
        L["status"].setText(out.status)
        cam_fps = self.camera.fps if self.camera else self._fps
        L["fps"].setText(f"{cam_fps:4.0f} fps / {self._fps:4.0f} fps")
        radio = self.link.radio_summary()
        if tele is not None and tele.battery_v > 0:
            radio += f" · battery {tele.battery_v:.1f} V"
        if tele is not None and tele.guard_holding:
            radio += " · GUARD STOP"
        if tele is not None and tele.sonar_faults:
            radio += " · sonar fault: " + ", ".join(tele.sonar_faults)
        L["radio"].setText(radio)

        for key, val in (("pwm_l", out.pwm[0]), ("pwm_r", out.pwm[1])):
            b, lbl = self.bars[key]
            b.setValue(int(abs(val) / 255 * 100))
            lbl.setText(f"{val:+d}")
        for key, i in (("s_l", 0), ("s_f", 1), ("s_r", 2)):
            b, lbl = self.bars[key]
            if tele is None:
                b.setValue(0)
                lbl.setText("—")
                continue
            d = tele.sonar[i]
            b.setValue(int(min(d, 150) / 150 * 100))
            color = "#ef4444" if d < self.cfg.obstacle.stop_cm else "#f59e0b" if d < self.cfg.obstacle.warn_cm else "#22c55e"
            b.setStyleSheet(f"QProgressBar::chunk {{ background: {color}; border-radius: 4px; }}")
            lbl.setText(f"{d:4.0f} cm")

        if isinstance(self.link, SimLink):
            text, color = "SIMULATOR", "#6366f1"
        elif isinstance(self.link, SerialGatewayLink):
            ok = self.link.connected(self.cfg.link.timeout_s)
            text, color = ("CAR LINKED", "#16a34a") if ok else ("NO CAR SIGNAL", "#dc2626")
        else:
            text, color = "VISION ONLY", "#475569"
        self.link_pill.setText(text)
        self.link_pill.setStyleSheet(f"background:{color};")

        self.inv_t_cb.blockSignals(True)
        self.inv_t_cb.setChecked(self.cfg.control.invert_throttle)
        self.inv_t_cb.blockSignals(False)
        self.inv_s_cb.blockSignals(True)
        self.inv_s_cb.setChecked(self.cfg.control.invert_steering)
        self.inv_s_cb.blockSignals(False)

        rl = self.engine.rl
        avg = sum(rl.last_rewards) / len(rl.last_rewards) if rl.last_rewards else 0.0
        rate = rl.successes / rl.episodes * 100 if rl.episodes else 0.0
        self.rl_lbl.setText(f"Policy: {self.engine.policy_source.split('/')[-1]}\n"
                            f"Episodes {rl.episodes}  ·  success {rate:.0f}%  ·  avg reward {avg:.1f}\n"
                            f"Action now: {out.action or '—'}  ·  updates {self.engine.agent.updates}")

    def closeEvent(self, e):
        self.link.send(0, 0)
        self.link.close()
        if self.camera:
            self.camera.stop()
        self.cfg.save()
        super().closeEvent(e)


def run_gui(args=None) -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyleSheet(STYLE)
    cfg = AppConfig.load()
    if args is not None and getattr(args, "sim", False):
        cfg.last_camera = "sim"
    win = MainWindow(cfg, args)
    win.show()
    return app.exec()
