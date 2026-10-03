#!/usr/bin/env sh
# Установка Uroboros на Linux и в Termux.
#
#   curl -fsSL https://raw.githubusercontent.com/asykixd/uroboros/master/install.sh | sh
#   sh install.sh --service   # + systemd user service (VPS)
#   sh install.sh --boot      # + автозапуск через Termux:Boot
#   sh install.sh --no-start  # только установить, не запускать
#
# Каталог установки: $UROBOROS_DIR (по умолчанию ~/uroboros).
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
        *) echo "Неизвестный параметр: $arg" >&2; exit 2 ;;
    esac
done

say() { printf '\033[1m%s\033[0m\n' "$*"; }
fail() { printf '\033[31m%s\033[0m\n' "$*" >&2; exit 1; }

IS_TERMUX=0
case "${PREFIX:-}" in *com.termux*) IS_TERMUX=1 ;; esac

# --- зависимости системы ---

if [ "$IS_TERMUX" = 1 ]; then
    say "Termux: ставлю python, git и rust (rust нужен, чтобы собрать pydantic-core для aiogram)"
    pkg update -y
    pkg install -y python git rust
else
    command -v git >/dev/null 2>&1 || fail "Нужен git: sudo apt install git (или пакетный менеджер вашей системы)"
    command -v python3 >/dev/null 2>&1 || fail "Нужен Python 3.10+: sudo apt install python3 python3-venv"
fi

PYTHON="$(command -v python3 || command -v python)"
"$PYTHON" -c 'import sys; sys.exit(sys.version_info < (3, 10))' \
    || fail "Нужен Python 3.10 или новее, а установлен $("$PYTHON" -V 2>&1)"
if [ "$IS_TERMUX" = 0 ]; then
    "$PYTHON" -c 'import venv, ensurepip' 2>/dev/null \
        || fail "Нет модуля venv: sudo apt install python3-venv"
fi

# --- исходники ---

if [ -d "$DIR/.git" ]; then
    say "Обновляю $DIR"
    git -C "$DIR" pull --ff-only
else
    say "Клонирую в $DIR"
    git clone "$REPO" "$DIR"
fi
cd "$DIR"

# --- виртуальное окружение ---

if [ ! -x .venv/bin/python ]; then
    say "Создаю виртуальное окружение"
    "$PYTHON" -m venv .venv
fi
say "Ставлю зависимости (в Termux сборка pydantic-core займёт несколько минут)"
.venv/bin/python -m pip install --disable-pip-version-check -q --upgrade pip
.venv/bin/python -m pip install --disable-pip-version-check -q -e .

# --- автозапуск ---

if [ "$SERVICE" = 1 ]; then
    command -v systemctl >/dev/null 2>&1 || fail "systemd не найден: --service только для Linux с systemd"
    UNIT_DIR="$HOME/.config/systemd/user"
    mkdir -p "$UNIT_DIR"
    sed "s|%h/uroboros|$DIR|g" deploy/uroboros.service > "$UNIT_DIR/uroboros.service"
    systemctl --user daemon-reload
    say "Служба установлена: $UNIT_DIR/uroboros.service"
    echo "  Чтобы она работала без входа в систему: sudo loginctl enable-linger $USER"
fi

if [ "$BOOT" = 1 ]; then
    [ "$IS_TERMUX" = 1 ] || fail "--boot только для Termux"
    mkdir -p "$HOME/.termux/boot"
    sed "s|\$HOME/uroboros|$DIR|g" deploy/termux-boot.sh > "$HOME/.termux/boot/uroboros"
    chmod +x "$HOME/.termux/boot/uroboros"
    say "Автозапуск установлен: ~/.termux/boot/uroboros (нужно приложение Termux:Boot)"
fi

# --- первый запуск ---

say "Готово."
if [ "$SERVICE" = 1 ]; then
    echo "Первый вход — в консоли (дальше бот работает службой):"
    echo "  cd $DIR && .venv/bin/python -m uroboros"
    echo "После входа остановите его (Ctrl+C) и запустите службу:"
    echo "  systemctl --user enable --now uroboros"
elif [ "$START" = 1 ]; then
    say "Запускаю Uroboros: откройте ссылку на веб-панель входа, которая появится ниже"
    exec .venv/bin/python -m uroboros
else
    echo "Запуск: cd $DIR && .venv/bin/python -m uroboros"
fi
