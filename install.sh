#!/usr/bin/env bash
set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'
CYAN='\033[0;36m'

echo "==================================="
echo "        NBTrackr installer"
echo "==================================="
echo

if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python -m venv venv
else
    echo "Virtual environment already exists."
fi

FULL_PATH="$(pwd)/venv/bin/python"

"$FULL_PATH" - <<'EOF'
try:
    import pip
except ImportError:
    print("WARNING: pip is not installed in this virtual environment.")
    print("Installation of NBTrackr dependencies may fail.")
    print("You can install pip manually by running:")
    print("  curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py")
    print("  python get-pip.py")
EOF

"$FULL_PATH" - <<'EOF'
import sys
RED='\033[1;31m'
NC='\033[0m'
try:
    import tkinter
except ImportError:
    print(f"{RED}ERROR: tkinter is not installed.{NC}")
    print("Install it via your distro package manager:")
    print("  Debian/Ubuntu: sudo apt install python3-tk")
    print("  Arch Linux:    sudo pacman -S tk")
    print("  Fedora:        sudo dnf install python3-tkinter")
    sys.exit(1)
EOF

echo "Installing required Python packages..."
"$FULL_PATH" -m pip install --upgrade pip
"$FULL_PATH" -m pip install -r requirements.txt

echo
echo -e "${GREEN}Installation complete!${NC}"
echo

INSTALL_DIR="$HOME/.local/bin"
LAUNCHER_TARGET="$(pwd)/nbtrackr"
LAUNCHER_LINK="$INSTALL_DIR/nbtrackr"

chmod +x "$LAUNCHER_TARGET"
mkdir -p "$INSTALL_DIR"

if [ -L "$LAUNCHER_LINK" ] || [ -e "$LAUNCHER_LINK" ]; then
    echo "Updating existing nbtrackr entry in $INSTALL_DIR..."
    ln -sf "$LAUNCHER_TARGET" "$LAUNCHER_LINK"
else
    ln -sf "$LAUNCHER_TARGET" "$LAUNCHER_LINK"
    echo -e "${GREEN}NBTrackr added to $INSTALL_DIR${NC}"
fi
case ":$PATH:" in
    *":$INSTALL_DIR:"*)
        ;;
    *)
        echo
        echo -e "${YELLOW}$INSTALL_DIR is not in your PATH.${NC}"
        echo "Add this line to your shell config (~/.bashrc, ~/.zshrc, etc.):"
        echo
        echo -e "  ${CYAN}export PATH=\"\$HOME/.local/bin:\$PATH\"${NC}"
        echo
        echo "Then restart your terminal."
        ;;
esac
echo

echo "To run NBTrackr:"
echo -e "  ${CYAN}nbtrackr${NC}"
echo
echo "To configure NBTrackr:"
echo -e "  ${CYAN}nbtrackr --settings${NC}"
echo
echo "To remove NBTrackr from your terminal, run:"
echo -e "  ${CYAN}./uninstall.sh${NC}"
