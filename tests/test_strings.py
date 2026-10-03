import asyncio

import pytest

from uroboros import utils
from uroboros.database import Database
from uroboros.loader import Loader

SRC = """
from uroboros import Module

class Greeter(Module):
    strings = {"hello": "Привет, <b>{name}</b>!", "plain": "<i>без подстановки</i>"}
"""


@pytest.fixture
def module(tmp_path):
    (inst,) = asyncio.run(Loader(None, Database(":memory:"), tmp_path).install(SRC, "x"))
    return inst


def test_strings_call_escapes_values(module):
    assert module.strings("hello", name="<script>") == "Привет, <b>&lt;script&gt;</b>!"


def test_strings_html_values_are_kept(module):
    assert module.strings("hello", name=utils.Html("<i>Аня</i>")) == "Привет, <b><i>Аня</i></b>!"


def test_strings_item_and_call_without_kwargs(module):
    assert module.strings["plain"] == module.strings("plain") == "<i>без подстановки</i>"


def test_strings_missing_key(module):
    with pytest.raises(KeyError):
        module.strings("nope")


def test_class_strings_are_not_mutated(module):
    module.strings["hello"] = "изменено"
    assert type(module).strings["hello"] == "Привет, <b>{name}</b>!"
