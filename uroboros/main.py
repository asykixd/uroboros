"""Точка входа: конфиг → логин → загрузка модулей → работа до отключения."""

from __future__ import annotations

import asyncio
import logging

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


async def run(config: Config) -> None:
    db = Database(config.db_path)
    client = make_client(config)
    try:
        await login(client)
        me = await client.get_me()
        log.info("Uroboros %s, аккаунт: %s (id %s)", __version__, me.first_name, me.id)

        loader = Loader(client, db, config.modules_dir)
        dispatcher = Dispatcher(client, db, loader)
        await loader.load_all()
        dispatcher.install()

        log.info("Готов. Префикс команд: %s", dispatcher.prefix)
        await client.run_until_disconnected()
    finally:
        await client.disconnect()
        db.close()


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
