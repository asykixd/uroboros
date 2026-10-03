"""Точка входа: конфиг → логин → загрузка модулей → работа до отключения."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import os
import signal
import subprocess
import sys

from . import __version__, logs, utils, web
from .client import UroborosClient, login, make_client
from .config import Config, get_data_dir, load_config
from .database import Database
from .dispatcher import Dispatcher
from .inline import InlineManager
from .loader import Loader
from .lock import InstanceLock
from .ratelimit import current_module

log = logging.getLogger("uroboros")


UNLOAD_TIMEOUT = 15
NO_SESSION = (
    "Нет сессии Telegram, а вход в консоли без терминала невозможен (служба, Termux:Boot). "
    "Войдите один раз вручную: python -m uroboros"
)


def handle_sigterm(client) -> None:
    """SIGTERM (systemd, docker stop) завершает работу так же аккуратно, как Ctrl+C."""
    if not hasattr(signal, "SIGTERM"):
        return
    loop = asyncio.get_running_loop()
    # Windows: обработчики сигналов в цикле asyncio не поддерживаются.
    with contextlib.suppress(NotImplementedError, RuntimeError):
        loop.add_signal_handler(signal.SIGTERM, lambda: loop.create_task(client.disconnect()))


def notify_frozen(client, name: str, settings: dict) -> None:
    async def send() -> None:
        current_module.set(None)  # уведомление — запрос ядра, а не замороженного модуля
        text = (
            f"❄️ <b>Модуль {utils.escape_html(name)} заморожен</b>\n"
            + utils.quote(
                f"Больше {settings['limit']} запросов к Telegram за {settings['window']} с. "
                f"Его запросы блокируются {settings['freeze']} с, чтобы аккаунт не получил ограничений."
            )
            + "\n<i>Настройка: .security flood</i>"
        )
        try:
            await client.send_message("me", text, parse_mode="html")
        except Exception:
            log.exception("Не удалось сообщить о заморозке модуля %s", name)

    asyncio.get_running_loop().create_task(send())


async def shutdown(loader: Loader) -> None:
    """Выгружает модули, чтобы отработали их on_unload. Зависший модуль не держит выход."""
    try:
        await asyncio.wait_for(loader.unload_all(), UNLOAD_TIMEOUT)
    except asyncio.TimeoutError:
        log.warning("Модули не выгрузились за %d с, завершаю без них", UNLOAD_TIMEOUT)
    except Exception:
        log.exception("Ошибка при выгрузке модулей")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="uroboros", description="Модульный юзербот для Telegram")
    parser.add_argument("--cli", action="store_true", help="входить через консоль, а не через веб-панель")
    parser.add_argument(
        "--host",
        default=os.environ.get("UROBOROS_WEB_HOST", web.DEFAULT_HOST),
        help="адрес веб-панели первого входа (по умолчанию 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("UROBOROS_WEB_PORT", web.DEFAULT_PORT)),
        help="порт веб-панели (по умолчанию 8080)",
    )
    return parser.parse_args(argv)


async def connect(args: argparse.Namespace) -> tuple[Config, UroborosClient]:
    """Клиент с готовой сессией. Нет сессии — вход через веб-панель или, с ``--cli``, в консоли."""
    interactive = sys.stdin is not None and sys.stdin.isatty()
    if args.cli and not interactive and load_config(prompt=False) is None:
        raise SystemExit(NO_SESSION)
    config = load_config(prompt=args.cli)
    client = None
    if config is not None:
        client = make_client(config)
        await client.connect()
        authorized = await client.is_user_authorized()
        if authorized or args.cli:
            if not authorized and not interactive:
                await client.disconnect()
                raise SystemExit(NO_SESSION)
            return config, client
    return await web.first_login(config, get_data_dir(), client, host=args.host, port=args.port)


async def run(args: argparse.Namespace) -> None:
    config, client = await connect(args)
    db = Database(config.db_path)
    loader = Loader(client, db, config.modules_dir)
    client.limiter = loader.ratelimit
    loader.ratelimit.on_freeze = lambda name, settings: notify_frozen(client, name, settings)
    inline = InlineManager(client, db)
    inline.loader = loader
    loader.inline = inline
    try:
        await login(client)
        me = await client.get_me()
        loader.security.me_id = me.id
        log.info("Uroboros %s, аккаунт: %s (id %s)", __version__, me.first_name, me.id)

        await inline.start()
        dispatcher = Dispatcher(client, db, loader)
        await loader.load_all()
        dispatcher.install()
        handle_sigterm(client)

        log.info("Готов. Префикс команд: %s", dispatcher.prefix)
        await client.run_until_disconnected()
    finally:
        await shutdown(loader)
        await inline.stop()
        await client.disconnect()
        db.close()
        log.info("Остановлен")


def supervise() -> None:
    """Windows: держит бота дочерним процессом и перезапускает его по ``RESTART_EXIT_CODE``.

    Новый процесс сидит в той же консоли, что и раньше, а не отрывается от неё.
    """
    env = {**os.environ, utils.SUPERVISED_ENV: "1"}
    while True:
        proc = subprocess.Popen(utils.restart_args(), env=env)
        while True:
            try:
                code = proc.wait()
                break
            except KeyboardInterrupt:
                continue  # Ctrl+C получает и дочерний процесс — ждём, пока он завершится сам
        if code != utils.RESTART_EXIT_CODE:
            sys.exit(code)


def main() -> None:
    if utils.IS_WINDOWS and not os.environ.get(utils.SUPERVISED_ENV):
        supervise()
        return

    args = parse_args(sys.argv[1:])
    data_dir = get_data_dir()
    lock = InstanceLock(data_dir / "uroboros.lock")
    if not lock.acquire():
        pid = lock.owner_pid()
        sys.exit(
            f"Uroboros уже запущен с данными {data_dir}"
            + (f" (PID {pid})" if pid else "")
            + ". Два экземпляра с одной сессией мешают друг другу."
        )

    logs.setup(data_dir / "uroboros.log")
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        return
    finally:
        # До перезапуска: на Windows новый процесс стартует, пока жив старый.
        lock.release()
    if utils.restart_requested():
        log.info("Перезапуск...")
        utils.exec_restart()


if __name__ == "__main__":
    main()
