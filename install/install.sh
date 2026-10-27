#!/usr/bin/env bash
# MarkerPilot installer for Linux and macOS.
#   curl -fsSL https://raw.githubusercontent.com/aadil-sp/shakthikulangara-project-2/main/install/install.sh | bash
set -euo pipefail

REPO="aadil-sp/shakthikulangara-project-2"
BASE="https://github.com/${REPO}/releases/latest/download"
NAME="markerpilot"

say()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!!\033[0m %s\n' "$*"; }

OS="$(uname -s)"
ARCH="$(uname -m)"
case "${OS}-${ARCH}" in
  Linux-x86_64)              ASSET="markerpilot-linux-x86_64" ;;
  Darwin-arm64)              ASSET="markerpilot-macos-arm64" ;;
  *)                         ASSET="" ;;
esac

SUDO=""
if [ "$(id -u)" -ne 0 ] && command -v sudo >/dev/null 2>&1; then SUDO="sudo"; fi

install_with_pip() {
  say "No ready-made app for ${OS}/${ARCH} - installing from source with pip"
  if ! command -v python3 >/dev/null 2>&1; then warn "Please install Python 3.9+ first"; exit 1; fi
  if command -v pipx >/dev/null 2>&1; then
    pipx install --force "git+https://github.com/${REPO}.git#subdirectory=robotics"
  else
    python3 -m pip install --user --upgrade "git+https://github.com/${REPO}.git#subdirectory=robotics"
  fi
  say "Done. Run: markerpilot"
  exit 0
}

[ -z "${ASSET}" ] && install_with_pip

if [ -w /usr/local/bin ] || [ -n "${SUDO}" ]; then
  DEST="/usr/local/bin"
else
  DEST="${HOME}/.local/bin"
  mkdir -p "${DEST}"
fi

TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT
say "Downloading ${ASSET} (latest release)"
curl -fL --progress-bar "${BASE}/${ASSET}" -o "${TMP}/${NAME}"
chmod +x "${TMP}/${NAME}"

say "Installing to ${DEST}/${NAME}"
if [ "${DEST}" = "/usr/local/bin" ] && [ ! -w "${DEST}" ]; then
  ${SUDO} install -m 0755 "${TMP}/${NAME}" "${DEST}/${NAME}"
else
  install -m 0755 "${TMP}/${NAME}" "${DEST}/${NAME}"
fi

if [ "${OS}" = "Darwin" ]; then
  xattr -d com.apple.quarantine "${DEST}/${NAME}" 2>/dev/null || true
fi

if [ "${OS}" = "Linux" ]; then
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
fi

case ":${PATH}:" in
  *":${DEST}:"*) ;;
  *) warn "${DEST} is not on your PATH. Add this line to ~/.bashrc or ~/.zshrc:  export PATH=\"${DEST}:\$PATH\"" ;;
esac

say "Installed: $("${DEST}/${NAME}" --version 2>/dev/null || echo markerpilot)"
echo
echo "  markerpilot            open the app"
echo "  markerpilot --sim      try it with the simulator"
echo "  markerpilot cameras    list cameras"
echo "  markerpilot markers    make printable markers"
