#!/usr/bin/env python3
"""Build a double-click installer for MarkerPilot on Debian / Ubuntu / Mint.

    python3 tools/build_linux_deb.py          -> dist/markerpilot_<version>_all.deb

Runs on any OS (no dpkg needed): a .deb is just an `ar` archive holding two
tarballs, which Python's standard library can write.

What the package does on the Linux laptop:
  /opt/markerpilot/app       the markerpilot Python package (pure Python)
  /opt/markerpilot/venv      private Python environment, created by postinst
                             with numpy, OpenCV, PyQt6 and pyserial from pip
  /usr/bin/markerpilot       command-line launcher
  app menu entry + icon      "MarkerPilot" (right-click: "Simulator")
  udev rule                  lets every user open the ESP32-C3 gateway and
                             USB-serial cables, no dialout group / re-login
Installing needs internet once (pip downloads ~120 MB of wheels). If that
fails, the launcher builds the environment in ~/.markerpilot on first start.
"""

import gzip
import io
import os
import re
import sys
import tarfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROBOTICS = os.path.join(ROOT, "robotics")
PKG_SRC = os.path.join(ROBOTICS, "markerpilot")
NOW = int(time.time())


def version() -> str:
    text = open(os.path.join(PKG_SRC, "__init__.py"), encoding="utf-8").read()
    return re.search(r'__version__\s*=\s*"([^"]+)"', text).group(1)


VERSION = version()
REQUIREMENTS = open(os.path.join(ROBOTICS, "requirements.txt"), encoding="utf-8").read()

# Runtime libraries the PyQt6 wheels need for their X11 / Wayland plugin
DEPENDS = ", ".join([
    "python3 (>= 3.9)", "python3-venv", "libgl1", "libegl1", "libxkbcommon-x11-0", "libxcb-cursor0",
    "libxcb-icccm4", "libxcb-keysyms1", "libxcb-image0", "libxcb-render-util0", "libxcb-xinerama0",
    "libxcb-shape0", "libdbus-1-3", "libfontconfig1",
])

CONTROL = f"""Package: markerpilot
Version: {VERSION}
Section: science
Priority: optional
Architecture: all
Maintainer: Aadil S P <aadil2001aadil@gmail.com>
Depends: {DEPENDS}
Recommends: libnotify-bin
Installed-Size: 2000
Homepage: https://github.com/aadil-sp/shakthikulangara-project-2
Description: Overhead-camera ArUco navigation for a robot car
 MarkerPilot drives a small robot car to any point clicked on the camera
 picture, or to a printed goal marker, using a ceiling camera and an
 ESP32 car linked over ESP-NOW. Includes a simulator, a classic controller
 and a reinforcement-learning agent.
 .
 Installing downloads numpy, OpenCV, PyQt6 and pyserial with pip into a
 private environment in /opt/markerpilot, so it needs internet once.
"""

POSTINST = """#!/bin/sh
set -e
APP=/opt/markerpilot
if [ "$1" = "configure" ]; then
    echo "MarkerPilot: setting up its Python environment (downloads ~120 MB, needs internet)..."
    rm -rf "$APP/venv"
    if python3 -m venv "$APP/venv" \\
       && "$APP/venv/bin/python" -m pip install --quiet --upgrade pip \\
       && "$APP/venv/bin/python" -m pip install --quiet --no-cache-dir -r "$APP/requirements.txt"; then
        "$APP/venv/bin/python" -m compileall -q "$APP/app" >/dev/null 2>&1 || true
        echo "MarkerPilot: ready. Open it from the app menu, or run 'markerpilot'."
    else
        rm -rf "$APP/venv"
        echo "MarkerPilot: could not download its libraries now (offline?)."
        echo "It will set itself up the first time you open it."
    fi
    udevadm control --reload-rules >/dev/null 2>&1 || true
    udevadm trigger --subsystem-match=tty >/dev/null 2>&1 || true
    update-desktop-database -q /usr/share/applications >/dev/null 2>&1 || true
    gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor >/dev/null 2>&1 || true
fi
exit 0
"""

PRERM = """#!/bin/sh
set -e
if [ "$1" = "remove" ] || [ "$1" = "purge" ]; then
    rm -rf /opt/markerpilot/venv
    find /opt/markerpilot/app -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
fi
exit 0
"""

POSTRM = """#!/bin/sh
set -e
udevadm control --reload-rules >/dev/null 2>&1 || true
update-desktop-database -q /usr/share/applications >/dev/null 2>&1 || true
exit 0
"""

# Launcher: uses the shared environment, or builds a private one in the
# user's home on first start when the install-time download failed.
LAUNCHER = """#!/bin/sh
APP=/opt/markerpilot
PY="$APP/venv/bin/python"
if [ ! -x "$PY" ]; then
    USERVENV="$HOME/.markerpilot/venv"
    PY="$USERVENV/bin/python"
    if [ ! -x "$PY" ] || ! "$PY" -c "import cv2, PyQt6, serial" >/dev/null 2>&1; then
        command -v notify-send >/dev/null 2>&1 && \\
            notify-send -i markerpilot "MarkerPilot" "First start: downloading its libraries (needs internet, a few minutes)..."
        mkdir -p "$HOME/.markerpilot"
        if ! { python3 -m venv "$USERVENV" \\
               && "$PY" -m pip install --quiet --upgrade pip \\
               && "$PY" -m pip install --quiet -r "$APP/requirements.txt"; } >"$HOME/.markerpilot/setup.log" 2>&1; then
            command -v notify-send >/dev/null 2>&1 && \\
                notify-send -i markerpilot "MarkerPilot" "Setup failed. Connect to the internet and try again. Details: ~/.markerpilot/setup.log"
            echo "MarkerPilot setup failed, see ~/.markerpilot/setup.log" >&2
            exit 1
        fi
    fi
fi
export PYTHONPATH="$APP/app${PYTHONPATH:+:$PYTHONPATH}"
exec "$PY" -m markerpilot "$@"
"""

DESKTOP = f"""[Desktop Entry]
Type=Application
Name=MarkerPilot
GenericName=Robot car navigation
Comment=Drive the robot car to points clicked on the overhead camera picture
Exec=markerpilot
Icon=markerpilot
Terminal=false
Categories=Education;Science;Engineering;
Keywords=robot;aruco;camera;esp32;rl;
StartupWMClass=MarkerPilot
Actions=Simulator;

[Desktop Action Simulator]
Name=Simulator (no robot needed)
Exec=markerpilot --sim
"""

# ESP32-C3 gateway (Espressif native USB) and the usual USB-serial chips on
# ESP32 boards. ModemManager must leave the gateway alone, or it grabs the
# port for a few seconds after every plug-in.
UDEV = """# MarkerPilot: let every user open the robot gateway and ESP32 USB cables
SUBSYSTEM=="tty", ATTRS{idVendor}=="303a", MODE="0666", ENV{ID_MM_DEVICE_IGNORE}="1"
SUBSYSTEM=="tty", ATTRS{idVendor}=="10c4", MODE="0666", ENV{ID_MM_DEVICE_IGNORE}="1"
SUBSYSTEM=="tty", ATTRS{idVendor}=="1a86", MODE="0666", ENV{ID_MM_DEVICE_IGNORE}="1"
SUBSYSTEM=="tty", ATTRS{idVendor}=="0403", MODE="0666"
"""


def make_icon(size: int = 256) -> bytes:
    """A simple app icon: an ArUco-style marker on a blue rounded square."""
    import numpy as np
    import cv2
    img = np.zeros((size, size, 4), np.uint8)
    r = size // 6
    color = (235, 120, 37, 255)   # BGR blue
    cv2.rectangle(img, (r, 0), (size - r, size), color, -1)
    cv2.rectangle(img, (0, r), (size, size - r), color, -1)
    for cx, cy in ((r, r), (size - r, r), (r, size - r), (size - r, size - r)):
        cv2.circle(img, (cx, cy), r, color, -1, cv2.LINE_AA)
    m = size * 5 // 8
    x0 = (size - m) // 2
    cv2.rectangle(img, (x0 - 8, x0 - 8), (x0 + m + 8, x0 + m + 8), (255, 255, 255, 255), -1)
    cell = m // 6
    pattern = ["111111", "100101", "110001", "101101", "100011", "111111"]   # black border + bits
    for row, bits in enumerate(pattern):
        for col, b in enumerate(bits):
            if b == "1":
                cv2.rectangle(img, (x0 + col * cell, x0 + row * cell),
                              (x0 + (col + 1) * cell - 1, x0 + (row + 1) * cell - 1), (20, 20, 20, 255), -1)
    ok, png = cv2.imencode(".png", img)
    assert ok
    return png.tobytes()


def add_bytes(tar: tarfile.TarFile, path: str, data: bytes, mode: int = 0o644) -> None:
    info = tarfile.TarInfo(path)
    info.size, info.mode, info.mtime = len(data), mode, NOW
    info.uid = info.gid = 0
    info.uname = info.gname = "root"
    tar.addfile(info, io.BytesIO(data))


def add_dir(tar: tarfile.TarFile, path: str) -> None:
    info = tarfile.TarInfo(path)
    info.type, info.mode, info.mtime = tarfile.DIRTYPE, 0o755, NOW
    info.uid = info.gid = 0
    info.uname = info.gname = "root"
    tar.addfile(info)


def tar_gz(build) -> bytes:
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.GNU_FORMAT) as tar:
        build(tar)
    return gzip.compress(raw.getvalue(), mtime=NOW)


def package_files():
    """(path in package, bytes) for every file of the markerpilot package."""
    for dirpath, dirnames, filenames in os.walk(PKG_SRC):
        dirnames[:] = sorted(d for d in dirnames if d != "__pycache__")
        for name in sorted(filenames):
            if name.endswith((".pyc", ".pyo")) or name == ".DS_Store":
                continue
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, ROBOTICS).replace(os.sep, "/")
            yield rel, open(full, "rb").read()


def data_tar(tar: tarfile.TarFile) -> None:
    made = set()

    def ensure_dirs(path: str) -> None:
        parts = path.strip("./").split("/")[:-1]
        for i in range(1, len(parts) + 1):
            d = "./" + "/".join(parts[:i])
            if d not in made:
                made.add(d)
                add_dir(tar, d)

    def put(path: str, data: bytes, mode: int = 0o644) -> None:
        ensure_dirs(path)
        add_bytes(tar, path, data, mode)

    for rel, data in package_files():
        put(f"./opt/markerpilot/app/{rel}", data)
    put("./opt/markerpilot/requirements.txt", REQUIREMENTS.encode())
    put("./usr/bin/markerpilot", LAUNCHER.encode(), 0o755)
    put("./usr/share/applications/markerpilot.desktop", DESKTOP.encode())
    put("./usr/share/icons/hicolor/256x256/apps/markerpilot.png", make_icon(256))
    put("./usr/lib/udev/rules.d/70-markerpilot.rules", UDEV.encode())
    put("./usr/share/doc/markerpilot/copyright",
        open(os.path.join(ROOT, "LICENSE"), "rb").read() if os.path.exists(os.path.join(ROOT, "LICENSE")) else b"MIT\n")


def control_tar(tar: tarfile.TarFile) -> None:
    add_bytes(tar, "./control", CONTROL.encode())
    add_bytes(tar, "./postinst", POSTINST.encode(), 0o755)
    add_bytes(tar, "./prerm", PRERM.encode(), 0o755)
    add_bytes(tar, "./postrm", POSTRM.encode(), 0o755)


def ar_member(name: str, data: bytes) -> bytes:
    header = f"{name:<16}{NOW:<12}{0:<6}{0:<6}{'100644':<8}{len(data):<10}`\n".encode()
    assert len(header) == 60
    return header + data + (b"\n" if len(data) % 2 else b"")


def main() -> int:
    out_dir = os.path.join(ROOT, "dist")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, f"markerpilot_{VERSION}_all.deb")
    deb = b"!<arch>\n" + ar_member("debian-binary", b"2.0\n") + \
        ar_member("control.tar.gz", tar_gz(control_tar)) + ar_member("data.tar.gz", tar_gz(data_tar))
    with open(out, "wb") as f:
        f.write(deb)
    print(f"Built {os.path.relpath(out, ROOT)} ({len(deb) / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
