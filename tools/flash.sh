#!/usr/bin/env bash
# Compile and upload one of the project sketches.
#   tools/flash.sh electronics [port]
#   tools/flash.sh iot [port]
#   tools/flash.sh car [port]
#   tools/flash.sh gateway [port]
# Without a port it uses the first ESP32 it finds. Needs arduino-cli with the
# esp32 core (3.x) and the libraries "DHT sensor library" and "TM1637".
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLI="${ARDUINO_CLI:-$(command -v arduino-cli || echo "$HOME/.local/bin/arduino-cli")}"
C3="esp32:esp32:esp32c3:CDCOnBoot=cdc,FlashMode=dio"

case "${1:-}" in
  electronics) SKETCH="$ROOT/electronics/hazardguard_c3";            FQBN="$C3" ;;
  iot)         SKETCH="$ROOT/iot/multi_hazard_monitor";              FQBN="$C3" ;;
  car)         SKETCH="$ROOT/robotics/firmware/markerpilot_car";     FQBN="esp32:esp32:esp32" ;;
  gateway)     SKETCH="$ROOT/robotics/firmware/markerpilot_gateway"; FQBN="$C3" ;;
  *) echo "usage: $0 electronics|iot|car|gateway [port]"; exit 1 ;;
esac

PORT="${2:-}"
if [ -z "$PORT" ]; then
  PORT="$("$CLI" board list 2>/dev/null | awk '/usbmodem|usbserial|ttyUSB|ttyACM|wchusbserial|SLAB/ {print $1; exit}')"
fi
[ -z "$PORT" ] && { echo "No ESP32 found - plug it in or pass the port"; exit 1; }

echo "==> Compiling $(basename "$SKETCH") for $FQBN"
"$CLI" compile --fqbn "$FQBN" "$SKETCH"
echo "==> Uploading to $PORT"
"$CLI" upload -p "$PORT" --fqbn "$FQBN" "$SKETCH"
echo "==> Done. Serial monitor:  $CLI monitor -p $PORT -c baudrate=115200"
