from uroboros import Module, command, utils
from uroboros.ratelimit import format_seconds


class Diagnostics(Module):
    """Диагностика: что не загрузилось и почему"""

    @command("doctor", access="owner", emoji="🩺")
    async def doctor(self, message):
        """— что не загрузилось, состояние inline-бота, изменённые файлы, замороженные модули"""
        await utils.answer(message, self._report())

    def _report(self):
        loader = self.loader
        problems = 0
        lines = [f"📦 Загружено модулей: <code>{len(loader.modules)}</code>"]
        sections = []

        if loader.failures:
            problems += len(loader.failures)
            items = [
                f"▸ <b>{utils.escape_html(stem)}</b> — {utils.escape_html(reason)}"
                for stem, reason in sorted(loader.failures.items())
            ]
            sections.append(("❌ <b>Не загрузились</b>", items))

        inline = loader.inline
        if inline is None:
            lines.append("🤖 Inline-бот: не подключён")
        elif inline.ready:
            lines.append(f"🤖 Inline-бот: @{utils.escape_html(inline.bot_username)}")
        else:
            problems += 1
            reason = utils.escape_html(inline.error or "причина в логах")
            lines.append(f"🤖 Inline-бот: не запущен — {reason}")

        if loader.tampered:
            problems += len(loader.tampered)
            items = [f"▸ <b>{utils.escape_html(stem)}</b>" for stem in sorted(loader.tampered)]
            sections.append(("🔏 <b>Файлы изменены не через Uroboros</b>", items))

        limiter = loader.ratelimit
        frozen = [(name, limiter.frozen_for(name)) for name in list(limiter.frozen)]
        frozen = [f"▸ <b>{utils.escape_html(n)}</b> — ещё {format_seconds(left)}" for n, left in frozen if left]
        if frozen:
            problems += len(frozen)
            sections.append(("🧊 <b>Заморожены за флуд</b>", frozen))

        title = "🩺 <b>Диагностика</b> · " + (f"проблем: {problems}" if problems else "всё в порядке")
        text = utils.card(title, lines)
        for heading, items in sections:
            text += f"\n{heading}\n" + utils.quote("\n".join(items), expandable=len(items) > 10)
        prefix = utils.escape_html(utils.get_prefix(self.db.raw))
        hint = (
            f"подробности: <code>{prefix}logs error</code> · переустановить модуль: <code>{prefix}dlm</code>"
            if problems
            else f"логи: <code>{prefix}logs</code>"
        )
        return text + f"\n💡 <i>{hint}</i>"
