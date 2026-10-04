"""Сгенерированные страницы документации (справочник команд, примеры) совпадают с кодом."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_generated_docs_are_up_to_date():
    spec = importlib.util.spec_from_file_location("gen_docs", ROOT / "scripts" / "gen_docs.py")
    gen_docs = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen_docs)
    for path, text in gen_docs.generate().items():
        assert path.read_text("utf-8") == text, f"{path.name} устарел: запустите python scripts/gen_docs.py"
