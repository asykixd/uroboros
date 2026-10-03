#!/data/data/com.termux/files/usr/bin/sh
# Автозапуск Uroboros при загрузке телефона (приложение Termux:Boot): ~/.termux/boot/uroboros
termux-wake-lock
cd "$HOME/uroboros" || exit 1
exec .venv/bin/python -m uroboros --cli >> data/boot.log 2>&1
