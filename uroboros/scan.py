"""Проверка исходника стороннего модуля перед установкой. Это эвристика, а не песочница.

Опасное — кража сессии, захват аккаунта, скрытый код — блокирует установку, пока пользователь явно
не подтвердит. Подозрительное только показывается в ответе.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field

from .errors import LoadError

DANGER = "danger"
WARNING = "warning"

# Запросы Telegram и методы клиента, которыми угоняют или ломают аккаунт.
DANGER_NAMES = {
    "ResetAuthorizationsRequest": "завершает все другие сеансы аккаунта",
    "ResetAuthorizationRequest": "завершает сеанс аккаунта",
    "DeleteAccountRequest": "удаляет аккаунт",
    "UpdatePasswordSettingsRequest": "меняет пароль 2FA",
    "ResetPasswordRequest": "сбрасывает пароль 2FA",
    "ChangePhoneRequest": "меняет номер телефона",
    "SendChangePhoneCodeRequest": "меняет номер телефона",
    "ExportLoginTokenRequest": "входит в аккаунт по QR-коду",
    "AcceptLoginTokenRequest": "подтверждает вход в аккаунт с другого устройства",
    "ExportAuthorizationRequest": "выгружает авторизацию аккаунта",
    "SendStarsFormRequest": "тратит звёзды",
    "SendPaymentFormRequest": "совершает платёж",
    "TransferStarGiftRequest": "передаёт подарки",
    "log_out": "выходит из аккаунта",
    "edit_2fa": "меняет пароль 2FA",
    "qr_login": "входит в аккаунт по QR-коду",
    "auth_key": "читает ключ авторизации (сессию)",
    "api_hash": "читает api_hash",
}
WARNING_NAMES = {
    "GetAuthorizationsRequest": "получает список сеансов аккаунта",
    "JoinChannelRequest": "подписывает аккаунт на каналы",
    "ImportChatInviteRequest": "вступает в чаты по ссылке",
    "request_join": "подписывает аккаунт на каналы",
    "StringSession": "работает со строковыми сессиями",
}
# Полные имена (после разбора импортов): префикс → описание.
WARNING_DOTTED = {
    "os.environ": "читает переменные окружения",
    "os.getenv": "читает переменные окружения",
    "os.putenv": "меняет переменные окружения",
    "os.system": "запускает команды в системе",
    "os.popen": "запускает команды в системе",
    "os.exec": "запускает команды в системе",
    "os.spawn": "запускает команды в системе",
    "os.fork": "запускает команды в системе",
    "subprocess.": "запускает команды в системе",
    "pty.spawn": "запускает команды в системе",
    "asyncio.create_subprocess_": "запускает команды в системе",
    "os.remove": "удаляет файлы",
    "os.unlink": "удаляет файлы",
    "os.rmdir": "удаляет файлы",
    "shutil.rmtree": "удаляет файлы",
    "ctypes.": "вызывает системные библиотеки (ctypes)",
    "sys.modules": "меняет загруженные модули Python",
    "sys.meta_path": "меняет механизм импорта Python",
    "sys.path_hooks": "меняет механизм импорта Python",
    "sys.settrace": "перехватывает выполнение кода",
    "sys.setprofile": "перехватывает выполнение кода",
}
DANGER_DOTTED = {
    "marshal.loads": "исполняет скрытый байткод (marshal)",
    "uroboros.ratelimit": "обходит защиту от флуда",
}
# Части имён: self.loader.security.owner → права доступа Uroboros.
DANGER_PARTS = {
    "loader.security": "меняет права доступа Uroboros",
    "loader.ratelimit": "обходит защиту от флуда",
    "session.save": "выгружает сессию в строку",
    "StringSession.save": "выгружает сессию в строку",
}
WARNING_PARTS = {
    "client.session": "обращается к сессии клиента",
}
# Строки в коде.
DANGER_STRINGS = [
    (re.compile(r"\.session(-journal)?\b", re.IGNORECASE), "обращается к файлу сессии"),
    (re.compile(r"\buroboros\.db\b"), "читает базу данных Uroboros"),
    (re.compile(r"^uroboros\.(inline|security)$"), "читает системные настройки Uroboros (токен бота, права доступа)"),
    (re.compile(r"^UROBOROS_(API_ID|API_HASH|BOT_TOKEN)$"), "читает ключи Uroboros из окружения"),
]
WARNING_STRINGS = [
    (re.compile(r"\bconfig\.json\b"), "обращается к config.json (там api_id и api_hash)"),
]
DANGER_NAMES_STRINGS = {name for name in DANGER_NAMES if name[0].isupper()}  # getattr(functions, "...Request")
DECODERS = {
    "b64decode",
    "b32decode",
    "b16decode",
    "a85decode",
    "b85decode",
    "urlsafe_b64decode",
    "decodebytes",
    "decompress",
    "unhexlify",
    "fromhex",
    "decode",
    "loads",
}
EXEC_FUNCS = {"exec", "eval", "compile"}
BLOB_RE = re.compile(r"^[A-Za-z0-9+/=_\-\s]+$")
BLOB_SIZE = 1000


@dataclass
class Finding:
    level: str
    text: str
    lines: list[int] = field(default_factory=list)


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)

    @property
    def dangerous(self) -> list[Finding]:
        return [f for f in self.findings if f.level == DANGER]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.level == WARNING]

    def add(self, level: str, text: str, line: int) -> None:
        for finding in self.findings:
            if finding.level == level and finding.text == text:
                if line not in finding.lines:
                    finding.lines.append(line)
                return
        self.findings.append(Finding(level, text, [line]))


class UnsafeModuleError(LoadError):
    """В модуле опасный код, а пользователь не подтвердил установку."""

    def __init__(self, report: Report):
        self.report = report
        super().__init__("В модуле опасный код: " + summary(report.dangerous))


def describe(findings: list[Finding]) -> str:
    """По строке на находку: ``строки 3, 7: читает файл сессии``."""
    lines = []
    for finding in findings:
        numbers = sorted(finding.lines)
        shown = ", ".join(map(str, numbers[:5])) + (" …" if len(numbers) > 5 else "")
        word = "строка" if len(numbers) == 1 else "строки"
        lines.append(f"{word} {shown}: {finding.text}")
    return "\n".join(lines)


def summary(findings: list[Finding]) -> str:
    return "; ".join(finding.text for finding in findings)


def scan(source: str) -> Report:
    report = Report()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return report  # ошибку покажет компиляция при загрузке
    _Visitor(report, tree).visit(tree)
    return report


def _docstrings(tree: ast.AST) -> set[int]:
    """id строк-докстрингов: их текст не проверяем."""
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                found.add(id(first.value))
    return found


class _Visitor(ast.NodeVisitor):
    def __init__(self, report: Report, tree: ast.AST):
        self.report = report
        self.aliases: dict[str, str] = {}  # локальное имя → полное (import x as y, from a import b as c)
        self.docstrings = _docstrings(tree)

    def danger(self, node: ast.AST, text: str) -> None:
        self.report.add(DANGER, text, getattr(node, "lineno", 0))

    def warning(self, node: ast.AST, text: str) -> None:
        self.report.add(WARNING, text, getattr(node, "lineno", 0))

    # --- имена ---

    def dotted(self, node: ast.AST) -> str | None:
        if isinstance(node, ast.Name):
            return self.aliases.get(node.id, node.id)
        if isinstance(node, ast.Attribute):
            base = self.dotted(node.value)
            return f"{base}.{node.attr}" if base else node.attr
        if isinstance(node, ast.Call):
            return self.dotted(node.func)
        return None

    def check_name(self, node: ast.AST, name: str) -> None:
        last = name.rsplit(".", 1)[-1]
        if last in DANGER_NAMES:
            self.danger(node, DANGER_NAMES[last])
        elif last in WARNING_NAMES:
            self.warning(node, WARNING_NAMES[last])
        for prefix, text in DANGER_DOTTED.items():
            if name.startswith(prefix):
                self.danger(node, text)
        for prefix, text in WARNING_DOTTED.items():
            if name.startswith(prefix):
                self.warning(node, text)
        padded = f".{name}."
        for part, text in DANGER_PARTS.items():
            if f".{part}." in padded:
                self.danger(node, text)
        for part, text in WARNING_PARTS.items():
            if f".{part}." in padded:
                self.warning(node, text)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.aliases[(alias.asname or alias.name).split(".")[0]] = (
                alias.name if alias.asname else alias.name.split(".")[0]
            )
            self.check_name(node, alias.name)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        base = node.module or ""
        for alias in node.names:
            full = f"{base}.{alias.name}" if base else alias.name
            self.aliases[alias.asname or alias.name] = full
            self.check_name(node, full)

    def visit_Name(self, node: ast.Name) -> None:
        if node.id in self.aliases:
            return  # уже проверено при импорте
        self.check_name(node, node.id)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        self.check_name(node, self.dotted(node) or node.attr)
        # Вложенные атрибуты (a.b в a.b.c) не обходим: префиксы проверены целиком, а имена — по последней части.
        base = node.value
        while isinstance(base, ast.Attribute):
            base = base.value
        self.visit(base)

    # --- вызовы ---

    def visit_Call(self, node: ast.Call) -> None:
        name = self.dotted(node.func) or ""
        func = name.rsplit(".", 1)[-1]
        if name in EXEC_FUNCS or name in {f"builtins.{f}" for f in EXEC_FUNCS}:
            self.check_exec(node, func)
        elif func in ("__import__", "import_module") and node.args and not isinstance(node.args[0], ast.Constant):
            self.warning(node, "импортирует модули по вычисляемому имени")
        elif func in ("unlink", "rmtree"):
            self.warning(node, "удаляет файлы")
        self.generic_visit(node)

    def check_exec(self, node: ast.Call, func: str) -> None:
        if not node.args or isinstance(node.args[0], ast.Constant):
            return
        decoded = any(
            isinstance(inner, ast.Call) and (self.dotted(inner.func) or "").rsplit(".", 1)[-1] in DECODERS
            for inner in ast.walk(node.args[0])
        )
        if decoded:
            self.danger(node, "исполняет закодированный код")
        else:
            self.warning(node, f"исполняет код из строки ({func})")

    # --- строки ---

    def visit_Constant(self, node: ast.Constant) -> None:
        if not isinstance(node.value, str) or id(node) in self.docstrings:
            return
        text = node.value
        if text in DANGER_NAMES_STRINGS:
            self.danger(node, DANGER_NAMES[text])
        for pattern, message in DANGER_STRINGS:
            if pattern.search(text):
                self.danger(node, message)
        for pattern, message in WARNING_STRINGS:
            if pattern.search(text):
                self.warning(node, message)
        if len(text) >= BLOB_SIZE and BLOB_RE.match(text):
            self.warning(node, "содержит большой закодированный блок")
