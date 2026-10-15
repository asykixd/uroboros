import time

from uroboros import Module, command, utils
from uroboros.ratelimit import format_seconds


class Diagnostics(Module):
    """Diagnostics: what failed to load and why, command statistics"""

    strings = {
        "loaded": "📦 Modules loaded: <code>{count}</code>",
        "failed": "❌ <b>Failed to load</b>",
        "inline_none": "🤖 Inline bot: not connected",
        "inline_ok": "🤖 Inline bot: @{username}",
        "inline_down": "🤖 Inline bot: not running — {reason}",
        "reason_in_logs": "the reason is in the logs",
        "tampered": "🔏 <b>Files changed outside Uroboros</b>",
        "frozen_left": "▸ <b>{name}</b> — {left} left",
        "frozen": "🧊 <b>Frozen for flooding</b>",
        "title": "🩺 <b>Diagnostics</b> · {state}",
        "problems": "problems: {count}",
        "all_good": "all good",
        "hint_problems": "details: <code>{prefix}logs error</code> · reinstall a module: <code>{prefix}dlm</code>",
        "hint_ok": "logs: <code>{prefix}logs</code>",
        "reset": "🗑 <b>Statistics reset</b>",
        "ms": "{ms} ms",
        "stats": "📊 <b>Statistics</b> · for <code>{uptime}</code>",
        "no_calls": "▸ no commands called yet",
        "reset_hint": "reset: <code>{prefix}stats reset</code>",
        "overview_hint": "per command: <code>{prefix}stats module</code> · reset: <code>{prefix}stats reset</code>",
        "calls": "{count} calls",
        "no_data": "📊 <b>{name}</b> · no data yet",
        "max": "max {ms}",
        "watcher_errors": "👀 Watcher errors: <code>{count}</code>",
        "flood_hits": "🧊 Flood protection hits: <code>{count}</code>",
    }
    strings_ru = {
        "_cls_doc": "Диагностика: что не загрузилось и почему, статистика команд",
        "_cmd_doc_doctor": "— что не загрузилось, состояние inline-бота, изменённые файлы, замороженные модули",
        "_cmd_doc_stats": "[модуль | reset] — вызовы и время команд, ошибки, заморозки за флуд с момента запуска",
        "loaded": "📦 Загружено модулей: <code>{count}</code>",
        "failed": "❌ <b>Не загрузились</b>",
        "inline_none": "🤖 Inline-бот: не подключён",
        "inline_ok": "🤖 Inline-бот: @{username}",
        "inline_down": "🤖 Inline-бот: не запущен — {reason}",
        "reason_in_logs": "причина в логах",
        "tampered": "🔏 <b>Файлы изменены не через Uroboros</b>",
        "frozen_left": "▸ <b>{name}</b> — ещё {left}",
        "frozen": "🧊 <b>Заморожены за флуд</b>",
        "title": "🩺 <b>Диагностика</b> · {state}",
        "problems": "проблем: {count}",
        "all_good": "всё в порядке",
        "hint_problems": (
            "подробности: <code>{prefix}logs error</code> · переустановить модуль: <code>{prefix}dlm</code>"
        ),
        "hint_ok": "логи: <code>{prefix}logs</code>",
        "reset": "🗑 <b>Статистика сброшена</b>",
        "ms": "{ms} мс",
        "stats": "📊 <b>Статистика</b> · за <code>{uptime}</code>",
        "no_calls": "▸ команды ещё не вызывались",
        "reset_hint": "сбросить: <code>{prefix}stats reset</code>",
        "overview_hint": "по командам: <code>{prefix}stats модуль</code> · сбросить: <code>{prefix}stats reset</code>",
        "calls": "{count} выз.",
        "no_data": "📊 <b>{name}</b> · данных пока нет",
        "max": "макс. {ms}",
        "watcher_errors": "👀 Ошибок в вотчерах: <code>{count}</code>",
        "flood_hits": "🧊 Срабатываний защиты от флуда: <code>{count}</code>",
    }

    @command("doctor", access="owner", emoji="🩺")
    async def doctor(self, message):
        """— what failed to load, inline bot state, changed files, frozen modules"""
        await utils.answer(message, self._report())

    def _report(self):
        loader = self.loader
        problems = 0
        lines = [self.strings("loaded", count=len(loader.modules))]
        sections = []

        if loader.failures:
            problems += len(loader.failures)
            items = [
                f"▸ <b>{utils.escape_html(stem)}</b> — {utils.escape_html(reason)}"
                for stem, reason in sorted(loader.failures.items())
            ]
            sections.append((self.strings("failed"), items))

        inline = loader.inline
        if inline is None:
            lines.append(self.strings("inline_none"))
        elif inline.ready:
            lines.append(self.strings("inline_ok", username=inline.bot_username))
        else:
            problems += 1
            lines.append(self.strings("inline_down", reason=inline.error or self.strings("reason_in_logs")))

        if loader.tampered:
            problems += len(loader.tampered)
            items = [f"▸ <b>{utils.escape_html(stem)}</b>" for stem in sorted(loader.tampered)]
            sections.append((self.strings("tampered"), items))

        limiter = loader.ratelimit
        frozen = [(name, limiter.frozen_for(name)) for name in list(limiter.frozen)]
        frozen = [self.strings("frozen_left", name=n, left=format_seconds(left)) for n, left in frozen if left]
        if frozen:
            problems += len(frozen)
            sections.append((self.strings("frozen"), frozen))

        state = self.strings("problems", count=problems) if problems else self.strings("all_good")
        text = utils.card(self.strings("title", state=state), lines)
        for heading, items in sections:
            text += f"\n{heading}\n" + utils.quote("\n".join(items), expandable=len(items) > 10)
        prefix = utils.get_prefix(self.db.raw)
        hint = self.strings("hint_problems" if problems else "hint_ok", prefix=prefix)
        return text + f"\n💡 <i>{hint}</i>"

    @command("stats", access="owner", emoji="📊")
    async def stats(self, message):
        """[module | reset] — command calls and timings, errors, flood freezes since start"""
        arg = utils.get_args_raw(message).strip()
        if arg == "reset":
            self.loader.stats.reset()
            self.loader.ratelimit.hits.clear()
            await utils.answer(message, self.strings("reset"))
            return
        if arg:
            module = self.loader.get_module(arg)
            name = module.name if module else arg
            await utils.answer(message, self._module_stats(name))
            return
        await utils.answer(message, self._overview())

    def _ms(self, seconds):
        return self.strings("ms", ms=f"{seconds * 1000:.0f}")

    def _overview(self):
        stats = self.loader.stats
        totals = stats.modules()
        hits = self.loader.ratelimit.hits
        names = set(totals) | set(stats.watcher_errors) | set(hits)
        title = self.strings("stats", uptime=utils.format_duration(time.time() - utils.START_TIME))
        prefix = utils.get_prefix(self.db.raw)
        if not names:
            return utils.card(title, self.strings("no_calls"), hint=self.strings("reset_hint", prefix=prefix))
        lines = []
        for name in sorted(names, key=lambda n: (-totals[n].calls if n in totals else 0, n.lower())):
            parts = []
            if name in totals:
                entry = totals[name]
                parts.append(f"{self.strings('calls', count=entry.calls)} · ⏱ {self._ms(entry.average)}")
            errors = (totals[name].errors if name in totals else 0) + stats.watcher_errors.get(name, 0)
            if errors:
                parts.append(f"❌ {errors}")
            if hits.get(name):
                parts.append(f"🧊 {hits[name]}")
            lines.append(f"▸ <b>{utils.escape_html(name)}</b> — " + " · ".join(parts))
        return utils.card(title, lines, hint=self.strings("overview_hint", prefix=prefix), expandable=len(lines) > 15)

    def _module_stats(self, name):
        stats = self.loader.stats
        commands = stats.module_commands(name)
        watcher_errors = stats.watcher_errors.get(name, 0)
        hits = self.loader.ratelimit.hits.get(name, 0)
        if not commands and not watcher_errors and not hits:
            return self.strings("no_data", name=name)
        lines = [
            f"▸ <code>{utils.escape_html(cmd)}</code> — {self.strings('calls', count=entry.calls)}"
            f" · ⏱ {self._ms(entry.average)} ({self.strings('max', ms=self._ms(entry.slowest))})"
            + (f" · ❌ {entry.errors}" if entry.errors else "")
            for cmd, entry in sorted(commands.items(), key=lambda item: -item[1].calls)
        ]
        if watcher_errors:
            lines.append(self.strings("watcher_errors", count=watcher_errors))
        if hits:
            lines.append(self.strings("flood_hits", count=hits))
        return utils.card(f"📊 <b>{utils.escape_html(name)}</b>", lines)
