"""Точка входа: конфиг → логин → загрузка модулей → работа до отключения."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal

from . import __version__, utils
from .client import login, make_client
from .config import Config, load_config
from .database import Database
from .dispatcher import Dispatcher
from .loader import Loader

log = logging.getLogger("uroboros")


def setup_logging(config: Config) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(config.log_path, encoding="utf-8"),
        ],
    )
    logging.getLogger("telethon").setLevel(logging.WARNING)


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


def main() -> None:
    config = load_config()
    setup_logging(config)
    try:
        asyncio.run(run(config))
    except KeyboardInterrupt:
        return
    if utils.restart_requested():
        log.info("Перезапуск...")
        utils.exec_restart()


if __name__ == "__main__":
    main()
