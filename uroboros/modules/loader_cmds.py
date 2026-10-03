import asyncio

from uroboros import Module, command, download, github, utils
from uroboros.errors import InlineError
from uroboros.loader import LoadError

MAX_SIZE = download.MAX_SIZE
CANCEL = {"text": "Отмена", "action": "close"}


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
        if url is not None:
            data = await download.download(url)
        else:
            url, data = await self._find_in_repos(spec)
        source = download.decode(data)
        if force or self._trusted(url):
            await self._install(message, source, url)
        else:
            await self._confirm(message, source, url, f"dlm -f {spec}")

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

    @command("lm", access="owner")
    async def lm(self, message):
        """[-f] (ответом на файл или с файлом) — установить модуль из файла; -f — без подтверждения"""
        force, _ = split_force(utils.get_args_raw(message))
        reply = await message.get_reply_message()
        source = reply if reply and reply.file else message if message.file else None
        if source is None:
            await utils.answer(message, "❌ Ответьте на .py-файл модуля или прикрепите его")
            return
        if source.file.size and source.file.size > MAX_SIZE:
            raise LoadError("Файл модуля больше 2 МБ")
        data = await source.download_media(bytes)
        origin = f"file:{source.file.name or 'module.py'}"
        if force:
            await self._install(message, download.decode(data), origin)
        else:
            await self._confirm(message, download.decode(data), origin, "lm -f")

    async def _confirm(self, message, source, origin, force_hint):
        """Модуль не из подключённого репозитория: показать, откуда он и какой длины, и спросить."""
        text = (
            "📦 <b>Установить модуль?</b>\n"
            + utils.quote(
                f"<b>Источник:</b> <code>{utils.escape_html(origin)}</code>\n"
                f"<b>Строк:</b> <code>{len(source.splitlines())}</code>"
            )
            + "\n<i>Источник не из подключённых репозиториев. Модуль получит полный доступ к аккаунту — "
            "ставьте только те, которым доверяете</i>"
        )
        if self.inline.available:
            buttons = [
                [{"text": "✅ Установить", "callback": self._install_confirmed, "args": (source, origin)}, CANCEL]
            ]
            try:
                await self.inline.form(message, text, buttons)
                return
            except InlineError:
                pass  # например, в чате запрещены inline-боты — подтверждение командой
        prefix = utils.get_prefix(self.db.raw)
        hint = f"<code>{utils.escape_html(prefix + force_hint)}</code>"
        await utils.answer(message, text + f"\nУстановить: {hint}")

    async def _install_confirmed(self, call, source, origin):
        await call.edit("⏳ Установка...", None)
        try:
            instances = await self.loader.install(source, origin)
        except LoadError as e:
            await call.edit(f"❌ <b>Модуль не установлен</b>\n{utils.quote(utils.escape_html(e))}")
            return
        await call.edit(self._installed_text(instances))

    async def _install(self, message, source, origin):
        instances = await self.loader.install(source, origin)
        await utils.answer(message, self._installed_text(instances))

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
        """[модуль] — обновить сторонние модули из источника"""
        name = utils.get_args_raw(message).strip()
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

        await utils.answer(message, "⏳ Обновление модулей...")
        names = {m._stem: m.name for m in self.loader.modules.values()}
        lines, failed = [], False
        for stem, origin in installed.items():
            label = f"<b>{utils.escape_html(names.get(stem, stem))}</b>"
            if not origin.startswith(("http://", "https://")):
                lines.append(f"{label} — установлен из файла, пропущен")
                continue
            try:
                source = download.decode(await download.download(origin))
                path = self.loader.modules_dir / f"{stem}.py"
                if path.exists() and path.read_bytes() == source.encode("utf-8"):
                    lines.append(f"{label} — без изменений")
                    continue
                await self.loader.install(source, origin)
                lines.append(f"{label} — обновлён")
            except LoadError as e:
                failed = True
                lines.append(f"{label} — ошибка: {utils.escape_html(e)}")

        title = "❌ <b>Не все модули обновились</b>" if failed else "✅ <b>Модули обновлены</b>"
        await utils.answer(message, title + "\n" + utils.quote("\n".join(lines), expandable=len(lines) > 10))

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


def split_force(raw):
    """``"-f ссылка"`` → ``(True, "ссылка")``."""
    parts = raw.strip().split(maxsplit=1)
    if parts and parts[0] == "-f":
        return True, parts[1] if len(parts) > 1 else ""
    return False, raw.strip()
