from uroboros import Module, ModuleConfig, command, utils, validators
from uroboros.errors import InlineError
from uroboros.validators import ValidationError

ROW_SIZE = 3


class Config(Module):
    """Module settings"""

    strings = {
        "configurable": "⚙️ <b>Modules with settings</b> · {count}",
        "none": "<i>none</i>",
        "module_hint": "module settings: <code>{prefix}cfg module</code>",
        "no_config": "❌ <b>This module has no settings</b>",
        "settings": "⚙️ <b>{name}</b> · settings",
        "change_hint": "change: <code>{prefix}cfg {name} key value</code>",
        "no_key": "❌ <b>No key</b> <code>{key}</code>",
        "invalid": "❌ <b>Not suitable</b>",
        "saved": "✅ <b>Saved</b>",
        "which_reset": "❌ <b>Which setting to reset?</b>",
        "reset_usage": "<code>rcfg module key</code>",
        "reset": "↩️ <b>Reset</b>",
        "no_configurable": "⚙️ <b>No modules with settings</b>",
        "pick_module": "pick a module with a button",
        "pick_key": "pick what to change",
        "back": "◀️ Back",
        "close": "✖️ Close",
        "turn_off": "🔴 Turn off",
        "turn_on": "🟢 Turn on",
        "edit": "✍️ Change",
        "new_value": "New value {key}",
        "reset_button": "↩️ Reset",
        "unloaded": "The module is already unloaded",
        "invalid_inline": "❌ <b>Not suitable:</b> {error}",
    }
    strings_ru = {
        "_cls_doc": "Настройки модулей",
        "_cmd_doc_cfg": "[модуль] [ключ] [значение] — посмотреть или изменить настройки",
        "_cmd_doc_rcfg": "<модуль> <ключ> — сбросить настройку на значение по умолчанию",
        "configurable": "⚙️ <b>Модули с настройками</b> · {count}",
        "none": "<i>нет</i>",
        "module_hint": "настройки модуля: <code>{prefix}cfg модуль</code>",
        "no_config": "❌ <b>У этого модуля нет настроек</b>",
        "settings": "⚙️ <b>{name}</b> · настройки",
        "change_hint": "изменить: <code>{prefix}cfg {name} ключ значение</code>",
        "no_key": "❌ <b>Нет ключа</b> <code>{key}</code>",
        "invalid": "❌ <b>Не подходит</b>",
        "saved": "✅ <b>Сохранено</b>",
        "which_reset": "❌ <b>Какую настройку сбросить?</b>",
        "reset_usage": "<code>rcfg модуль ключ</code>",
        "reset": "↩️ <b>Сброшено</b>",
        "no_configurable": "⚙️ <b>Модулей с настройками нет</b>",
        "pick_module": "выберите модуль кнопкой",
        "pick_key": "выберите, что изменить",
        "back": "◀️ Назад",
        "close": "✖️ Закрыть",
        "turn_off": "🔴 Выключить",
        "turn_on": "🟢 Включить",
        "edit": "✍️ Изменить",
        "new_value": "Новое значение {key}",
        "reset_button": "↩️ Сбросить",
        "unloaded": "Модуль уже выгружен",
        "invalid_inline": "❌ <b>Не подходит:</b> {error}",
    }

    @property
    def _close(self):
        return {"text": self.strings("close"), "action": "close"}

    def _configurable(self):
        return [m for m in self.loader.modules.values() if isinstance(m.config, ModuleConfig) and len(m.config)]

    @command("cfg", aliases=["config"], access="owner", emoji="⚙️")
    async def cfg(self, message):
        """[module] [key] [value] — view or change settings"""
        raw = utils.get_args_raw(message).strip()
        parts = raw.split(maxsplit=2)

        if len(parts) < 3 and self.inline.available:
            view = self._inline_view(parts)
            if view is not None:
                try:
                    await self.inline.form(message, *view)
                    return
                except InlineError:
                    pass  # e.g. inline bots are banned in this chat: answer with text

        if not parts:
            modules = sorted(self._configurable(), key=lambda m: m.name.lower())
            prefix = utils.get_prefix(self.db.raw)
            await utils.answer(
                message,
                utils.card(
                    self.strings("configurable", count=len(modules)),
                    [f"▸ <b>{utils.escape_html(m.name)}</b> — {len(m.config)}" for m in modules]
                    or self.strings("none"),
                    hint=self.strings("module_hint", prefix=prefix),
                ),
            )
            return

        module = self.loader.get_module(parts[0])
        if module is None or not isinstance(module.config, ModuleConfig):
            await utils.answer(message, self.strings("no_config"))
            return
        config = module.config

        if len(parts) == 1:
            items = "\n\n".join(self._describe(module, key) for key in config)
            prefix = utils.get_prefix(self.db.raw)
            await utils.answer(
                message,
                utils.card(
                    self.strings("settings", name=module.name),
                    items,
                    hint=self.strings("change_hint", prefix=prefix, name=module.name.lower()),
                ),
            )
            return

        key = parts[1]
        if key not in config:
            await utils.answer(message, self.strings("no_key", key=key))
            return

        if len(parts) == 2:
            await utils.answer(
                message, utils.card(f"⚙️ <b>{utils.escape_html(module.name)}</b>", self._describe(module, key))
            )
            return

        try:
            config[key] = parts[2]
        except ValidationError as e:
            await utils.answer(message, utils.card(self.strings("invalid"), utils.escape_html(e)))
            return
        await utils.answer(message, utils.card(self.strings("saved"), self._describe(module, key)))

    @command("rcfg", access="owner", emoji="↩️")
    async def rcfg(self, message):
        """<module> <key> — reset a setting to its default"""
        parts = utils.get_args(message)
        module = self.loader.get_module(parts[0]) if parts else None
        if len(parts) != 2 or module is None or not isinstance(module.config, ModuleConfig):
            await utils.answer(message, utils.card(self.strings("which_reset"), hint=self.strings("reset_usage")))
            return
        if parts[1] not in module.config:
            await utils.answer(message, self.strings("no_key", key=parts[1]))
            return
        module.config.reset(parts[1])
        await utils.answer(message, utils.card(self.strings("reset"), self._describe(module, parts[1])))

    @staticmethod
    def _describe(module, key):
        config = module.config
        value = config.value(key)
        text = f"🔧 <code>{utils.escape_html(key)}</code> = <b>{utils.escape_html(repr(config[key]))}</b>"
        # As in Hikka: _cfg_doc_<key> in the module strings translates the setting description.
        doc = module.strings.get(f"_cfg_doc_{key}") or value.doc
        hints = [h for h in (doc, getattr(value.validator, "doc", "")) if h]
        if hints:
            text += f"\n<i>{utils.escape_html(' · '.join(hints))}</i>"
        return text

    # --- inline: modules → keys → value ---

    def _inline_view(self, parts):
        """Form for ``.cfg``, ``.cfg module`` and ``.cfg module key``; None — answer with text (wrong name)."""
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
            return self.strings("no_configurable"), [[self._close]]
        names = [{"text": m.name, "callback": self._open_module, "args": (m.name,)} for m in modules]
        buttons = [names[i : i + ROW_SIZE] for i in range(0, len(names), ROW_SIZE)]
        title = self.strings("configurable", count=len(modules)) + f"\n💡 <i>{self.strings('pick_module')}</i>"
        return title, [*buttons, [self._close]]

    def _module_view(self, module):
        config = module.config
        text = utils.card(
            self.strings("settings", name=module.name),
            "\n\n".join(self._describe(module, key) for key in config),
            hint=self.strings("pick_key"),
            expandable=len(config) > 5,
        )
        keys = [{"text": key, "callback": self._open_key, "args": (module.name, key)} for key in config]
        buttons = [keys[i : i + 2] for i in range(0, len(keys), 2)]
        return text, [*buttons, [{"text": self.strings("back"), "callback": self._open_root}, self._close]]

    def _key_view(self, module, key, status=""):
        config = module.config
        text = utils.card(f"⚙️ <b>{utils.escape_html(module.name)}</b>", self._describe(module, key))
        if status:
            text += "\n" + status
        args = (module.name, key)
        validator = config.value(key).validator
        if isinstance(validator, validators.Boolean):
            label = self.strings("turn_off") if config[key] else self.strings("turn_on")
            row = [{"text": label, "callback": self._set, "args": (*args, not config[key])}]
        elif isinstance(validator, validators.Choice):
            row = [
                {"text": str(option), "callback": self._set, "args": (*args, option)}
                for option in validator.options
                if option != config[key]
            ]
        else:
            prompt = self.strings("new_value", key=key)
            row = [{"text": self.strings("edit"), "input": prompt, "handler": self._input, "args": args}]
        buttons = [row[i : i + ROW_SIZE] for i in range(0, len(row), ROW_SIZE)]
        buttons.append([{"text": self.strings("reset_button"), "callback": self._reset, "args": args}])
        buttons.append(
            [{"text": self.strings("back"), "callback": self._open_module, "args": (module.name,)}, self._close]
        )
        return text, buttons

    def _find(self, name):
        module = self.loader.get_module(name)
        if module is None or not isinstance(module.config, ModuleConfig):
            raise InlineError(self.strings("unloaded"))
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
            await call.edit(*self._key_view(module, key, self.strings("invalid_inline", error=e)))
            return
        await call.edit(*self._key_view(module, key, self.strings("saved")))

    async def _input(self, call, text, name, key):
        await self._set(call, name, key, text)

    async def _reset(self, call, name, key):
        module = self._find(name)
        module.config.reset(key)
        await call.edit(*self._key_view(module, key, self.strings("reset")))
