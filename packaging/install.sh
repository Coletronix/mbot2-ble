#!/bin/sh
# Installs the mbot2 command-line tool on Linux or macOS. Run:
#
#   curl -LsSf https://github.com/Coletronix/mbot2-ble/releases/latest/download/install.sh | sh
#
# It downloads one file, the standalone `mbot2` program from the latest release, to
# ~/.local/bin (or $MBOT2_INSTALL_DIR). Nothing else is installed or changed. To uninstall,
# delete ~/.local/bin/mbot2. Running it again updates to the newest version.
set -eu

REPO="Coletronix/mbot2-ble"
DIR="${MBOT2_INSTALL_DIR:-$HOME/.local/bin}"

fail() {
    echo "error: $*" >&2
    exit 1
}

case "$(uname -s)" in
    Linux) os=linux ;;
    Darwin) os=macos ;;
    *) fail "this installer is for Linux and macOS. On Windows, see https://github.com/$REPO#install" ;;
esac
case "$(uname -m)" in
    x86_64 | amd64) arch=x64 ;;
    aarch64 | arm64) arch=arm64 ;;
    *) fail "no ready-made mbot2 for $(uname -m) processors. Install from source instead: https://github.com/$REPO#from-source" ;;
esac
if [ "$os" = macos ] && [ "$arch" = x64 ]; then
    fail "no ready-made mbot2 for Intel Macs. Install from source instead: https://github.com/$REPO#from-source"
fi

url="https://github.com/$REPO/releases/latest/download/mbot2-$os-$arch"
mkdir -p "$DIR"
tmp="$DIR/.mbot2-download.$$"
trap 'rm -f "$tmp"' EXIT

echo "Downloading $url"
if command -v curl > /dev/null 2>&1; then
    curl -fL --progress-bar -o "$tmp" "$url" || fail "download failed"
elif command -v wget > /dev/null 2>&1; then
    wget -q --show-progress -O "$tmp" "$url" || fail "download failed"
else
    fail "need curl or wget to download"
fi
chmod +x "$tmp"
mv -f "$tmp" "$DIR/mbot2"

echo "Installed $("$DIR/mbot2" --version) to $DIR/mbot2"

case ":$PATH:" in
    *":$DIR:"*)
        echo "Try it:  mbot2 scan"
        ;;
    *)
        echo
        echo "$DIR isn't on your PATH yet, so for now run it as:  $DIR/mbot2 scan"
        echo "To type just 'mbot2', add this line to your shell's startup file (~/.bashrc, ~/.zshrc, ...)"
        echo "and open a new terminal:"
        echo
        echo "    export PATH=\"$DIR:\$PATH\""
        ;;
esac
