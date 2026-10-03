from uroboros import Module, ModuleConfig, command, utils, validators
from uroboros.errors import InlineError
from uroboros.validators import ValidationError

ROW_SIZE = 3
CLOSE = {"text": "✖ Закрыть", "action": "close"}


class Config(Module):
    """Настройки модулей"""

    def _configurable(self):
        return [m for m in self.loader.modules.values() if isinstance(m.config, ModuleConfig) and len(m.config)]

    @command("cfg", aliases=["config"], access="owner")
    async def cfg(self, message):
        """[модуль] [ключ] [значение] — посмотреть или изменить настройки"""
        raw = utils.get_args_raw(message).strip()
        parts = raw.split(maxsplit=2)

        if len(parts) < 3 and self.inline.available:
            view = self._inline_view(parts)
            if view is not None:
                try:
                    await self.inline.form(message, *view)
                    return
                except InlineError:
                    pass  # например, в чате запрещены inline-боты — покажем текстом

        if not parts:
            names = ", ".join(f"<b>{utils.escape_html(m.name)}</b>" for m in self._configurable())
            await utils.answer(message, f"⚙️ <b>Модули с настройками:</b> {names or 'нет'}")
            return

        module = self.loader.get_module(parts[0])
        if module is None or not isinstance(module.config, ModuleConfig):
            await utils.answer(message, "❌ У этого модуля нет настроек")
            return
        config = module.config

        if len(parts) == 1:
            items = "\n\n".join(self._describe(config, key) for key in config)
            await utils.answer(message, f"⚙️ <b>{utils.escape_html(module.name)}</b>\n" + utils.quote(items))
            return

        key = parts[1]
        if key not in config:
            await utils.answer(message, f"❌ Нет ключа <code>{utils.escape_html(key)}</code>")
            return

        if len(parts) == 2:
            await utils.answer(message, "⚙️ " + utils.quote(self._describe(config, key)))
            return

        try:
            config[key] = parts[2]
        except ValidationError as e:
            await utils.answer(message, f"❌ {utils.escape_html(e)}")
            return
        await utils.answer(message, "✅ <b>Сохранено</b>\n" + utils.quote(self._describe(config, key)))

    @command("rcfg", access="owner")
    async def rcfg(self, message):
        """<модуль> <ключ> — сбросить настройку на значение по умолчанию"""
        parts = utils.get_args(message)
        module = self.loader.get_module(parts[0]) if parts else None
        if len(parts) != 2 or module is None or not isinstance(module.config, ModuleConfig):
            await utils.answer(message, "❌ Использование: <code>rcfg модуль ключ</code>")
            return
        if parts[1] not in module.config:
            await utils.answer(message, "❌ Нет такого ключа")
            return
        module.config.reset(parts[1])
        await utils.answer(message, "✅ <b>Сброшено</b>\n" + utils.quote(self._describe(module.config, parts[1])))

    @staticmethod
    def _describe(config, key):
        value = config.value(key)
        text = f"<code>{utils.escape_html(key)}</code> = <code>{utils.escape_html(repr(config[key]))}</code>"
        hints = [h for h in (value.doc, getattr(value.validator, "doc", "")) if h]
        if hints:
            text += f"\n<i>{utils.escape_html(' · '.join(hints))}</i>"
        return text

    # --- inline: модули → ключи → значение ---

    def _inline_view(self, parts):
        """Форма для ``.cfg``, ``.cfg модуль`` и ``.cfg модуль ключ``; None — ответить текстом (ошибка в имени)."""
        if not parts:
            return self._root_view()
        module = self.loader.get_module(parts[0])
        if module is None or not isinstance(module.config, ModuleConfig):
            return None
        if len(parts) == 1:
            return self._module_view(module)
        if parts[1] not in module.config:
            return None
        return self._key_view(module, parts[1])

    def _root_view(self):
        modules = sorted(self._configurable(), key=lambda m: m.name.lower())
        if not modules:
            return "⚙️ <b>Модулей с настройками нет</b>", [[CLOSE]]
        names = [{"text": m.name, "callback": self._open_module, "args": (m.name,)} for m in modules]
        buttons = [names[i : i + ROW_SIZE] for i in range(0, len(names), ROW_SIZE)]
        return "⚙️ <b>Модули с настройками</b>\n<i>Выберите модуль</i>", [*buttons, [CLOSE]]

    def _module_view(self, module):
        config = module.config
        text = f"⚙️ <b>{utils.escape_html(module.name)}</b>\n"
        text += utils.quote("\n\n".join(self._describe(config, key) for key in config), expandable=len(config) > 5)
        keys = [{"text": key, "callback": self._open_key, "args": (module.name, key)} for key in config]
        buttons = [keys[i : i + 2] for i in range(0, len(keys), 2)]
        return text, [*buttons, [{"text": "◀ Назад", "callback": self._open_root}, CLOSE]]

    def _key_view(self, module, key, status=""):
        config = module.config
        text = f"⚙️ <b>{utils.escape_html(module.name)}</b>\n" + utils.quote(self._describe(config, key))
        if status:
            text += "\n" + status
        args = (module.name, key)
        validator = config.value(key).validator
        if isinstance(validator, validators.Boolean):
            label = "Выключить" if config[key] else "Включить"
            row = [{"text": label, "callback": self._set, "args": (*args, not config[key])}]
        elif isinstance(validator, validators.Choice):
            row = [
                {"text": str(option), "callback": self._set, "args": (*args, option)}
                for option in validator.options
                if option != config[key]
            ]
        else:
            row = [{"text": "✍️ Изменить", "input": f"Новое значение {key}", "handler": self._input, "args": args}]
        buttons = [row[i : i + ROW_SIZE] for i in range(0, len(row), ROW_SIZE)]
        buttons.append([{"text": "↩️ Сбросить", "callback": self._reset, "args": args}])
        buttons.append([{"text": "◀ Назад", "callback": self._open_module, "args": (module.name,)}, CLOSE])
        return text, buttons

    def _find(self, name):
        module = self.loader.get_module(name)
        if module is None or not isinstance(module.config, ModuleConfig):
            raise InlineError("Модуль уже выгружен")
        return module

    async def _open_root(self, call):
        await call.edit(*self._root_view())

    async def _open_module(self, call, name):
        await call.edit(*self._module_view(self._find(name)))

    async def _open_key(self, call, name, key):
        await call.edit(*self._key_view(self._find(name), key))

    async def _set(self, call, name, key, value):
        module = self._find(name)
        try:
            module.config[key] = value
        except ValidationError as e:
            await call.edit(*self._key_view(module, key, f"❌ {utils.escape_html(e)}"))
            return
        await call.edit(*self._key_view(module, key, "✅ Сохранено"))

    async def _input(self, call, text, name, key):
        await self._set(call, name, key, text)

    async def _reset(self, call, name, key):
        module = self._find(name)
        module.config.reset(key)
        await call.edit(*self._key_view(module, key, "✅ Сброшено"))
