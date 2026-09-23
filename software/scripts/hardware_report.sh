#!/usr/bin/env bash
# Read-only identification. No GPIO writes, service installation, or radio changes.
set -euo pipefail
uname -srm
if [[ -r /proc/device-tree/model ]]; then
  tr -d '\0' < /proc/device-tree/model
  echo
else
  echo "No Raspberry Pi device-tree model available on this computer."
fi
if [[ -r /etc/os-release ]]; then
  cat /etc/os-release
fi
python3 - <<'PY'
import importlib.util
import platform
print('Python:', platform.python_version(), 'Architecture:', platform.machine())
for name in ('picamera2', 'PIL', 'pygame', 'spidev', 'gpiozero'):
    print(name + ':', 'installed' if importlib.util.find_spec(name) else 'not installed')
PY
if command -v rpicam-hello >/dev/null 2>&1; then
  rpicam-hello --list-cameras
elif command -v libcamera-hello >/dev/null 2>&1; then
  libcamera-hello --list-cameras
else
  echo "Camera identification tools not installed; exact Pi camera model remains unknown."
fi
echo "The LCD controller, SPI mode, GPIO pinout and button wiring still need supplier documentation."
