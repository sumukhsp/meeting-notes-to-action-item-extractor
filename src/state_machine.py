from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

from .logging_utils import utc_now
from .schemas import StateTransition, SystemState


@dataclass
class StateMachine:
    state: SystemState = SystemState.IDLE
    transitions: list[StateTransition] = field(default_factory=list)
    seed: int = 0
    max_steps: int = 50
    steps: int = 0
    last_error: str | None = None
    rng: random.Random = field(default_factory=random.Random, repr=False)

    def __post_init__(self) -> None:
        self.rng.seed(self.seed)

    def _guard_max_steps(self, event: str) -> None:
        if self.steps >= self.max_steps:
            self.error(event="max_steps_exceeded", error=f"max_steps={self.max_steps} exceeded")
            raise RuntimeError(f"StateMachine max_steps exceeded ({self.max_steps})")

    def transition(self, event: str, next_state: SystemState) -> StateTransition:
        if self.state == SystemState.ERROR:
            raise RuntimeError("StateMachine is in ERROR state; no further transitions allowed")

        self._guard_max_steps(event)
        t = StateTransition(
            timestamp=utc_now(),
            previous_state=self.state,
            event=event,
            next_state=next_state,
        )
        self.state = next_state
        self.transitions.append(t)
        self.steps += 1
        return t

    def error(self, event: str, error: str, details: dict[str, Any] | None = None) -> StateTransition:
        self.last_error = error
        t = StateTransition(
            timestamp=utc_now(),
            previous_state=self.state,
            event=event,
            next_state=SystemState.ERROR,
        )
        self.state = SystemState.ERROR
        self.transitions.append(t)
        self.steps += 1
        return t
