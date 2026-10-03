"""Проверка совместимости с модулями Hikka/FTG: скачать модули из репозиториев и попробовать загрузить.

    .venv/bin/python scripts/hikka_compat.py            # таблица в docs/hikka-compat.md
    .venv/bin/python scripts/hikka_compat.py --limit 20 # не больше 20 модулей из репозитория

Модули загружаются без Telegram: вместо клиента — заглушка, вместо БД — SQLite в памяти.
Зависимости из ``# requires:`` не ставятся: такие модули помечаются отдельно.
Нужна сеть (GitHub API и raw.githubusercontent.com).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import tempfile
import urllib.request
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from telethon import TelegramClient  # noqa: E402

from uroboros import loader as core_loader  # noqa: E402
from uroboros.database import Database  # noqa: E402
from uroboros.errors import LoadError  # noqa: E402

REPOS = [
    "hikariatama/ftg",
    "GeekTG/FTG-Modules",
    "Fl1yd/FTG-Modules",
    "KeyZenD/modules",
    "vsecoder/hikka_modules",
    "coddrago/modules",
    "MuRuLOSE/HikkaModulesRepo",
    "sqlmerr/hikka_mods",
    "N3rcy/modules",
]
OUTPUT = ROOT / "docs" / "hikka-compat.md"
TIMEOUT = 20

OK, DEPS, FAIL = "✅", "📦", "❌"


@dataclass
class Result:
    repo: str
    name: str
    status: str
    detail: str = ""


class MissingRequirements(LoadError):
    pass


def _get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "Uroboros-compat"})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return response.read()


def list_modules(repo: str) -> list[tuple[str, str]]:
    items = json.loads(_get(f"https://api.github.com/repos/{repo}/contents/"))
    return sorted(
        (item["name"], item["download_url"])
        for item in items
        if item.get("type") == "file" and item["name"].endswith(".py") and not item["name"].startswith("_")
    )


def fake_client() -> mock.MagicMock:
    client = mock.MagicMock(spec=TelegramClient)
    client.list_event_handlers.return_value = []
    return client


async def check_source(source: str, tmp: Path) -> tuple[str, str]:
    """Пробует загрузить модуль: (статус, подробности)."""

    async def no_pip(packages):
        raise MissingRequirements("нужны пакеты: " + " ".join(packages))

    db = Database(":memory:")
    loader = core_loader.Loader(fake_client(), db, tmp)
    loader.security.me_id = 1
    try:
        with mock.patch.object(core_loader, "pip_install", no_pip):
            instances = await asyncio.wait_for(loader.install(source, "file:compat.py"), TIMEOUT)
        commands = sum(len(loader.module_commands(inst)) for inst in instances)
        await asyncio.wait_for(loader.unload_all(), TIMEOUT)
        return OK, f"команд: {commands}"
    except MissingRequirements as e:
        return DEPS, str(e)
    except LoadError as e:
        return FAIL, str(e).splitlines()[0][:200]
    except asyncio.TimeoutError:
        return FAIL, "загрузка зависла"
    except BaseException as e:  # модуль может бросить что угодно, вплоть до SystemExit
        return FAIL, f"{type(e).__name__}: {e}".splitlines()[0][:200]
    finally:
        db.close()


async def run(repos: list[str], limit: int | None) -> list[Result]:
    results = []
    with tempfile.TemporaryDirectory() as tmp:
        for repo in repos:
            try:
                modules = list_modules(repo)
            except Exception as e:
                print(f"{repo}: не удалось получить список ({e})", file=sys.stderr)
                continue
            for name, url in modules[:limit]:
                try:
                    source = _get(url).decode("utf-8")
                except Exception as e:
                    results.append(Result(repo, name, FAIL, f"не скачался: {e}"))
                    continue
                status, detail = await check_source(source, Path(tmp))
                results.append(Result(repo, name, status, detail))
                print(f"{status} {repo}/{name} {detail}", flush=True)
    return results


def render(results: list[Result]) -> str:
    counts = Counter(r.status for r in results)
    total = len(results) or 1
    lines = [
        "# Совместимость с модулями Hikka/FTG",
        "",
        "Таблицу собирает `scripts/hikka_compat.py`: он скачивает модули из репозиториев и загружает их",
        "в Uroboros без Telegram (клиент — заглушка). Зависимости из `# requires:` не ставятся.",
        "«Загружается» значит, что модуль исполнился, зарегистрировал команды и прошёл `client_ready`;",
        "работу самих команд с настоящим аккаунтом это не проверяет.",
        "",
        f"- {OK} загружается: **{counts[OK]}** из {len(results)} ({counts[OK] * 100 // total}%)",
        f"- {DEPS} нужны зависимости (без них не проверить): **{counts[DEPS]}**",
        f"- {FAIL} не загружается: **{counts[FAIL]}**",
        "",
        "| Репозиторий | Модуль | | Подробности |",
        "|---|---|---|---|",
    ]
    for r in results:
        detail = r.detail.replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {r.repo} | `{r.name}` | {r.status} | {detail} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--limit", type=int, default=None, help="сколько модулей брать из каждого репозитория")
    parser.add_argument("--repo", action="append", help="проверить только этот репозиторий (можно несколько)")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    logging.basicConfig(level=logging.CRITICAL)  # ошибки модулей — в таблице, не в консоли

    results = asyncio.run(run(args.repo or REPOS, args.limit))
    args.output.write_text(render(results), "utf-8")
    counts = Counter(r.status for r in results)
    print(f"\n{OK} {counts[OK]}  {DEPS} {counts[DEPS]}  {FAIL} {counts[FAIL]} → {args.output}")


if __name__ == "__main__":
    main()
