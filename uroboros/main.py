"""Точка входа: конфиг → логин → загрузка модулей → работа до отключения."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import signal
import subprocess
import sys

from . import __version__, logs, utils
from .client import login, make_client
from .config import Config, load_config
from .database import Database
from .dispatcher import Dispatcher
from .loader import Loader
from .lock import InstanceLock

log = logging.getLogger("uroboros")


UNLOAD_TIMEOUT = 15


def handle_sigterm(client) -> None:
    """SIGTERM (systemd, docker stop) завершает работу так же аккуратно, как Ctrl+C."""
    if not hasattr(signal, "SIGTERM"):
        return
    loop = asyncio.get_running_loop()
    # Windows: обработчики сигналов в цикле asyncio не поддерживаются.
    with contextlib.suppress(NotImplementedError, RuntimeError):
        loop.add_signal_handler(signal.SIGTERM, lambda: loop.create_task(client.disconnect()))


async def shutdown(loader: Loader) -> None:
    """Выгружает модули, чтобы отработали их on_unload. Зависший модуль не держит выход."""
    try:
        await asyncio.wait_for(loader.unload_all(), UNLOAD_TIMEOUT)
    except asyncio.TimeoutError:
        log.warning("Модули не выгрузились за %d с, завершаю без них", UNLOAD_TIMEOUT)
    except Exception:
        log.exception("Ошибка при выгрузке модулей")


async def run(config: Config) -> None:
    db = Database(config.db_path)
    client = make_client(config)
    loader = Loader(client, db, config.modules_dir)
    try:
        await login(client)
        me = await client.get_me()
        log.info("Uroboros %s, аккаунт: %s (id %s)", __version__, me.first_name, me.id)

        dispatcher = Dispatcher(client, db, loader)
        await loader.load_all()
        dispatcher.install()
        handle_sigterm(client)

        log.info("Готов. Префикс команд: %s", dispatcher.prefix)
        await client.run_until_disconnected()
    finally:
        await shutdown(loader)
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

    config = load_config()
    lock = InstanceLock(config.lock_path)
    if not lock.acquire():
        pid = lock.owner_pid()
        sys.exit(
            f"Uroboros уже запущен с данными {config.data_dir}"
            + (f" (PID {pid})" if pid else "")
            + ". Два экземпляра с одной сессией мешают друг другу."
        )

    logs.setup(config.log_path)
    try:
        asyncio.run(run(config))
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
