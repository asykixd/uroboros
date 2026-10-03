import asyncio

import pytest

from uroboros import loop
from uroboros.database import Database
from uroboros.loader import Loader

SRC = """
from uroboros import Module, loop

class Ticker(Module):
    ticks = 0

    @loop(interval=0.01)
    async def tick(self):
        type(self).ticks += 1
        if type(self).ticks == 2:
            raise RuntimeError("ошибка не останавливает цикл")

    @loop(interval=0.01, autostart=False)
    async def manual(self):
        pass
"""


def test_loop_runs_survives_errors_and_stops_on_unload(tmp_path):
    async def scenario():
        loader = Loader(None, Database(":memory:"), tmp_path)
        (inst,) = await loader.install(SRC, "x")
        assert inst.tick.running and not inst.manual.running
        await asyncio.sleep(0.08)
        assert type(inst).ticks >= 3

        inst.manual.start()
        assert inst.manual.running
        tick, manual = inst.tick, inst.manual
        await loader.uninstall("ticker")
        assert not tick.running and not manual.running
        stopped_at = type(inst).ticks
        await asyncio.sleep(0.03)
        assert type(inst).ticks == stopped_at

    asyncio.run(scenario())


def test_loop_rejects_bad_interval():
    with pytest.raises(ValueError):
        loop(0)
