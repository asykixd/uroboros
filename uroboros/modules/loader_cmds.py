import asyncio
import difflib
import time
from dataclasses import dataclass, field

from uroboros import Module, command, download, github, scan, utils
from uroboros.errors import InlineError
from uroboros.loader import LoadError, same_module_url

MAX_SIZE = download.MAX_SIZE
SEARCH_CACHE = 600
SEARCH_LIMIT = 30
DEFAULT_REPOS = ("asykixd/uroboros-modules",)  # official modules: connected until the user removes them
DIFF_LINES = 40  # diff lines per module
DIFF_BUDGET = 2500  # diff characters for the whole message: it must fit into 4096 with everything else


@dataclass
class Candidate:
    """A downloaded module that isn't installed yet."""

    source: str
    origin: str  # where updates come from
    pin: str | None  # the same version at a specific commit (GitHub)
    report: scan.Report
    deps: list["Candidate"] = field(default_factory=list)  # from # requires_module:, deepest first

    @property
    def everything(self):
        """Dependencies and the module itself, in install order."""
        return [*self.deps, self]


async def resolve_deps(loader, candidate, strings):
    """Downloads missing modules from ``# requires_module:`` (and their dependencies); a cycle is an error."""
    ordered, seen = [], []

    async def visit(current, path):
        for url in loader.missing_modules(current.source):
            if any(same_module_url(url, step) for step in path):
                raise LoadError(strings("cycle", chain=" → ".join([*path, url])))
            if any(same_module_url(url, done) for done in seen):
                continue
            seen.append(url)
            dep = await fetch_candidate(url)
            await visit(dep, [*path, url])
            ordered.append(dep)

    await visit(candidate, [candidate.origin])
    candidate.deps = ordered
    return candidate


async def fetch_candidate(url, data=None):
    """Downloads a module; from GitHub by a commit link, to know which version is installed."""
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
    label: str  # module name as HTML
    old: str
    candidate: Candidate

    @property
    def report(self):
        return self.candidate.report

    def diff(self):
        return list(
            difflib.unified_diff(
                self.old.splitlines(), self.candidate.source.splitlines(), "installed", "new", n=1, lineterm=""
            )
        )[2:]

    @property
    def stat(self):
        diff = self.diff()
        added = sum(1 for line in diff if line.startswith("+"))
        removed = sum(1 for line in diff if line.startswith("-"))
        return f"+{added} −{removed}"


class Loader(Module):
    """Install and remove modules, GitHub repos"""

    strings = {
        "cycle": "Circular module dependency: {chain}",
        "cancel": "✖️ Cancel",
        "which_module": "❌ <b>Which module to install?</b>",
        "by_link": "🔗 a link to the file",
        "by_path": "📁 a path <code>owner/repo/module</code>",
        "by_name": "🏷 a module name from connected repos",
        "downloading": "⏳ <b>Downloading the module...</b>",
        "no_repos_error": "No connected repos, add one: addrepo owner/repo",
        "not_in_repos": "Module {name} not found in repos: {repos}",
        "list_failed": "Couldn't list the modules of {repo}: {error}",
        "repo_empty": "❌ <b>No modules in the root of {repo}</b>",
        "repo_title": '📚 <b><a href="https://github.com/{repo}">{repo}</a></b> · modules: {count}',
        "tap_to_copy": "tap a command to copy it",
        "what_to_search": "❌ <b>What to search for?</b>",
        "search_example": "for example: <code>search weather</code>",
        "no_repos": "❌ <b>No connected repos</b>",
        "add_repo_hint": "add one: <code>addrepo owner/repo</code>",
        "searching": "🔎 <b>Searching modules...</b>",
        "list_failed_note": "\n⚠️ <i>Couldn't get the list: {repos}</i>",
        "nothing_found": "🔎 <b>Nothing found</b> for <code>{query}</code>",
        "and_more": "… and {count} more",
        "found": "🔎 <b>Found</b> · {count}",
        "reply_to_file": "❌ <b>Reply to a module .py file</b> or attach it to the command",
        "file_too_big": "The module file is larger than 2 MB",
        "source": "🔗 Source: <code>{origin}</code>",
        "commit": "📌 Commit: {commit}",
        "permissions": "🔐 Permissions: {names}",
        "not_needed": "none needed",
        "uses": "🧰 Uses: {names}",
        "lines": "📏 Lines: <code>{count}</code>",
        "deps": "🧩 Dependencies: <code>{count}</code> — installed together with the module",
        "harmful": "🚨 <b>The module may harm the account</b>",
        "harmful_hint": "💡 <i>Install only if you trust the author and understand why the module needs this</i>",
        "install_anyway": "⚠️ Install anyway",
        "install_question": "📦 <b>Install the module?</b>",
        "install_hint": (
            "💡 <i>The source isn't a connected repo. The module gets full access to the account — "
            "install only ones you trust</i>"
        ),
        "install": "📥 Install",
        "install_command": "\n📥 Install: <code>{command}</code>",
        "installing": "⏳ <b>Installing the module...</b>",
        "not_installed": "❌ <b>Module not installed</b>",
        "loaded": "✅ <b>Module {name} loaded</b>",
        "no_external": "❌ <b>No third-party module</b> <code>{name}</code>",
        "no_externals": "📦 <b>No third-party modules</b>",
        "checking": "⏳ <b>Checking module updates...</b>",
        "from_file": "📎 {label} — installed from a file, skipped",
        "error_line": "❌ {label} — error: {error}",
        "unchanged": "➖ {label} — unchanged",
        "not_all_checked": "❌ <b>Not all modules were checked</b>",
        "no_updates": "✅ <b>No updates</b>",
        "updating": "⏳ <b>Updating modules...</b>",
        "update_anyway": "⚠️ Update anyway",
        "update": "🔃 Update",
        "update_command": "\n🔃 Update: <code>{command}</code>",
        "updated_line": "✅ {label} — updated ({stat})",
        "updated_note": ", note: {notes}",
        "not_all_updated": "❌ <b>Not all modules were updated</b>",
        "updated": "✅ <b>Modules updated</b>",
        "which_remove": "❌ <b>Which module to remove?</b>",
        "remove_question": "🗑 <b>Remove {names}?</b>",
        "same_file": "\n💡 <i>They are in one file and are removed together</i>",
        "remove": "🗑 Remove",
        "removed": "🗑 <b>Removed:</b> {names}",
        "reloading": "⏳ <b>Reloading modules...</b>",
        "reloaded": "✅ <b>Modules reloaded</b>",
        "counts": "📦 Modules: <code>{modules}</code> · commands: <code>{commands}</code>",
        "which_repo": "❌ <b>Which repo?</b>",
        "repo_usage": "<code>owner/repo</code> or a GitHub link",
        "repo_connected_already": "🔗 <b>{repo}</b> is already connected",
        "repo_connected": "🔗 <b>Repo {repo} connected</b>",
        "repo_connected_hint": (
            "its modules: <code>{prefix}dlm {repo}</code>, install by name: <code>{prefix}dlm module</code>"
        ),
        "repo_not_connected": "❌ <b>This repo isn't connected</b>",
        "repo_removed": "✂️ <b>Repo {repo} disconnected</b>",
        "no_repos_title": "📚 <b>No repos connected</b>",
        "repos": "📚 <b>Repos</b> · {count}",
        "dangerous": "🚨 <b>Dangerous</b>",
        "notice": "⚠️ <b>Note</b>",
        "dependency": "🧩 <b>Dependency</b> <code>{origin}</code>",
        "dangerous_updates": "🚨 <b>Dangerous code in module updates</b>",
        "update_question": "🔃 <b>Update modules?</b>",
        "more_lines": "\n… {count} more lines",
        "update_hint": "💡 <i>Update only if you trust the author and understand why the module needs this</i>",
    }
    strings_ru = {
        "_cls_doc": "Установка и удаление модулей, репозитории на GitHub",
        "_cmd_doc_dlm": "[-f] <ссылка | owner/repo/модуль | модуль> — установить модуль; -f — без подтверждения",
        "_cmd_doc_search": "<запрос> — найти модуль в подключённых репозиториях",
        "_cmd_doc_lm": "[-f] (ответом на файл или с файлом) — установить модуль из файла; -f — без подтверждения",
        "_cmd_doc_uplm": "[-f] [модуль] — обновить сторонние модули: сначала изменения и подтверждение; -f — сразу",
        "_cmd_doc_ulm": "<модуль> — удалить модуль",
        "_cmd_doc_reload": "— перезагрузить все модули",
        "_cmd_doc_addrepo": "<owner/repo | ссылка> — подключить репозиторий модулей с GitHub",
        "_cmd_doc_delrepo": "<owner/repo> — отключить репозиторий",
        "_cmd_doc_repos": "— подключённые репозитории",
        "cycle": "Циклическая зависимость модулей: {chain}",
        "cancel": "✖️ Отмена",
        "which_module": "❌ <b>Какой модуль установить?</b>",
        "by_link": "🔗 ссылка на файл",
        "by_path": "📁 путь <code>owner/repo/модуль</code>",
        "by_name": "🏷 имя модуля из подключённых репозиториев",
        "downloading": "⏳ <b>Скачиваю модуль...</b>",
        "no_repos_error": "Нет подключённых репозиториев, добавьте: addrepo owner/repo",
        "not_in_repos": "Модуль {name} не найден в репозиториях: {repos}",
        "list_failed": "Не удалось получить список модулей {repo}: {error}",
        "repo_empty": "❌ <b>В корне {repo} нет модулей</b>",
        "repo_title": '📚 <b><a href="https://github.com/{repo}">{repo}</a></b> · модулей: {count}',
        "tap_to_copy": "нажмите на команду, чтобы скопировать",
        "what_to_search": "❌ <b>Что искать?</b>",
        "search_example": "например: <code>search weather</code>",
        "no_repos": "❌ <b>Нет подключённых репозиториев</b>",
        "add_repo_hint": "добавьте: <code>addrepo owner/repo</code>",
        "searching": "🔎 <b>Ищу модули...</b>",
        "list_failed_note": "\n⚠️ <i>Не удалось получить список: {repos}</i>",
        "nothing_found": "🔎 <b>Ничего не нашлось</b> по запросу <code>{query}</code>",
        "and_more": "… и ещё {count}",
        "found": "🔎 <b>Найдено</b> · {count}",
        "reply_to_file": "❌ <b>Ответьте на .py-файл модуля</b> или прикрепите его к команде",
        "file_too_big": "Файл модуля больше 2 МБ",
        "source": "🔗 Источник: <code>{origin}</code>",
        "commit": "📌 Коммит: {commit}",
        "permissions": "🔐 Права: {names}",
        "not_needed": "не нужны",
        "uses": "🧰 Использует: {names}",
        "lines": "📏 Строк: <code>{count}</code>",
        "deps": "🧩 Зависимостей: <code>{count}</code> — установятся вместе с модулем",
        "harmful": "🚨 <b>Модуль может навредить аккаунту</b>",
        "harmful_hint": "💡 <i>Устанавливайте, только если доверяете автору и понимаете, зачем модулю это нужно</i>",
        "install_anyway": "⚠️ Установить всё равно",
        "install_question": "📦 <b>Установить модуль?</b>",
        "install_hint": (
            "💡 <i>Источник не из подключённых репозиториев. Модуль получит полный доступ к аккаунту — "
            "ставьте только те, которым доверяете</i>"
        ),
        "install": "📥 Установить",
        "install_command": "\n📥 Установить: <code>{command}</code>",
        "installing": "⏳ <b>Устанавливаю модуль...</b>",
        "not_installed": "❌ <b>Модуль не установлен</b>",
        "loaded": "✅ <b>Модуль {name} загружен</b>",
        "no_external": "❌ <b>Нет стороннего модуля</b> <code>{name}</code>",
        "no_externals": "📦 <b>Сторонних модулей нет</b>",
        "checking": "⏳ <b>Проверяю обновления модулей...</b>",
        "from_file": "📎 {label} — установлен из файла, пропущен",
        "error_line": "❌ {label} — ошибка: {error}",
        "unchanged": "➖ {label} — без изменений",
        "not_all_checked": "❌ <b>Не все модули проверены</b>",
        "no_updates": "✅ <b>Обновлений нет</b>",
        "updating": "⏳ <b>Обновляю модули...</b>",
        "update_anyway": "⚠️ Обновить всё равно",
        "update": "🔃 Обновить",
        "update_command": "\n🔃 Обновить: <code>{command}</code>",
        "updated_line": "✅ {label} — обновлён ({stat})",
        "updated_note": ", обратите внимание: {notes}",
        "not_all_updated": "❌ <b>Не все модули обновились</b>",
        "updated": "✅ <b>Модули обновлены</b>",
        "which_remove": "❌ <b>Какой модуль удалить?</b>",
        "remove_question": "🗑 <b>Удалить {names}?</b>",
        "same_file": "\n💡 <i>Они в одном файле и удаляются вместе</i>",
        "remove": "🗑 Удалить",
        "removed": "🗑 <b>Удалено:</b> {names}",
        "reloading": "⏳ <b>Перезагружаю модули...</b>",
        "reloaded": "✅ <b>Модули перезагружены</b>",
        "counts": "📦 Модулей: <code>{modules}</code> · команд: <code>{commands}</code>",
        "which_repo": "❌ <b>Какой репозиторий?</b>",
        "repo_usage": "<code>owner/repo</code> или ссылка на GitHub",
        "repo_connected_already": "🔗 <b>{repo}</b> уже подключён",
        "repo_connected": "🔗 <b>Репозиторий {repo} подключён</b>",
        "repo_connected_hint": (
            "его модули: <code>{prefix}dlm {repo}</code>, установка по имени: <code>{prefix}dlm модуль</code>"
        ),
        "repo_not_connected": "❌ <b>Такой репозиторий не подключён</b>",
        "repo_removed": "✂️ <b>Репозиторий {repo} отключён</b>",
        "no_repos_title": "📚 <b>Репозитории не подключены</b>",
        "repos": "📚 <b>Репозитории</b> · {count}",
        "dangerous": "🚨 <b>Опасное</b>",
        "notice": "⚠️ <b>Обратите внимание</b>",
        "dependency": "🧩 <b>Зависимость</b> <code>{origin}</code>",
        "dangerous_updates": "🚨 <b>В обновлениях модулей опасный код</b>",
        "update_question": "🔃 <b>Обновить модули?</b>",
        "more_lines": "\n… ещё {count} строк",
        "update_hint": "💡 <i>Обновляйте, только если доверяете автору и понимаете, зачем модулю это нужно</i>",
    }

    @property
    def _cancel(self):
        return {"text": self.strings("cancel"), "action": "close"}

    def _prefix(self):
        return utils.get_prefix(self.db.raw)

    def _repos(self):
        return self.db.get("repos", list(DEFAULT_REPOS))

    def _trusted(self, url):
        repo = github.repo_of(url)
        return repo is not None and repo.lower() in (r.lower() for r in self._repos())

    @command("dlm", access="owner", emoji="📥")
    async def dlm(self, message):
        """[-f] <link | owner/repo/module | module> — install a module; -f — without confirmation"""
        force, spec = split_force(utils.get_args_raw(message))
        if not spec:
            await utils.answer(
                message,
                utils.card(
                    self.strings("which_module"),
                    [self.strings("by_link"), self.strings("by_path"), self.strings("by_name")],
                ),
            )
            return

        repo = github.parse_repo(spec)
        if repo:
            await self._show_repo(message, repo)
            return

        url = github.to_raw_url(spec)
        if url is None and spec.startswith(("http://", "https://")):
            url = spec

        await utils.answer(message, self.strings("downloading"))
        data = None
        if url is None:
            url, data = await self._find_in_repos(spec)
        candidate = await resolve_deps(self.loader, await fetch_candidate(url, data), self.strings)
        if force or all(self._trusted(c.origin) and not c.report.dangerous for c in candidate.everything):
            await self._install(message, candidate, force=force)
        else:
            await self._confirm(message, candidate, f"dlm -f {spec}")

    async def _find_in_repos(self, name):
        repos = self._repos()
        if not repos:
            raise LoadError(self.strings["no_repos_error"])
        for repo in repos:
            url = github.module_url(repo, name)
            try:
                return url, await download.download(url)
            except LoadError:
                continue
        raise LoadError(self.strings["not_in_repos"].format(name=name, repos=", ".join(repos)))

    async def _show_repo(self, message, repo):
        try:
            names = await asyncio.to_thread(github.list_modules, repo)
        except Exception as e:
            raise LoadError(self.strings["list_failed"].format(repo=repo, error=e)) from e
        if not names:
            await utils.answer(message, self.strings("repo_empty", repo=repo))
            return
        prefix = utils.escape_html(self._prefix())
        lines = [f"▸ <code>{prefix}dlm {utils.escape_html(repo)}/{utils.escape_html(n)}</code>" for n in names]
        await utils.answer(
            message,
            utils.card(
                self.strings("repo_title", repo=repo, count=len(names)),
                lines,
                hint=self.strings("tap_to_copy"),
                expandable=len(names) > 10,
            ),
        )

    async def _repo_modules(self, repo):
        """A repo's module list, cached for ``SEARCH_CACHE`` seconds."""
        cache = self.__dict__.setdefault("_listing", {})
        cached = cache.get(repo)
        if cached and time.monotonic() - cached[0] < SEARCH_CACHE:
            return cached[1]
        names = await asyncio.to_thread(github.list_modules, repo)
        cache[repo] = (time.monotonic(), names)
        return names

    @command("search", emoji="🔎")
    async def search(self, message):
        """<query> — find a module in connected repos"""
        query = utils.get_args_raw(message).strip().lower()
        if not query:
            await utils.answer(message, utils.card(self.strings("what_to_search"), hint=self.strings("search_example")))
            return
        repos = self._repos()
        if not repos:
            await utils.answer(message, utils.card(self.strings("no_repos"), hint=self.strings("add_repo_hint")))
            return

        await utils.answer(message, self.strings("searching"))
        words = query.split()
        found, failed = [], []
        for repo in repos:
            try:
                names = await self._repo_modules(repo)
            except Exception:
                failed.append(repo)
                continue
            found += [(repo, name) for name in names if all(word in name.lower() for word in words)]

        prefix = self._prefix()
        notes = self.strings("list_failed_note", repos=", ".join(failed)) if failed else ""
        if not found:
            await utils.answer(message, self.strings("nothing_found", query=query) + notes)
            return
        lines = [
            f"▸ <code>{utils.escape_html(prefix)}dlm {utils.escape_html(repo)}/{utils.escape_html(name)}</code>"
            for repo, name in found[:SEARCH_LIMIT]
        ]
        if len(found) > SEARCH_LIMIT:
            lines.append(self.strings("and_more", count=len(found) - SEARCH_LIMIT))
        await utils.answer(
            message,
            utils.card(self.strings("found", count=len(found)), lines, expandable=len(lines) > 10) + notes,
        )

    @command("lm", access="owner", emoji="📎")
    async def lm(self, message):
        """[-f] (reply to a file or with a file) — install a module from a file; -f — without confirmation"""
        force, _ = split_force(utils.get_args_raw(message))
        reply = await message.get_reply_message()
        file_message = reply if reply and reply.file else message if message.file else None
        if file_message is None:
            await utils.answer(message, self.strings("reply_to_file"))
            return
        if file_message.file.size and file_message.file.size > MAX_SIZE:
            raise LoadError(self.strings["file_too_big"])
        source = download.decode(await file_message.download_media(bytes))
        origin = f"file:{file_message.file.name or 'module.py'}"
        candidate = await resolve_deps(self.loader, Candidate(source, origin, None, scan.scan(source)), self.strings)
        if force:
            await self._install(message, candidate, force=True)
        else:
            await self._confirm(message, candidate, "lm -f")

    async def _confirm(self, message, candidate, force_hint):
        """Ask before installing: the source isn't a connected repo or the module has dangerous code."""
        report = candidate.report
        info = [self.strings("source", origin=candidate.origin)]
        if candidate.pin:
            info.append(self.strings("commit", commit=utils.Html(commit_html(candidate.pin))))
        if report.declared is not None:
            names = scan.permission_names(report.declared) or self.strings("not_needed")
            info.append(self.strings("permissions", names=utils.Html(names)))
        elif report.uses:
            info.append(self.strings("uses", names=utils.Html(scan.permission_names(report.uses))))
        info.append(self.strings("lines", count=len(candidate.source.splitlines())))
        if candidate.deps:
            info.append(self.strings("deps", count=len(candidate.deps)))
        details = findings_text(report, self.strings) + deps_text(candidate.deps, self.strings)
        if any(c.report.dangerous for c in candidate.everything):
            text = utils.card(self.strings("harmful"), info) + details + "\n" + self.strings("harmful_hint")
            button = self.strings("install_anyway")
        else:
            text = utils.card(self.strings("install_question"), info) + details + "\n" + self.strings("install_hint")
            button = self.strings("install")
        if self.inline.available:
            buttons = [[{"text": button, "callback": self._install_confirmed, "args": (candidate,)}, self._cancel]]
            try:
                await self.inline.form(message, text, buttons)
                return
            except InlineError:
                pass  # e.g. inline bots are banned in this chat: confirm with a command
        await utils.answer(message, text + self.strings("install_command", command=self._prefix() + force_hint))

    async def _install_confirmed(self, call, candidate):
        await call.edit(self.strings("installing"), None)
        try:
            # Pressing the button is explicit confirmation, dangerous code included (dependencies were shown too).
            instances = await self._install_all(candidate, force=True)
        except LoadError as e:
            await call.edit(utils.card(self.strings("not_installed"), utils.escape_html(e)))
            return
        await call.edit(self._installed_text(instances) + findings_text(candidate.report, self.strings))

    async def _install(self, message, candidate, *, force=False):
        instances = await self._install_all(candidate, force=force)
        await utils.answer(message, self._installed_text(instances) + findings_text(candidate.report, self.strings))

    async def _install_all(self, candidate, *, force):
        """Dependencies first, then the module: the core won't install a module before them."""
        instances = []
        for item in candidate.everything:
            instances += await self.loader.install(item.source, item.origin, force=force, pin=item.pin)
        return instances

    def _installed_text(self, instances):
        prefix = utils.escape_html(self._prefix())
        parts = []
        for inst in instances:
            commands = [
                f"{cmd.info.emoji or '▸'} <code>{prefix}{cmd.name}</code> "
                f"{utils.escape_html(self.loader.command_doc(cmd))}".rstrip()
                for cmd in self.loader.module_commands(inst)
            ]
            parts.append(utils.card(self.strings("loaded", name=inst.name), commands or None))
        return "\n".join(parts)

    @command("uplm", access="owner", emoji="🔃")
    async def uplm(self, message):
        """[-f] [module] — update third-party modules: changes and confirmation first; -f — right away"""
        force, name = split_force(utils.get_args_raw(message))
        installed = self.loader.installed()
        if name:
            inst = self.loader.get_module(name)
            if inst is None or inst.is_builtin:
                await utils.answer(message, self.strings("no_external", name=name))
                return
            installed = {inst._stem: installed.get(inst._stem, inst._origin)}
        if not installed:
            await utils.answer(message, self.strings("no_externals"))
            return

        await utils.answer(message, self.strings("checking"))
        names = {m._stem: m.name for m in self.loader.modules.values()}
        updates, lines, failed = [], [], False
        for stem, origin in installed.items():
            label = utils.Html(f"<b>{utils.escape_html(names.get(stem, stem))}</b>")
            if not origin.startswith(("http://", "https://")):
                lines.append(self.strings("from_file", label=label))
                continue
            try:
                candidate = await fetch_candidate(origin)
            except LoadError as e:
                failed = True
                lines.append(self.strings("error_line", label=label, error=e))
                continue
            path = self.loader.modules_dir / f"{stem}.py"
            old = path.read_bytes().decode("utf-8", errors="replace") if path.exists() else ""
            if old == candidate.source:
                lines.append(self.strings("unchanged", label=label))
                continue
            updates.append(PendingUpdate(label, old, candidate))

        if not updates:
            title = self.strings("not_all_checked") if failed else self.strings("no_updates")
            await utils.answer(message, title + "\n" + utils.quote("\n".join(lines), expandable=len(lines) > 10))
            return
        if force:
            await utils.answer(message, self.strings("updating"))
            await utils.answer(message, await self._apply_updates(updates, lines, failed))
            return

        text = updates_text(updates, lines, self.strings)
        dangerous = any(update.report.dangerous for update in updates)
        if self.inline.available:
            button = self.strings("update_anyway") if dangerous else self.strings("update")
            args = (updates, lines, failed)
            try:
                await self.inline.form(
                    message, text, [[{"text": button, "callback": self._uplm_confirmed, "args": args}, self._cancel]]
                )
                return
            except InlineError:
                pass  # e.g. inline bots are banned in this chat: confirm with a command
        hint = f"{self._prefix()}uplm -f {name}".rstrip()
        await utils.answer(message, text + self.strings("update_command", command=hint))

    async def _uplm_confirmed(self, call, updates, lines, failed):
        await call.edit(self.strings("updating"), None)
        await call.edit(await self._apply_updates(updates, lines, failed), None)

    async def _apply_updates(self, updates, lines, failed):
        """Installs confirmed updates (dangerous code included: the user has seen it)."""
        lines = list(lines)
        for update in updates:
            try:
                new = update.candidate
                await self.loader.install(new.source, new.origin, force=True, pin=new.pin)
            except LoadError as e:
                failed = True
                lines.append(self.strings("error_line", label=utils.Html(update.label), error=e))
                continue
            notes = scan.summary(update.candidate.report.findings)
            lines.append(
                self.strings("updated_line", label=utils.Html(update.label), stat=update.stat)
                + (self.strings("updated_note", notes=utils.Html(notes)) if notes else "")
            )
        title = self.strings("not_all_updated") if failed else self.strings("updated")
        return title + "\n" + utils.quote("\n".join(lines), expandable=len(lines) > 10)

    @command("ulm", access="owner", emoji="🗑")
    async def ulm(self, message):
        """<module> — remove a module"""
        name = utils.get_args_raw(message).strip()
        if not name:
            await utils.answer(message, self.strings("which_remove"))
            return
        inst = self.loader.get_module(name)
        if inst is not None and not inst.is_builtin and self.inline.available:
            same_file = [m.name for m in self.loader.modules.values() if m._stem == inst._stem]
            text = self.strings("remove_question", names=utils.Html(self._names(same_file)))
            if len(same_file) > 1:
                text += self.strings("same_file")
            remove = {"text": self.strings("remove"), "callback": self._ulm_confirmed, "args": (inst.name,)}
            try:
                await self.inline.form(message, text, [[remove, self._cancel]])
                return
            except InlineError:
                pass  # e.g. inline bots are banned in this chat: remove without confirmation
        removed = await self.loader.uninstall(name)
        await utils.answer(message, self._removed(removed))

    async def _ulm_confirmed(self, call, name):
        removed = await self.loader.uninstall(name)
        await call.edit(self._removed(removed), None)

    def _removed(self, removed):
        return self.strings("removed", names=utils.Html(self._names(m.name for m in removed)))

    @staticmethod
    def _names(names):
        return ", ".join(f"<b>{utils.escape_html(name)}</b>" for name in names)

    @command("reload", access="owner", emoji="🔁")
    async def reload(self, message):
        """— reload all modules"""
        await utils.answer(message, self.strings("reloading"))
        await self.loader.reload_all()
        await utils.answer(
            message,
            utils.card(
                self.strings("reloaded"),
                self.strings("counts", modules=len(self.loader.modules), commands=len(self.loader.commands)),
            ),
        )

    @command("addrepo", access="owner", emoji="🔗")
    async def addrepo(self, message):
        """<owner/repo | link> — connect a GitHub module repo"""
        repo = github.parse_repo(utils.get_args_raw(message))
        if repo is None:
            await utils.answer(message, utils.card(self.strings("which_repo"), hint=self.strings("repo_usage")))
            return
        repos = self._repos()
        if repo.lower() in (r.lower() for r in repos):
            await utils.answer(message, self.strings("repo_connected_already", repo=repo))
            return
        repos.append(repo)
        self.db.set("repos", repos)
        await utils.answer(
            message,
            utils.card(
                self.strings("repo_connected", repo=repo),
                hint=self.strings("repo_connected_hint", prefix=self._prefix(), repo=repo),
            ),
        )

    @command("delrepo", access="owner", emoji="✂️")
    async def delrepo(self, message):
        """<owner/repo> — disconnect a repo"""
        repo = github.parse_repo(utils.get_args_raw(message)) or ""
        repos = self._repos()
        kept = [r for r in repos if r.lower() != repo.lower()]
        if len(kept) == len(repos):
            await utils.answer(message, self.strings("repo_not_connected"))
            return
        self.db.set("repos", kept)
        await utils.answer(message, self.strings("repo_removed", repo=repo))

    @command("repos", emoji="📚")
    async def repos(self, message):
        """— connected repos"""
        repos = self._repos()
        if not repos:
            await utils.answer(message, utils.card(self.strings("no_repos_title"), hint=self.strings("add_repo_hint")))
            return
        lines = [f'▸ <a href="https://github.com/{r}">{utils.escape_html(r)}</a>' for r in repos]
        await utils.answer(message, utils.card(self.strings("repos", count=len(repos)), lines))


def findings_text(report, strings):
    """Dangerous and suspicious findings, as blocks under the main reply."""
    text = ""
    if report.dangerous:
        text += f"\n{strings('dangerous')}\n" + utils.quote(scan.describe(report.dangerous))
    if report.warnings:
        text += f"\n{strings('notice')}\n" + utils.quote(
            scan.describe(report.warnings), expandable=len(report.warnings) > 5
        )
    return text


def deps_text(deps, strings):
    """Dependencies from ``# requires_module:``: where from and what the scan found in them."""
    text = ""
    for dep in deps:
        text += "\n" + strings("dependency", origin=dep.origin) + findings_text(dep.report, strings)
    return text


def updates_text(updates, lines, strings):
    """What will change: per module, line counts, scan findings and the diff itself."""
    dangerous = any(update.report.dangerous for update in updates)
    parts, budget = [strings("dangerous_updates") if dangerous else strings("update_question")], DIFF_BUDGET
    for update in updates:
        diff = update.diff()
        shown = "\n".join(diff[:DIFF_LINES])[:budget]
        budget -= len(shown)
        more = len(diff) - len(shown.splitlines())
        if more > 0:
            shown += strings["more_lines"].format(count=more)
        commit = f" · 📌 {commit_html(update.candidate.pin)}" if update.candidate.pin else ""
        parts.append(
            f"🧩 {update.label} · {update.stat}{commit}"
            + findings_text(update.report, strings)
            + "\n"
            + utils.quote(f"<code>{utils.escape_html(shown)}</code>", expandable=True)
        )
    if lines:
        parts.append(utils.quote("\n".join(lines), expandable=len(lines) > 10))
    if dangerous:
        parts.append(strings("update_hint"))
    return "\n".join(parts)


def split_force(raw):
    """``"-f link"`` → ``(True, "link")``."""
    parts = raw.strip().split(maxsplit=1)
    if parts and parts[0] == "-f":
        return True, parts[1] if len(parts) > 1 else ""
    return False, raw.strip()
