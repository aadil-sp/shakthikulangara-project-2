#!/usr/bin/env bash
# MarkerPilot installer for Linux and macOS.
#   curl -fsSL https://raw.githubusercontent.com/aadil-sp/shakthikulangara-project-2/main/install/install.sh | bash
# Installs the ready-made app from the latest release when one exists for this
# computer, otherwise installs from source with pip (Python 3.9+ needed).
set -euo pipefail

REPO="aadil-sp/shakthikulangara-project-2"
BASE="https://github.com/${REPO}/releases/latest/download"
SOURCE_ZIP="https://github.com/${REPO}/archive/refs/heads/main.zip#subdirectory=robotics"
NAME="markerpilot"

say()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!!\033[0m %s\n' "$*"; }

OS="$(uname -s)"
ARCH="$(uname -m)"
case "${OS}-${ARCH}" in
  Linux-x86_64) ASSET="markerpilot-linux-x86_64" ;;
  Darwin-arm64) ASSET="markerpilot-macos-arm64" ;;
  *)            ASSET="" ;;
esac

SUDO=""
if [ "$(id -u)" -ne 0 ] && command -v sudo >/dev/null 2>&1; then SUDO="sudo"; fi

linux_setup() {
  [ "${OS}" = "Linux" ] || return 0
  if command -v apt-get >/dev/null 2>&1; then
    say "Installing Qt/X11 runtime libraries (needs sudo)"
    ${SUDO} apt-get install -y -qq libxcb-cursor0 libxkbcommon-x11-0 libxcb-icccm4 libxcb-keysyms1 \
      libxcb-image0 libxcb-render-util0 libxcb-xinerama0 libxcb-shape0 libegl1 libgl1 >/dev/null 2>&1 \
      || warn "Could not install Qt libraries automatically; the app may ask for them"
  fi
  if getent group dialout >/dev/null 2>&1 && ! id -nG "${USER:-$(id -un)}" | grep -qw dialout; then
    say "Adding you to the 'dialout' group so the app can use the USB gateway (log out and in afterwards)"
    ${SUDO} usermod -aG dialout "${USER:-$(id -un)}" || true
  fi
}

finish() {
  echo
  say "MarkerPilot is installed."
  echo "  markerpilot            open the app"
  echo "  markerpilot --sim      try it with the simulator"
  echo "  markerpilot cameras    list cameras"
  echo "  markerpilot markers    make printable markers"
}

install_with_pip() {
  say "Installing MarkerPilot from source with pip"
  if ! command -v python3 >/dev/null 2>&1; then
    warn "Python 3.9+ is needed. Install it (e.g. 'sudo apt install python3-pip python3-venv' or from python.org) and run this again."
    exit 1
  fi
  if command -v pipx >/dev/null 2>&1; then
    pipx install --force "${SOURCE_ZIP}"
  elif python3 -m pip install --user --upgrade "${SOURCE_ZIP}" 2>/dev/null; then
    :
  else
    # Debian/Ubuntu 23+ block system pip: use a private virtual environment
    VENV="${HOME}/.markerpilot/venv"
    python3 -m venv "${VENV}"
    "${VENV}/bin/pip" install --upgrade pip >/dev/null
    "${VENV}/bin/pip" install --upgrade "${SOURCE_ZIP}"
    mkdir -p "${HOME}/.local/bin"
    ln -sf "${VENV}/bin/markerpilot" "${HOME}/.local/bin/markerpilot"
    case ":${PATH}:" in *":${HOME}/.local/bin:"*) ;; *) warn "Add ~/.local/bin to your PATH: export PATH=\"\$HOME/.local/bin:\$PATH\"" ;; esac
  fi
  finish
  exit 0
}

linux_setup
[ -z "${ASSET}" ] && install_with_pip

TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT
say "Downloading ${ASSET} (latest release)"
if ! curl -fL --progress-bar "${BASE}/${ASSET}" -o "${TMP}/${NAME}"; then
  warn "No ready-made app for ${OS}/${ARCH} in the latest release yet"
  install_with_pip
fi
chmod +x "${TMP}/${NAME}"

if [ -w /usr/local/bin ] || [ -n "${SUDO}" ]; then DEST="/usr/local/bin"; else DEST="${HOME}/.local/bin"; mkdir -p "${DEST}"; fi
say "Installing to ${DEST}/${NAME}"
if [ "${DEST}" = "/usr/local/bin" ] && [ ! -w "${DEST}" ]; then
  ${SUDO} install -m 0755 "${TMP}/${NAME}" "${DEST}/${NAME}"
else
  install -m 0755 "${TMP}/${NAME}" "${DEST}/${NAME}"
fi
[ "${OS}" = "Darwin" ] && xattr -d com.apple.quarantine "${DEST}/${NAME}" 2>/dev/null || true

case ":${PATH}:" in
  *":${DEST}:"*) ;;
  *) warn "${DEST} is not on your PATH. Add: export PATH=\"${DEST}:\$PATH\"" ;;
esac
say "$("${DEST}/${NAME}" --version 2>/dev/null || echo markerpilot)"
finish
