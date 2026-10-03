import asyncio
import urllib.error
import urllib.request

from uroboros import Module, command, github, utils
from uroboros.loader import LoadError

MAX_SIZE = 2 * 1024 * 1024


def _fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": "Uroboros"})
    with urllib.request.urlopen(request, timeout=30) as response:
        data = response.read(MAX_SIZE + 1)
    if len(data) > MAX_SIZE:
        raise LoadError("Файл модуля больше 2 МБ")
    return data


async def _download(url):
    try:
        return await asyncio.to_thread(_fetch, url)
    except LoadError:
        raise
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise LoadError(f"Не найдено: {url}") from e
        raise LoadError(f"Не удалось скачать {url}: HTTP {e.code}") from e
    except Exception as e:
        raise LoadError(f"Не удалось скачать {url}: {e}") from e


def _decode(data):
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        raise LoadError("Файл модуля не в UTF-8") from None


class Loader(Module):
    """Установка и удаление модулей, репозитории на GitHub"""

    def _repos(self):
        return self.db.get("repos", [])

    @command("dlm")
    async def dlm(self, message):
        """<ссылка | owner/repo/модуль | модуль> — установить модуль"""
        spec = utils.get_args_raw(message).strip()
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
            data = await _download(url)
        else:
            url, data = await self._find_in_repos(spec)
        await self._install(message, _decode(data), url)

    async def _find_in_repos(self, name):
        repos = self._repos()
        if not repos:
            raise LoadError("Нет подключённых репозиториев, добавьте: addrepo owner/repo")
        for repo in repos:
            url = github.module_url(repo, name)
            try:
                return url, await _download(url)
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

    @command("lm")
    async def lm(self, message):
        """(ответом на файл или с файлом) — установить модуль из файла"""
        reply = await message.get_reply_message()
        source = reply if reply and reply.file else message if message.file else None
        if source is None:
            await utils.answer(message, "❌ Ответьте на .py-файл модуля или прикрепите его")
            return
        if source.file.size and source.file.size > MAX_SIZE:
            raise LoadError("Файл модуля больше 2 МБ")
        data = await source.download_media(bytes)
        await self._install(message, _decode(data), f"file:{source.file.name or 'module.py'}")

    async def _install(self, message, source, origin):
        instances = await self.loader.install(source, origin)
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
        await utils.answer(message, "\n".join(parts))

    @command("uplm")
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
                source = _decode(await _download(origin))
                path = self.loader.modules_dir / f"{stem}.py"
                if path.exists() and path.read_text("utf-8") == source:
                    lines.append(f"{label} — без изменений")
                    continue
                await self.loader.install(source, origin)
                lines.append(f"{label} — обновлён")
            except LoadError as e:
                failed = True
                lines.append(f"{label} — ошибка: {utils.escape_html(e)}")

        title = "❌ <b>Не все модули обновились</b>" if failed else "✅ <b>Модули обновлены</b>"
        await utils.answer(message, title + "\n" + utils.quote("\n".join(lines), expandable=len(lines) > 10))

    @command("ulm")
    async def ulm(self, message):
        """<модуль> — удалить модуль"""
        name = utils.get_args_raw(message).strip()
        if not name:
            await utils.answer(message, "❌ Укажите имя модуля")
            return
        removed = await self.loader.uninstall(name)
        names = ", ".join(f"<b>{utils.escape_html(m.name)}</b>" for m in removed)
        await utils.answer(message, f"🗑 Удалено: {names}")

    @command("reload")
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

    @command("addrepo")
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

    @command("delrepo")
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
