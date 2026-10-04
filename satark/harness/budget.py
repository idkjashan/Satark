"""Budget: time and tool-call accounting for one run (LLD §3.2, §3.6).

Two deadlines share one clock (`time.monotonic`, immune to wall-clock jumps): the verdict
deadline (check mode must have a verdict by then) and the run deadline (the whole run, including
the explanation, must end by then). `tool_calls` is spent by the executor, one unit per checker
`cost`, so a wave never runs more steps than the budget allows.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class Budget:
    verdict_deadline_s: float
    run_deadline_s: float
    tool_calls: int
    _start: float = field(default_factory=time.monotonic, repr=False)
    tool_calls_left: int = field(init=False)

    def __post_init__(self) -> None:
        self.tool_calls_left = self.tool_calls

    def take(self, cost: int = 1) -> bool:
        """Spend `cost` tool calls. False (and no change) when not enough are left."""
        if cost > self.tool_calls_left:
            return False
        self.tool_calls_left -= cost
        return True

    def verdict_left(self) -> float:
        return max(0.0, self.verdict_deadline_s - (time.monotonic() - self._start))

    def run_left(self) -> float:
        return max(0.0, self.run_deadline_s - (time.monotonic() - self._start))

    def verdict_expired(self) -> bool:
        return self.verdict_left() <= 0

    def expired(self) -> bool:
        return self.run_left() <= 0
