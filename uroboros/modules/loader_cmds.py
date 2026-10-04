import asyncio
import difflib
import time
from dataclasses import dataclass

from uroboros import Module, command, download, github, scan, utils
from uroboros.errors import InlineError
from uroboros.loader import LoadError

MAX_SIZE = download.MAX_SIZE
SEARCH_CACHE = 600
SEARCH_LIMIT = 30
CANCEL = {"text": "Отмена", "action": "close"}
DIFF_LINES = 40  # строк разницы на модуль
DIFF_BUDGET = 2500  # символов разницы на всё сообщение: оно должно влезть в 4096 вместе с остальным


@dataclass
class Candidate:
    """Скачанный модуль, который ещё не установлен."""

    source: str
    origin: str  # откуда брать обновления
    pin: str | None  # та же версия в конкретном коммите (GitHub)
    report: scan.Report


async def fetch_candidate(url, data=None):
    """Скачивает модуль; с GitHub — по ссылке на конкретный коммит, чтобы знать, какая версия установлена."""
    pinned = await github.pin(url)
    if pinned is not None:
        data = await download.download(pinned[0])
    elif data is None:
        data = await download.download(url)
    source = download.decode(data)
    return Candidate(source, url, pinned[0] if pinned else None, scan.scan(source))


def commit_html(pin):
    link = github.commit_link(pin)
    sha = github.split_raw(pin)[1][:7]
    return f'<a href="{link}">{sha}</a>' if link else f"<code>{sha}</code>"


@dataclass
class PendingUpdate:
    label: str  # имя модуля в HTML
    old: str
    candidate: Candidate

    @property
    def report(self):
        return self.candidate.report

    def diff(self):
        return list(
            difflib.unified_diff(
                self.old.splitlines(), self.candidate.source.splitlines(), "установлен", "новый", n=1, lineterm=""
            )
        )[2:]

    @property
    def stat(self):
        diff = self.diff()
        added = sum(1 for line in diff if line.startswith("+"))
        removed = sum(1 for line in diff if line.startswith("-"))
        return f"+{added} −{removed}"


class Loader(Module):
    """Установка и удаление модулей, репозитории на GitHub"""

    def _repos(self):
        return self.db.get("repos", [])

    def _trusted(self, url):
        repo = github.repo_of(url)
        return repo is not None and repo.lower() in (r.lower() for r in self._repos())

    @command("dlm", access="owner")
    async def dlm(self, message):
        """[-f] <ссылка | owner/repo/модуль | модуль> — установить модуль; -f — без подтверждения"""
        force, spec = split_force(utils.get_args_raw(message))
        if not spec:
            await utils.answer(
                message, "❌ Укажите ссылку, путь <code>owner/repo/модуль</code> или имя модуля из репозитория"
            )
            return

        repo = github.parse_repo(spec)
        if repo:
            await self._show_repo(message, repo)
            return

        url = github.to_raw_url(spec)
        if url is None and spec.startswith(("http://", "https://")):
            url = spec

        await utils.answer(message, "⏳ Загрузка...")
        data = None
        if url is None:
            url, data = await self._find_in_repos(spec)
        candidate = await fetch_candidate(url, data)
        if force or (self._trusted(url) and not candidate.report.dangerous):
            await self._install(message, candidate, force=force)
        else:
            await self._confirm(message, candidate, f"dlm -f {spec}")

    async def _find_in_repos(self, name):
        repos = self._repos()
        if not repos:
            raise LoadError("Нет подключённых репозиториев, добавьте: addrepo owner/repo")
        for repo in repos:
            url = github.module_url(repo, name)
            try:
                return url, await download.download(url)
            except LoadError:
                continue
        raise LoadError(f"Модуль {name} не найден в репозиториях: {', '.join(repos)}")

    async def _show_repo(self, message, repo):
        try:
            names = await asyncio.to_thread(github.list_modules, repo)
        except Exception as e:
            raise LoadError(f"Не удалось получить список модулей {repo}: {e}") from e
        if not names:
            await utils.answer(message, f"❌ В корне {utils.escape_html(repo)} нет .py-файлов")
            return
        prefix = utils.get_prefix(self.db.raw)
        lines = [f"<code>{prefix}dlm {utils.escape_html(repo)}/{utils.escape_html(n)}</code>" for n in names]
        await utils.answer(
            message,
            f"📦 <b>{utils.escape_html(repo)}</b> · {len(names)}\n"
            + utils.quote("\n".join(lines), expandable=len(names) > 10),
        )

    async def _repo_modules(self, repo):
        """Список модулей репозитория, кешируется на ``SEARCH_CACHE`` секунд."""
        cache = self.__dict__.setdefault("_listing", {})
        cached = cache.get(repo)
        if cached and time.monotonic() - cached[0] < SEARCH_CACHE:
            return cached[1]
        names = await asyncio.to_thread(github.list_modules, repo)
        cache[repo] = (time.monotonic(), names)
        return names

    @command("search")
    async def search(self, message):
        """<запрос> — найти модуль в подключённых репозиториях"""
        query = utils.get_args_raw(message).strip().lower()
        if not query:
            await utils.answer(message, "❌ Что искать? Например: <code>search weather</code>")
            return
        repos = self._repos()
        if not repos:
            await utils.answer(message, "❌ Нет подключённых репозиториев, добавьте: <code>addrepo owner/repo</code>")
            return

        await utils.answer(message, "⏳ Поиск...")
        words = query.split()
        found, failed = [], []
        for repo in repos:
            try:
                names = await self._repo_modules(repo)
            except Exception:
                failed.append(repo)
                continue
            found += [(repo, name) for name in names if all(word in name.lower() for word in words)]

        prefix = utils.get_prefix(self.db.raw)
        notes = f"\n<i>Не удалось получить список: {utils.escape_html(', '.join(failed))}</i>" if failed else ""
        if not found:
            await utils.answer(
                message, f"❌ Ничего не найдено по запросу <code>{utils.escape_html(query)}</code>{notes}"
            )
            return
        lines = [
            f"<code>{utils.escape_html(prefix)}dlm {utils.escape_html(repo)}/{utils.escape_html(name)}</code>"
            for repo, name in found[:SEARCH_LIMIT]
        ]
        if len(found) > SEARCH_LIMIT:
            lines.append(f"… и ещё {len(found) - SEARCH_LIMIT}")
        await utils.answer(
            message,
            f"📦 <b>Найдено</b> · {len(found)}\n" + utils.quote("\n".join(lines), expandable=len(lines) > 10) + notes,
        )

    @command("lm", access="owner")
    async def lm(self, message):
        """[-f] (ответом на файл или с файлом) — установить модуль из файла; -f — без подтверждения"""
        force, _ = split_force(utils.get_args_raw(message))
        reply = await message.get_reply_message()
        file_message = reply if reply and reply.file else message if message.file else None
        if file_message is None:
            await utils.answer(message, "❌ Ответьте на .py-файл модуля или прикрепите его")
            return
        if file_message.file.size and file_message.file.size > MAX_SIZE:
            raise LoadError("Файл модуля больше 2 МБ")
        source = download.decode(await file_message.download_media(bytes))
        origin = f"file:{file_message.file.name or 'module.py'}"
        candidate = Candidate(source, origin, None, scan.scan(source))
        if force:
            await self._install(message, candidate, force=True)
        else:
            await self._confirm(message, candidate, "lm -f")

    async def _confirm(self, message, candidate, force_hint):
        """Спросить перед установкой: источник не из подключённых репозиториев или в модуле опасный код."""
        report = candidate.report
        info = f"<b>Источник:</b> <code>{utils.escape_html(candidate.origin)}</code>\n"
        if candidate.pin:
            info += f"<b>Коммит:</b> {commit_html(candidate.pin)}\n"
        if report.declared is not None:
            info += f"<b>Права:</b> {scan.permission_names(report.declared) or 'не нужны'}\n"
        elif report.uses:
            info += f"<b>Использует:</b> {scan.permission_names(report.uses)}\n"
        info = utils.quote(info + f"<b>Строк:</b> <code>{len(candidate.source.splitlines())}</code>")
        if report.dangerous:
            text = (
                "❌ <b>Модуль может навредить аккаунту</b>\n"
                + info
                + findings_text(report)
                + "\n<i>Устанавливайте, только если доверяете автору и понимаете, зачем модулю это нужно</i>"
            )
            button = "⚠️ Установить всё равно"
        else:
            text = (
                "📦 <b>Установить модуль?</b>\n"
                + info
                + findings_text(report)
                + "\n<i>Источник не из подключённых репозиториев. Модуль получит полный доступ к аккаунту — "
                "ставьте только те, которым доверяете</i>"
            )
            button = "✅ Установить"
        if self.inline.available:
            buttons = [[{"text": button, "callback": self._install_confirmed, "args": (candidate,)}, CANCEL]]
            try:
                await self.inline.form(message, text, buttons)
                return
            except InlineError:
                pass  # например, в чате запрещены inline-боты — подтверждение командой
        prefix = utils.get_prefix(self.db.raw)
        hint = f"<code>{utils.escape_html(prefix + force_hint)}</code>"
        await utils.answer(message, text + f"\nУстановить: {hint}")

    async def _install_confirmed(self, call, candidate):
        await call.edit("⏳ Установка...", None)
        try:
            # Нажатие кнопки — явное подтверждение, в том числе для опасного кода.
            instances = await self.loader.install(candidate.source, candidate.origin, force=True, pin=candidate.pin)
        except LoadError as e:
            await call.edit(f"❌ <b>Модуль не установлен</b>\n{utils.quote(utils.escape_html(e))}")
            return
        await call.edit(self._installed_text(instances) + findings_text(candidate.report))

    async def _install(self, message, candidate, *, force=False):
        instances = await self.loader.install(candidate.source, candidate.origin, force=force, pin=candidate.pin)
        await utils.answer(message, self._installed_text(instances) + findings_text(candidate.report))

    def _installed_text(self, instances):
        prefix = utils.get_prefix(self.db.raw)
        parts = []
        for inst in instances:
            part = f"✅ Модуль <b>{utils.escape_html(inst.name)}</b> загружен"
            commands = [
                f"<code>{prefix}{cmd.name}</code> {utils.escape_html(cmd.info.doc)}".rstrip()
                for cmd in self.loader.module_commands(inst)
            ]
            if commands:
                part += "\n" + utils.quote("\n".join(commands))
            parts.append(part)
        return "\n".join(parts)

    @command("uplm", access="owner")
    async def uplm(self, message):
        """[-f] [модуль] — обновить сторонние модули: сначала изменения и подтверждение; -f — сразу"""
        force, name = split_force(utils.get_args_raw(message))
        installed = self.loader.installed()
        if name:
            inst = self.loader.get_module(name)
            if inst is None or inst.is_builtin:
                await utils.answer(message, f"❌ Нет стороннего модуля <code>{utils.escape_html(name)}</code>")
                return
            installed = {inst._stem: installed.get(inst._stem, inst._origin)}
        if not installed:
            await utils.answer(message, "📦 Сторонних модулей нет")
            return

        await utils.answer(message, "⏳ Проверяю обновления модулей...")
        names = {m._stem: m.name for m in self.loader.modules.values()}
        updates, lines, failed = [], [], False
        for stem, origin in installed.items():
            label = f"<b>{utils.escape_html(names.get(stem, stem))}</b>"
            if not origin.startswith(("http://", "https://")):
                lines.append(f"{label} — установлен из файла, пропущен")
                continue
            try:
                candidate = await fetch_candidate(origin)
            except LoadError as e:
                failed = True
                lines.append(f"{label} — ошибка: {utils.escape_html(e)}")
                continue
            path = self.loader.modules_dir / f"{stem}.py"
            old = path.read_bytes().decode("utf-8", errors="replace") if path.exists() else ""
            if old == candidate.source:
                lines.append(f"{label} — без изменений")
                continue
            updates.append(PendingUpdate(label, old, candidate))

        if not updates:
            title = "❌ <b>Не все модули проверены</b>" if failed else "✅ <b>Обновлений нет</b>"
            await utils.answer(message, title + "\n" + utils.quote("\n".join(lines), expandable=len(lines) > 10))
            return
        if force:
            await utils.answer(message, "⏳ Обновление модулей...")
            await utils.answer(message, await self._apply_updates(updates, lines, failed))
            return

        text = updates_text(updates, lines)
        dangerous = any(update.report.dangerous for update in updates)
        if self.inline.available:
            button = "⚠️ Обновить всё равно" if dangerous else "✅ Обновить"
            args = (updates, lines, failed)
            try:
                await self.inline.form(
                    message, text, [[{"text": button, "callback": self._uplm_confirmed, "args": args}, CANCEL]]
                )
                return
            except InlineError:
                pass  # например, в чате запрещены inline-боты — подтверждение командой
        hint = utils.escape_html(f"{utils.get_prefix(self.db.raw)}uplm -f {name}".rstrip())
        await utils.answer(message, text + f"\nОбновить: <code>{hint}</code>")

    async def _uplm_confirmed(self, call, updates, lines, failed):
        await call.edit("⏳ Обновление модулей...", None)
        await call.edit(await self._apply_updates(updates, lines, failed), None)

    async def _apply_updates(self, updates, lines, failed):
        """Ставит подтверждённые обновления (в том числе с опасным кодом — его пользователь видел)."""
        lines = list(lines)
        for update in updates:
            try:
                new = update.candidate
                await self.loader.install(new.source, new.origin, force=True, pin=new.pin)
            except LoadError as e:
                failed = True
                lines.append(f"{update.label} — ошибка: {utils.escape_html(e)}")
                continue
            notes = scan.summary(update.candidate.report.findings)
            lines.append(
                f"{update.label} — обновлён ({update.stat})" + (f", обратите внимание: {notes}" if notes else "")
            )
        title = "❌ <b>Не все модули обновились</b>" if failed else "✅ <b>Модули обновлены</b>"
        return title + "\n" + utils.quote("\n".join(lines), expandable=len(lines) > 10)

    @command("ulm", access="owner")
    async def ulm(self, message):
        """<модуль> — удалить модуль"""
        name = utils.get_args_raw(message).strip()
        if not name:
            await utils.answer(message, "❌ Укажите имя модуля")
            return
        inst = self.loader.get_module(name)
        if inst is not None and not inst.is_builtin and self.inline.available:
            same_file = [m.name for m in self.loader.modules.values() if m._stem == inst._stem]
            text = f"🗑 <b>Удалить {self._names(same_file)}?</b>"
            if len(same_file) > 1:
                text += "\n<i>Они в одном файле и удаляются вместе</i>"
            buttons = [[{"text": "🗑 Удалить", "callback": self._ulm_confirmed, "args": (inst.name,)}, CANCEL]]
            try:
                await self.inline.form(message, text, buttons)
                return
            except InlineError:
                pass  # например, в чате запрещены inline-боты — удаляем без подтверждения
        removed = await self.loader.uninstall(name)
        await utils.answer(message, f"🗑 Удалено: {self._names(m.name for m in removed)}")

    async def _ulm_confirmed(self, call, name):
        removed = await self.loader.uninstall(name)
        await call.edit(f"🗑 Удалено: {self._names(m.name for m in removed)}", None)

    @staticmethod
    def _names(names):
        return ", ".join(f"<b>{utils.escape_html(name)}</b>" for name in names)

    @command("reload", access="owner")
    async def reload(self, message):
        """— перезагрузить все модули"""
        await utils.answer(message, "⏳ Перезагрузка модулей...")
        await self.loader.reload_all()
        await utils.answer(
            message,
            "✅ <b>Модули перезагружены</b>\n"
            + utils.quote(
                f"Модулей: <code>{len(self.loader.modules)}</code> · команд: <code>{len(self.loader.commands)}</code>"
            ),
        )

    @command("addrepo", access="owner")
    async def addrepo(self, message):
        """<owner/repo | ссылка> — подключить репозиторий модулей с GitHub"""
        repo = github.parse_repo(utils.get_args_raw(message))
        if repo is None:
            await utils.answer(message, "❌ Нужен репозиторий: <code>owner/repo</code> или ссылка на GitHub")
            return
        repos = self._repos()
        if repo.lower() in (r.lower() for r in repos):
            await utils.answer(message, f"❌ {utils.escape_html(repo)} уже подключён")
            return
        repos.append(repo)
        self.db.set("repos", repos)
        await utils.answer(message, f"✅ Репозиторий <b>{utils.escape_html(repo)}</b> подключён")

    @command("delrepo", access="owner")
    async def delrepo(self, message):
        """<owner/repo> — отключить репозиторий"""
        repo = github.parse_repo(utils.get_args_raw(message)) or ""
        repos = self._repos()
        kept = [r for r in repos if r.lower() != repo.lower()]
        if len(kept) == len(repos):
            await utils.answer(message, "❌ Такой репозиторий не подключён")
            return
        self.db.set("repos", kept)
        await utils.answer(message, f"🗑 Репозиторий <b>{utils.escape_html(repo)}</b> отключён")

    @command("repos")
    async def repos(self, message):
        """— подключённые репозитории"""
        repos = self._repos()
        if not repos:
            await utils.answer(message, "🔗 Репозитории не подключены")
            return
        lines = [f'<a href="https://github.com/{r}">{utils.escape_html(r)}</a>' for r in repos]
        await utils.answer(message, "🔗 <b>Репозитории</b>\n" + utils.quote("\n".join(lines)))


def findings_text(report):
    """Опасное и подозрительное в модуле — блоками под основным ответом."""
    text = ""
    if report.dangerous:
        text += "\n<b>Опасное:</b>\n" + utils.quote(scan.describe(report.dangerous))
    if report.warnings:
        text += "\n<b>Обратите внимание:</b>\n" + utils.quote(
            scan.describe(report.warnings), expandable=len(report.warnings) > 5
        )
    return text


def updates_text(updates, lines):
    """Что изменится: по каждому модулю — счётчик строк, находки проверки и сама разница."""
    dangerous = any(update.report.dangerous for update in updates)
    title = "❌ <b>В обновлениях модулей опасный код</b>" if dangerous else "📦 <b>Обновить модули?</b>"
    parts, budget = [title], DIFF_BUDGET
    for update in updates:
        diff = update.diff()
        shown = "\n".join(diff[:DIFF_LINES])[:budget]
        budget -= len(shown)
        more = len(diff) - len(shown.splitlines())
        if more > 0:
            shown += f"\n… ещё {more} строк"
        commit = f" · коммит {commit_html(update.candidate.pin)}" if update.candidate.pin else ""
        parts.append(
            f"{update.label} · {update.stat}{commit}"
            + findings_text(update.report)
            + "\n"
            + utils.quote(f"<code>{utils.escape_html(shown)}</code>", expandable=True)
        )
    if lines:
        parts.append(utils.quote("\n".join(lines), expandable=len(lines) > 10))
    if dangerous:
        parts.append("<i>Обновляйте, только если доверяете автору и понимаете, зачем модулю это нужно</i>")
    return "\n".join(parts)


def split_force(raw):
    """``"-f ссылка"`` → ``(True, "ссылка")``."""
    parts = raw.strip().split(maxsplit=1)
    if parts and parts[0] == "-f":
        return True, parts[1] if len(parts) > 1 else ""
    return False, raw.strip()
