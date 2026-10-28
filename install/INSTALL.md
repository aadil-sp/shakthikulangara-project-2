# Install MarkerPilot

MarkerPilot is the robot-navigation app from the robotics project. Install it with one command in a terminal. You don't need Python.

## Linux laptop (Ubuntu, Debian, Mint): double-click installer

1. Copy **`markerpilot_2.0.0_all.deb`** to the laptop. Build it with `python3 tools/build_linux_deb.py`; it lands in `dist/`.
2. **Double-click it.** The software installer opens. Click **Install** and enter your password.
   - If double-click opens an archive viewer instead, right-click the file → **Open With → Software Install**, or run `sudo apt install ./markerpilot_2.0.0_all.deb`.
3. Keep the laptop **online** while it installs. It downloads OpenCV, PyQt6, numpy and pyserial once (about 120 MB, a few minutes).
4. Open **MarkerPilot** from the app menu. To start without the robot, right-click the icon and choose **Simulator**. Add it to the dock with right-click → **Add to Favourites**.

The package also lets every user open the ESP32-C3 gateway and USB cables, so there's no `dialout` group to join and no need to log out.

If the laptop was offline during install, MarkerPilot sets itself up the first time you open it. A notification says so, and that first start needs internet.

Uninstall from the software centre, or with `sudo apt remove markerpilot`.

## Linux and macOS (terminal)

```bash
curl -fsSL https://raw.githubusercontent.com/aadil-sp/shakthikulangara-project-2/main/install/install.sh | bash
```

The script:

- downloads the ready-made app for your computer from the latest release and installs it as `/usr/local/bin/markerpilot`, asking for your `sudo` password once
- installs from source with pip if there's no ready-made app for your computer
- on Linux, installs the small Qt display libraries and adds you to the `dialout` group so the app can use the USB gateway (log out and back in once)

## Windows (PowerShell)

```powershell
irm https://raw.githubusercontent.com/aadil-sp/shakthikulangara-project-2/main/install/install.ps1 | iex
```

This puts `markerpilot.exe` in `%LOCALAPPDATA%\MarkerPilot`, adds it to your PATH and creates a Start-menu shortcut. If the release has no Windows app yet, it installs MarkerPilot with pip instead, installing Python through winget first if you don't have it. Open a **new** terminal afterwards.

## Any computer with Python 3.9+ (pipx)

```bash
pipx install "https://github.com/aadil-sp/shakthikulangara-project-2/archive/refs/heads/main.zip#subdirectory=robotics"
```

Use this on Intel Macs, Raspberry Pi and ARM Linux, which have no ready-made app.

## Direct downloads

| Computer | File |
| :--- | :--- |
| macOS (Apple Silicon M1/M2/M3/M4) | [markerpilot-macos-arm64](https://github.com/aadil-sp/shakthikulangara-project-2/releases/latest/download/markerpilot-macos-arm64) |
| Windows / Linux | The installer commands above. Ready-made apps arrive once the [release pipeline](../ci/README.md) is enabled. |
| Firmware for all boards (zip) | [firmware-all-boards.zip](https://github.com/aadil-sp/shakthikulangara-project-2/releases/latest/download/firmware-all-boards.zip) |

On Linux and macOS, make a downloaded file runnable with `chmod +x markerpilot-*`.

## First run

```bash
markerpilot --sim        # try everything with the built-in simulator
markerpilot              # real camera + robot
markerpilot cameras      # list every camera the computer can see
markerpilot ports        # list serial ports (find the ESP32-C3 gateway)
markerpilot markers      # save printable ArUco markers (print at 100%)
markerpilot selftest     # headless end-to-end test
markerpilot train        # train the RL agent further in the simulator
```

macOS asks for camera permission the first time. Allow it for your Terminal app, then pick the camera again.

## Uninstall

- **Linux/macOS:** `sudo rm /usr/local/bin/markerpilot ~/.markerpilot -r`
- **Windows:** delete `%LOCALAPPDATA%\MarkerPilot` and the Start-menu shortcut.
