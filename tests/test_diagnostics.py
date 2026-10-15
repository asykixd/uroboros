import asyncio
from types import SimpleNamespace

from conftest import FakeMessage

SAFE = """
from uroboros import Module, command

class Demo(Module):
    @command("one")
    async def one(self, m):
        pass
"""
STEALER = SAFE.replace("        pass\n", "        await self.client.send_message('me', self.client.session.save())\n")
BROKEN = SAFE.replace("class Demo", "raise RuntimeError('boom')\nclass Demo")


def run(loader, text):
    message = FakeMessage(text)
    asyncio.run(loader.get_command(text.split()[0][1:]).func(message))
    return message.edits[-1]


def test_doctor_all_clear(builtin_loader):
    text = run(builtin_loader, ".doctor")
    assert text.startswith("🩺 <b>Диагностика</b> · всё в порядке")
    assert "Inline-бот: не подключён" in text


def test_doctor_reports_failed_and_tampered_modules(builtin_loader):
    loader = builtin_loader
    asyncio.run(loader.install(SAFE, "https://example.com/demo.py"))
    asyncio.run(loader.install(SAFE.replace("Demo", "Other").replace('"one"', '"two"'), "https://example.com/o.py"))
    (loader.modules_dir / "demo.py").write_text(STEALER, encoding="utf-8")
    (loader.modules_dir / "other.py").write_text(BROKEN.replace("Demo", "Other"), encoding="utf-8")
    asyncio.run(loader.reload_all())

    text = run(loader, ".doctor")
    assert "проблем: 4" in text  # two failures, two edited files
    assert "<b>demo</b> — файл изменён не через Uroboros, опасный код" in text
    assert "<b>other</b> — Ошибка в коде модуля: RuntimeError('boom')" in text
    assert "🔏 <b>Файлы изменены не через Uroboros</b>\n<blockquote>▸ <b>demo</b>\n▸ <b>other</b>" in text

    # Reinstalling through Uroboros clears both problems.
    asyncio.run(loader.install(SAFE, "https://example.com/demo.py"))
    assert "demo" not in loader.failures and "demo" not in loader.tampered
    assert set(loader.failures) == loader.tampered == {"other"}


def test_doctor_reports_missing_file(builtin_loader):
    loader = builtin_loader
    asyncio.run(loader.install(SAFE, "https://example.com/demo.py"))
    (loader.modules_dir / "demo.py").unlink()
    asyncio.run(loader.reload_all())
    assert "<b>demo</b> — файл модуля пропал" in run(loader, ".doctor")


def test_doctor_reports_inline_and_frozen(builtin_loader):
    loader = builtin_loader
    loader.inline = SimpleNamespace(ready=False, error="токен <отклонён>", release=lambda stem: None)
    loader.ratelimit.frozen["Spammer"] = loader.ratelimit.clock() + 120
    text = run(loader, ".doctor")
    assert "проблем: 2" in text
    assert "Inline-бот: не запущен — токен &lt;отклонён&gt;" in text
    assert "🧊 <b>Заморожены за флуд</b>" in text and "<b>Spammer</b> — ещё 2 мин 0 с" in text

    loader.inline = SimpleNamespace(ready=True, bot_username="my_bot", release=lambda stem: None)
    assert "Inline-бот: @my_bot" in run(loader, ".doctor")


def test_stats_overview_and_module(builtin_loader):
    loader = builtin_loader
    assert "команды ещё не вызывались" in run(loader, ".stats")

    stats = loader.stats
    stats.record_command("Demo<x>", "one", 0.010, failed=False)
    stats.record_command("Demo<x>", "one", 0.030, failed=True)
    stats.record_command("Help", "help", 0.002, failed=False)
    stats.watcher_errors["Demo<x>"] += 2
    loader.ratelimit.hits["Spammer"] += 3

    text = run(loader, ".stats")
    assert text.startswith("📊 <b>Статистика</b>")
    assert "▸ <b>Demo&lt;x&gt;</b> — 2 выз. · ⏱ 20 мс · ❌ 3" in text
    assert "▸ <b>Help</b> — 1 выз. · ⏱ 2 мс" in text
    assert "▸ <b>Spammer</b> — 🧊 3" in text
    assert text.index("Demo&lt;x&gt;") < text.index("Help") < text.index("Spammer")

    text = run(loader, ".stats Demo<x>")
    assert "▸ <code>one</code> — 2 выз. · ⏱ 20 мс (макс. 30 мс) · ❌ 1" in text
    assert "Ошибок в вотчерах: <code>2</code>" in text
    assert run(loader, ".stats help").startswith("📊 <b>Help</b>")  # module name is case-insensitive
    assert "данных пока нет" in run(loader, ".stats nothing")

    assert "сброшена" in run(loader, ".stats reset")
    assert not stats.commands and not stats.watcher_errors and not loader.ratelimit.hits
