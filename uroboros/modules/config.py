from uroboros import Module, ModuleConfig, command, utils
from uroboros.validators import ValidationError


class Config(Module):
    """Настройки модулей"""

    def _configurable(self):
        return [
            m for m in self.loader.modules.values()
            if isinstance(m.config, ModuleConfig) and len(m.config)
        ]

    @command("cfg", aliases=["config"])
    async def cfg(self, message):
        """[модуль] [ключ] [значение] — посмотреть или изменить настройки"""
        raw = utils.get_args_raw(message).strip()
        parts = raw.split(maxsplit=2)

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

    @command("rcfg")
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
