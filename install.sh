#!/usr/bin/env bash
set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[1;31m'
NC='\033[0m'
CYAN='\033[0;36m'

echo "==================================="
echo "        NBTrackr installer"
echo "==================================="
echo

if command -v python3 &>/dev/null; then
    PYTHON_BIN="python3"
elif command -v python &>/dev/null; then
    PYTHON_BIN="python"
else
    echo -e "${RED}ERROR: Python is not installed.${NC}"
    echo "Install it via your distro package manager:"
    echo "  Debian/Ubuntu: sudo apt install python3"
    echo "  Arch Linux:    sudo pacman -S python"
    echo "  Fedora:        sudo dnf install python3"
    exit 1
fi

if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    "$PYTHON_BIN" -m venv venv
else
    echo "Virtual environment already exists."
fi

FULL_PATH="$(pwd)/venv/bin/python"

"$FULL_PATH" - <<'EOF'
import sys
try:
    import pip
except ImportError:
    print("ERROR: pip is not installed in this virtual environment.")
    print("Installation of NBTrackr dependencies will fail.")
    print("You can try to fix this by running:")
    print(f"  {sys.executable} -m ensurepip")
    print("Or manually via:")
    print("  curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py")
    print(f"  {sys.executable} get-pip.py")
    sys.exit(1)
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
DESKTOP_DIR="$HOME/.local/share/applications"

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

detect_terminal() {
    local p=$PPID
    local name
    local parent_pid

    for _ in 1 2 3 4 5; do
        name="$(ps -p "$p" -o comm= 2>/dev/null)"
        name="${name// /}"
        case "$name" in
            *gnome*)
                echo "gnome-terminal"
                return
                ;;
            *xfce*)
                echo "xfce4-terminal"
                return
                ;;
            bash|zsh|sh|fish|dash)
                ;;
            "")
                break
                ;;
            *)
                echo "$name"
                return
                ;;
        esac
        parent_pid="$(ps -p "$p" -o ppid= 2>/dev/null)"
        parent_pid="${parent_pid// /}"
        if [ -z "$parent_pid" ] || [ "$parent_pid" -le 1 ]; then
            break
        fi

        p="$parent_pid"
    done
    echo ""
}

CURRENT_TERMINAL="$(detect_terminal)"

if [ -n "$CURRENT_TERMINAL" ]; then
    case "$CURRENT_TERMINAL" in
        gnome-terminal)
            TERM_EXEC_FLAG="--"
            ;;
        xfce4-terminal)
            TERM_EXEC_FLAG="-x"
            ;;
        *)
            TERM_EXEC_FLAG="-e"
            ;;
    esac
fi

EXTRA_FLAGS=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --flags)
            shift
            EXTRA_FLAGS="$*"
            break
            ;;
        *)
            shift
            ;;
    esac
done

mkdir -p "$DESKTOP_DIR"

NBTRACKR_CMD="nbtrackr"
if [ -n "$EXTRA_FLAGS" ]; then
    NBTRACKR_CMD="nbtrackr $EXTRA_FLAGS"
fi

if [ -n "$CURRENT_TERMINAL" ]; then
    MAIN_EXEC="$CURRENT_TERMINAL $TERM_EXEC_FLAG $NBTRACKR_CMD"
    echo "When you launch the program via your application launcher, it will be run with the current terminal you're using: $CURRENT_TERMINAL"
else
    MAIN_EXEC="$NBTRACKR_CMD"
    echo -e "${YELLOW}Warning: could not detect your current terminal. NBTrackr should be run via a terminal.${NC}"
    echo "The .desktop launcher will run NBTrackr without a terminal window."
    echo "To fix this, edit ~/.local/share/applications/nbtrackr.desktop"
    echo "and change Exec= to include your terminal manually, e.g.:"
    echo -e "  ${CYAN}Exec=kitty -e nbtrackr${NC}"
    echo
fi

sed "s|__NBTRACKR_EXEC__|$MAIN_EXEC|g" \
    assets/desktop/nbtrackr.desktop > "$DESKTOP_DIR/nbtrackr.desktop"
chmod +x "$DESKTOP_DIR/nbtrackr.desktop"

echo
echo -e "${GREEN}Added NBTrackr to your application launcher.${NC}"
if [ -n "$EXTRA_FLAGS" ]; then
    echo "  (program will use flags: $EXTRA_FLAGS)"
fi
echo

echo "Would you like to add NBTrackr Settings to your application launcher?"
echo "You can also open settings by running \"nbtrackr --settings\" in your terminal."
read -rp "[y/N] " create_settings_entry
if [[ "$create_settings_entry" =~ ^[Yy]$ ]]; then
    cp assets/desktop/nbtrackr-settings.desktop "$DESKTOP_DIR/nbtrackr-settings.desktop"
    chmod +x "$DESKTOP_DIR/nbtrackr-settings.desktop"
    echo
    echo -e "${GREEN}Added NBTrackr Settings to your application launcher.${NC}"
    echo
else
    echo "Skipped."
    echo
fi

echo "To run NBTrackr:"
echo -e "  ${CYAN}nbtrackr${NC}"
echo
echo "To configure NBTrackr:"
echo -e "  ${CYAN}nbtrackr --settings${NC}"
echo
echo "To uninstall NBTrackr, run:"
echo -e "  ${CYAN}./uninstall.sh${NC}"
echo
echo "To add or change flags used by the program in your application launcher (NOT when you run \"nbtrackr\" in terminal), rerun install.sh"
echo "with --flags followed by one or more flags in quotes, for example:"
echo -e "  ${CYAN}./install.sh --flags \"--click-through\"${NC}"
echo -e "  ${CYAN}./install.sh --flags \"--click-through --lock-overlay\"${NC}"
echo
echo "Possible flags:"
echo -e "  ${CYAN}--headless${NC}       Makes the window not appear (the overlay is always written to /tmp/imgpin-overlay.png)"
echo -e "  ${CYAN}--lock-overlay${NC}   Locks the overlay in place (window cannot be moved)"
echo -e "  ${CYAN}--click-through${NC}  Makes the overlay click-through (window cannot be moved)"
echo -e "  ${CYAN}--debug${NC}          Enable debug logging"
echo
echo "You can also edit ~/.local/share/applications/nbtrackr.desktop manually."
