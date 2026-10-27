## MarkerPilot 2.0: Shakthikulangara Project 2

**Install the robot-navigation app with one command:**

- **Linux / macOS:**
  ```bash
  curl -fsSL https://raw.githubusercontent.com/aadil-sp/shakthikulangara-project-2/main/install/install.sh | bash
  ```
- **Windows (PowerShell):**
  ```powershell
  irm https://raw.githubusercontent.com/aadil-sp/shakthikulangara-project-2/main/install/install.ps1 | iex
  ```

The installers use a ready-made app from this release when there is one for your computer. Otherwise they install MarkerPilot from source with pip, and on Windows they install Python first with winget if needed.

### What's included

- `markerpilot-macos-arm64`: stand-alone app for Apple Silicon Macs, built and self-tested on macOS
- `firmware-all-boards.zip`: Arduino sketches for every board:
  - HazardGuard C3 (electronics)
  - Marine Fish Quality Monitor (IoT, NodeMCU ESP8266)
  - MarkerPilot car (robotics)
  - MarkerPilot USB gateway (robotics)
- the three project report PDFs
- `install.sh` / `install.ps1`: the installers

Stand-alone Windows and Linux apps will be added by the release pipeline in `ci/release.yml` once it is enabled. Until then, the installers install from source on those systems.
