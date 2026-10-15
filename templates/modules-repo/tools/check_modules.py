"""Check every module in the repo the way Uroboros does on install: source scan, then a real load.

Usage: python tools/check_modules.py [repo dir]

Modules are the ``*.py`` files in the repo root (``.dlm owner/repo`` lists the same files; names starting with
``_`` are skipped). Dangerous code fails the check, suspicious code is printed as a warning. No Telegram account
is needed: the loader runs without a client and with an in-memory database, as in Uroboros's own tests.
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

from uroboros import scan
from uroboros.database import Database
from uroboros.errors import LoadError
from uroboros.loader import Loader


def module_files(root: Path) -> list[Path]:
    return sorted(p for p in root.glob("*.py") if not p.name.startswith("_"))


async def check(path: Path) -> list[str]:
    """Problems found in one module file; empty means it passed."""
    source = path.read_text("utf-8")
    report = scan.scan(source)
    for finding in report.warnings:
        print(f"  warning: {scan.describe([finding])}")
    if report.dangerous:
        return [f"dangerous: {scan.describe([finding])}" for finding in report.dangerous]

    with tempfile.TemporaryDirectory() as modules_dir:
        loader = Loader(None, Database(":memory:"), Path(modules_dir))
        try:
            instances = await loader.install(source, f"file:{path.name}")
        except Exception as e:  # any error in a module's top-level code is a failed check, not a crash
            return [f"load failed: {e if isinstance(e, LoadError) else repr(e)}"]
        finally:
            await loader.unload_all()
    if not instances:
        return ["no Module subclass found"]
    return []


async def main(root: Path) -> int:
    files = module_files(root)
    if not files:
        print(f"No modules in {root}")
        return 1
    failed = 0
    for path in files:
        print(f"{path.name}")
        problems = await check(path)
        for problem in problems:
            print(f"  {problem}")
        failed += bool(problems)
    print(f"\n{len(files) - failed}/{len(files)} modules passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd())))
