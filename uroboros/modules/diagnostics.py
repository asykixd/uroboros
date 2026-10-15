import time

from uroboros import Module, command, utils
from uroboros.ratelimit import format_seconds


class Diagnostics(Module):
    """Диагностика: что не загрузилось и почему, статистика команд"""

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

    @command("stats", access="owner", emoji="📊")
    async def stats(self, message):
        """[модуль | reset] — вызовы и время команд, ошибки, заморозки за флуд с момента запуска"""
        arg = utils.get_args_raw(message).strip()
        if arg == "reset":
            self.loader.stats.reset()
            self.loader.ratelimit.hits.clear()
            await utils.answer(message, "🗑 <b>Статистика сброшена</b>")
            return
        if arg:
            module = self.loader.get_module(arg)
            name = module.name if module else arg
            await utils.answer(message, self._module_stats(name))
            return
        await utils.answer(message, self._overview())

    @staticmethod
    def _ms(seconds):
        return f"{seconds * 1000:.0f} мс"

    def _overview(self):
        stats = self.loader.stats
        totals = stats.modules()
        hits = self.loader.ratelimit.hits
        names = set(totals) | set(stats.watcher_errors) | set(hits)
        uptime = utils.format_duration(time.time() - utils.START_TIME)
        prefix = utils.escape_html(utils.get_prefix(self.db.raw))
        if not names:
            return utils.card(
                f"📊 <b>Статистика</b> · за <code>{uptime}</code>",
                "▸ команды ещё не вызывались",
                hint=f"сбросить: <code>{prefix}stats reset</code>",
            )
        lines = []
        for name in sorted(names, key=lambda n: (-totals[n].calls if n in totals else 0, n.lower())):
            parts = []
            if name in totals:
                entry = totals[name]
                parts.append(f"{entry.calls} выз. · ⏱ {self._ms(entry.average)}")
            errors = (totals[name].errors if name in totals else 0) + stats.watcher_errors.get(name, 0)
            if errors:
                parts.append(f"❌ {errors}")
            if hits.get(name):
                parts.append(f"🧊 {hits[name]}")
            lines.append(f"▸ <b>{utils.escape_html(name)}</b> — " + " · ".join(parts))
        return utils.card(
            f"📊 <b>Статистика</b> · за <code>{uptime}</code>",
            lines,
            hint=f"по командам: <code>{prefix}stats модуль</code> · сбросить: <code>{prefix}stats reset</code>",
            expandable=len(lines) > 15,
        )

    def _module_stats(self, name):
        stats = self.loader.stats
        commands = stats.module_commands(name)
        watcher_errors = stats.watcher_errors.get(name, 0)
        hits = self.loader.ratelimit.hits.get(name, 0)
        if not commands and not watcher_errors and not hits:
            return f"📊 <b>{utils.escape_html(name)}</b> · данных пока нет"
        lines = [
            f"▸ <code>{utils.escape_html(cmd)}</code> — {entry.calls} выз. · ⏱ {self._ms(entry.average)}"
            f" (макс. {self._ms(entry.slowest)})" + (f" · ❌ {entry.errors}" if entry.errors else "")
            for cmd, entry in sorted(commands.items(), key=lambda item: -item[1].calls)
        ]
        if watcher_errors:
            lines.append(f"👀 Ошибок в вотчерах: <code>{watcher_errors}</code>")
        if hits:
            lines.append(f"🧊 Срабатываний защиты от флуда: <code>{hits}</code>")
        return utils.card(f"📊 <b>{utils.escape_html(name)}</b>", lines)
