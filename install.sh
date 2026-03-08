#!/usr/bin/env bash
set -e

GREEN='\033[0;32m'
NC='\033[0m'
CYAN='\033[0;36m'

echo "========================================"
echo "    NBTrackr dependencies installer"
echo "========================================"
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
    print("  $FULL_PATH get-pip.py")
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

if [ -f "NBTrackr-imgpin.py" ] && [ -f "Customizer-imgpin.py" ]; then
    echo -e "${CYAN}NBTrackr-imgpin.py${NC} is the main script for running NBTrackr."
    echo -e "${CYAN}Customizer-imgpin.py${NC} is the script for customizing NBTrackr."
    echo
    echo "Run the scripts from inside the current directory:"
    echo -e "  - For ${CYAN}NBTrackr-imgpin.py${NC}: \"./venv/bin/python\" \"NBTrackr-imgpin.py\""
    echo -e "  - For ${CYAN}Customizer-imgpin.py${NC}: \"./venv/bin/python\" \"Customizer-imgpin.py\""
    echo
    echo "Run from anywhere (full path):"
    echo -e "  - For ${CYAN}NBTrackr-imgpin.py${NC}: \"${FULL_PATH}\" \"$(pwd)/NBTrackr-imgpin.py\""
    echo -e "  - For ${CYAN}Customizer-imgpin.py${NC}: \"${FULL_PATH}\" \"$(pwd)/Customizer-imgpin.py\""

else
    echo "Warning: Could not detect which NBTrackr scripts are present in this folder."
fi