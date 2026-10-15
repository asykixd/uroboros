"""Hikka/FTG module compatibility check: download modules from repos and try to load them.

    .venv/bin/python scripts/hikka_compat.py            # tables in docs/hikka-compat{,.ru}.md
    .venv/bin/python scripts/hikka_compat.py --limit 20 # at most 20 modules per repo

Modules load without Telegram: a stub client and an in-memory SQLite database.
``# requires:`` dependencies aren't installed; such modules are marked separately.
Needs network (GitHub API and raw.githubusercontent.com).
"""

from __future__ import annotations

import argparse
import asyncio
import html
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
OUTPUT_RU = ROOT / "docs" / "hikka-compat.ru.md"
TEXTS = {
    "en": {
        "title": "Hikka/FTG module compatibility",
        "intro": [
            "Built by `scripts/hikka_compat.py`: it downloads modules from repos and loads them into Uroboros",
            "without Telegram (stub client). `# requires:` dependencies aren't installed.",
            '"Loads" means the module executed, registered commands and passed `client_ready`;',
            "commands aren't tested against a real account.",
        ],
        "ok": "loads: **{ok}** of {total} ({percent}%)",
        "deps": "needs dependencies (can't check without them): **{deps}**",
        "fail": "fails: **{fail}**",
        "header": "| Repo | Module | | Details |",
    },
    "ru": {
        "title": "Совместимость с модулями Hikka/FTG",
        "intro": [
            "Собрано `scripts/hikka_compat.py`: он скачивает модули из репозиториев и загружает их в Uroboros",
            "без Telegram (клиент-заглушка). Зависимости из `# requires:` не ставятся.",
            "«Загружается» — модуль исполнился, зарегистрировал команды и прошёл `client_ready`;",
            "сами команды на настоящем аккаунте не проверяются. Подробности — на английском, как их выдал модуль.",
        ],
        "ok": "загружается: **{ok}** из {total} ({percent}%)",
        "deps": "нужны зависимости (без них не проверить): **{deps}**",
        "fail": "не загружается: **{fail}**",
        "header": "| Репозиторий | Модуль | | Подробности |",
    },
}
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
    """Tries to load a module: (status, details)."""

    async def no_pip(packages):
        raise MissingRequirements("needs packages: " + " ".join(packages))

    db = Database(":memory:")
    loader = core_loader.Loader(fake_client(), db, tmp)
    loader.security.me_id = 1
    try:
        with mock.patch.object(core_loader, "pip_install", no_pip):
            instances = await asyncio.wait_for(loader.install(source, "file:compat.py", force=True), TIMEOUT)
        commands = sum(len(loader.module_commands(inst)) for inst in instances)
        await asyncio.wait_for(loader.unload_all(), TIMEOUT)
        return OK, f"commands: {commands}"
    except MissingRequirements as e:
        return DEPS, str(e)
    except LoadError as e:
        return FAIL, str(e).splitlines()[0][:200]
    except asyncio.TimeoutError:
        return FAIL, "load hung"
    except BaseException as e:  # a module may raise anything, even SystemExit
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
                print(f"{repo}: failed to list ({e})", file=sys.stderr)
                continue
            for name, url in modules[:limit]:
                try:
                    source = _get(url).decode("utf-8")
                except Exception as e:
                    results.append(Result(repo, name, FAIL, f"download failed: {e}"))
                    continue
                status, detail = await check_source(source, Path(tmp))
                results.append(Result(repo, name, status, detail))
                print(f"{status} {repo}/{name} {detail}", flush=True)
    return results


def _cell(text: str) -> str:
    """Table cell from third-party text: the docs site renders raw HTML in Markdown, so escape it."""
    return html.escape(text, quote=False).replace("|", "\\|").replace("`", "'").replace("\n", " ")


def render(results: list[Result], lang: str = "en") -> str:
    texts = TEXTS[lang]
    counts = Counter(r.status for r in results)
    total = len(results) or 1
    lines = [
        f"# {texts['title']}",
        "",
        *texts["intro"],
        "",
        f"- {OK} " + texts["ok"].format(ok=counts[OK], total=len(results), percent=counts[OK] * 100 // total),
        f"- {DEPS} " + texts["deps"].format(deps=counts[DEPS]),
        f"- {FAIL} " + texts["fail"].format(fail=counts[FAIL]),
        "",
        texts["header"],
        "|---|---|---|---|",
    ]
    for r in results:
        lines.append(f"| {_cell(r.repo)} | `{_cell(r.name)}` | {r.status} | {_cell(r.detail)} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--limit", type=int, default=None, help="modules per repo")
    parser.add_argument("--repo", action="append", help="check only this repo (repeatable)")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--output-ru", type=Path, default=OUTPUT_RU)
    args = parser.parse_args()
    logging.basicConfig(level=logging.CRITICAL)  # module errors go to the table, not the console

    results = asyncio.run(run(args.repo or REPOS, args.limit))
    args.output.write_text(render(results), "utf-8")
    args.output_ru.write_text(render(results, "ru"), "utf-8")
    counts = Counter(r.status for r in results)
    print(f"\n{OK} {counts[OK]}  {DEPS} {counts[DEPS]}  {FAIL} {counts[FAIL]} → {args.output}")


if __name__ == "__main__":
    main()
