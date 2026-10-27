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

Before upload, each app file in this release was built by GitHub Actions and passed the end-to-end simulator self-test on its own operating system.

### What's included

- `markerpilot-*`: the stand-alone app (Windows, Linux, macOS Apple Silicon)
- `firmware-all-boards.zip`: Arduino sketches for every board:
  - HazardGuard C3 (electronics)
  - Multi-Hazard Monitor (IoT)
  - MarkerPilot car (robotics)
  - MarkerPilot USB gateway (robotics)
- the three project report PDFs
- `install.sh` / `install.ps1`: the installers
