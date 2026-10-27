# Install MarkerPilot

MarkerPilot is the robot-navigation app from the robotics project. Install it with one command in a terminal. You don't need Python.

## Linux and macOS

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
