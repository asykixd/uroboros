#!/usr/bin/env sh
# Install Uroboros on Linux and Termux.
#
#   curl -fsSL https://raw.githubusercontent.com/asykixd/uroboros/master/install.sh | sh
#   sh install.sh --service   # + systemd user service (VPS)
#   sh install.sh --boot      # + autostart via Termux:Boot
#   sh install.sh --no-start  # install only, don't start
#
# Install directory: $UROBOROS_DIR (default ~/uroboros).
set -eu

REPO="https://github.com/asykixd/uroboros"
DIR="${UROBOROS_DIR:-$HOME/uroboros}"
SERVICE=0
BOOT=0
START=1

for arg in "$@"; do
    case "$arg" in
        --service) SERVICE=1 ;;
        --boot) BOOT=1 ;;
        --no-start) START=0 ;;
        -h|--help) sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "Unknown option: $arg" >&2; exit 2 ;;
    esac
done

say() { printf '\033[1m%s\033[0m\n' "$*"; }
fail() { printf '\033[31m%s\033[0m\n' "$*" >&2; exit 1; }

IS_TERMUX=0
case "${PREFIX:-}" in *com.termux*) IS_TERMUX=1 ;; esac

# --- system dependencies ---

if [ "$IS_TERMUX" = 1 ]; then
    say "Termux: installing python, git and rust (rust builds pydantic-core for aiogram)"
    pkg update -y
    pkg install -y python git rust
else
    command -v git >/dev/null 2>&1 || fail "git required: sudo apt install git (or your package manager)"
    command -v python3 >/dev/null 2>&1 || fail "Python 3.10+ required: sudo apt install python3 python3-venv"
fi

PYTHON="$(command -v python3 || command -v python)"
"$PYTHON" -c 'import sys; sys.exit(sys.version_info < (3, 10))' \
    || fail "Python 3.10+ required, found $("$PYTHON" -V 2>&1)"
if [ "$IS_TERMUX" = 0 ]; then
    "$PYTHON" -c 'import venv, ensurepip' 2>/dev/null \
        || fail "venv module missing: sudo apt install python3-venv"
fi

# --- source ---

if [ -d "$DIR/.git" ]; then
    say "Updating $DIR"
    git -C "$DIR" pull --ff-only
else
    say "Cloning into $DIR"
    git clone "$REPO" "$DIR"
fi
cd "$DIR"

# --- virtualenv ---

if [ ! -x .venv/bin/python ]; then
    say "Creating virtualenv"
    "$PYTHON" -m venv .venv
fi
say "Installing dependencies (building pydantic-core in Termux takes a few minutes)"
.venv/bin/python -m pip install --disable-pip-version-check -q --upgrade pip
.venv/bin/python -m pip install --disable-pip-version-check -q -e .

# --- autostart ---

if [ "$SERVICE" = 1 ]; then
    command -v systemctl >/dev/null 2>&1 || fail "systemd not found: --service needs Linux with systemd"
    UNIT_DIR="$HOME/.config/systemd/user"
    mkdir -p "$UNIT_DIR"
    sed "s|%h/uroboros|$DIR|g" deploy/uroboros.service > "$UNIT_DIR/uroboros.service"
    systemctl --user daemon-reload
    say "Service installed: $UNIT_DIR/uroboros.service"
    echo "  To keep it running while logged out: sudo loginctl enable-linger $USER"
fi

if [ "$BOOT" = 1 ]; then
    [ "$IS_TERMUX" = 1 ] || fail "--boot is Termux-only"
    mkdir -p "$HOME/.termux/boot"
    sed "s|\$HOME/uroboros|$DIR|g" deploy/termux-boot.sh > "$HOME/.termux/boot/uroboros"
    chmod +x "$HOME/.termux/boot/uroboros"
    say "Autostart installed: ~/.termux/boot/uroboros (needs the Termux:Boot app)"
fi

# --- first run ---

say "Done."
if [ "$SERVICE" = 1 ]; then
    echo "Log in once from the console (the service runs the bot after that):"
    echo "  cd $DIR && .venv/bin/python -m uroboros"
    echo "After login stop it (Ctrl+C) and start the service:"
    echo "  systemctl --user enable --now uroboros"
elif [ "$START" = 1 ]; then
    say "Starting Uroboros: open the login panel link printed below"
    exec .venv/bin/python -m uroboros
else
    echo "Run: cd $DIR && .venv/bin/python -m uroboros"
fi
