"""Генерирует страницы документации из кода: справочник команд и примеры модулей.

python scripts/gen_docs.py          # перезаписать docs/commands.md и docs/examples.md
python scripts/gen_docs.py --check  # только проверить, что они актуальны (то же делает tests/test_docs.py)
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from uroboros.database import Database  # noqa: E402
from uroboros.loader import Loader  # noqa: E402
from uroboros.security import LEVEL_NAMES  # noqa: E402

DOCS = ROOT / "docs"
EXAMPLES = ROOT / "examples"
NOTICE = "<!-- Сгенерировано scripts/gen_docs.py из кода — не править вручную. -->\n\n"


def cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


async def _commands() -> str:
    with tempfile.TemporaryDirectory() as tmp:
        db = Database(":memory:")
        loader = Loader(None, db, Path(tmp) / "modules")
        await loader.load_all()
        parts = [
            "# Команды\n\n",
            NOTICE,
            "Встроенные команды Uroboros. Префикс по умолчанию — точка, меняется командой `.setprefix`. ",
            "Доступ — кто ещё, кроме этого аккаунта, может вызвать команду (см. [Безопасность](security.md)); ",
            "права меняются командой `.security <команда> <уровень>`.\n",
        ]
        for module in sorted(loader.modules.values(), key=lambda m: m.name.lower()):
            commands = sorted(loader.module_commands(module), key=lambda c: c.name)
            if not commands:
                continue
            parts.append(f"\n## {module.name}\n\n{(type(module).__doc__ or '').strip()}\n\n")
            parts.append("| Команда | Что делает | Доступ |\n|---|---|---|\n")
            for cmd in commands:
                args, _, about = cmd.info.doc.partition("— ")
                usage = f"`.{cmd.name}{(' ' + args.strip()) if args.strip() else ''}`"
                if cmd.info.aliases:
                    usage += " (" + ", ".join(f"`.{alias}`" for alias in cmd.info.aliases) + ")"
                parts.append(
                    f"| {cell(usage)} | {cell(about.strip() or cmd.info.doc)} | {LEVEL_NAMES[cmd.info.access]} |\n"
                )
        await loader.unload_all()
        db.close()
    return "".join(parts)


def _examples() -> str:
    parts = [
        "# Примеры модулей\n\n",
        NOTICE,
        "Каждый пример загружается в тестах (`tests/test_examples.py`), поэтому код ниже рабочий для текущей версии. ",
        "Установить пример: ответьте на файл командой `.lm` или `.dlm asykixd/uroboros/examples/<имя>`.\n",
    ]
    for path in sorted(EXAMPLES.glob("*.py")):
        source = path.read_text("utf-8")
        parts.append(f"\n## {path.stem}\n\n```python\n{source.rstrip()}\n```\n")
    return "".join(parts)


def generate() -> dict[Path, str]:
    return {DOCS / "commands.md": asyncio.run(_commands()), DOCS / "examples.md": _examples()}


def main() -> int:
    check = "--check" in sys.argv
    stale = []
    for path, text in generate().items():
        if path.exists() and path.read_text("utf-8") == text:
            continue
        stale.append(path)
        if not check:
            path.write_text(text, "utf-8")
    if check and stale:
        print("Устарели:", ", ".join(str(p.relative_to(ROOT)) for p in stale), "— запустите scripts/gen_docs.py")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
