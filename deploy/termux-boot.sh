#!/data/data/com.termux/files/usr/bin/sh
# Start Uroboros on phone boot (Termux:Boot app): ~/.termux/boot/uroboros
termux-wake-lock
cd "$HOME/uroboros" || exit 1
exec .venv/bin/python -m uroboros --cli >> data/boot.log 2>&1
