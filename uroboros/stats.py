"""Usage statistics for ``.stats``: command calls and timings, errors. In memory, reset on restart."""

from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass


@dataclass
class CommandStats:
    calls: int = 0
    errors: int = 0
    total: float = 0.0  # seconds
    slowest: float = 0.0

    @property
    def average(self) -> float:
        return self.total / self.calls if self.calls else 0.0


class Stats:
    def __init__(self, clock=time.perf_counter):
        self.clock = clock
        self.commands: dict[tuple[str, str], CommandStats] = {}  # (module, command) → stats
        self.watcher_errors: Counter[str] = Counter()  # module → errors in its watchers

    def record_command(self, module: str, command: str, seconds: float, *, failed: bool) -> None:
        entry = self.commands.setdefault((module, command), CommandStats())
        entry.calls += 1
        entry.errors += failed
        entry.total += seconds
        entry.slowest = max(entry.slowest, seconds)

    def module_commands(self, module: str) -> dict[str, CommandStats]:
        return {cmd: entry for (mod, cmd), entry in self.commands.items() if mod == module}

    def modules(self) -> dict[str, CommandStats]:
        """Per-module totals over all its commands."""
        result: dict[str, CommandStats] = {}
        for (module, _), entry in self.commands.items():
            total = result.setdefault(module, CommandStats())
            total.calls += entry.calls
            total.errors += entry.errors
            total.total += entry.total
            total.slowest = max(total.slowest, entry.slowest)
        return result

    def reset(self) -> None:
        self.commands.clear()
        self.watcher_errors.clear()
