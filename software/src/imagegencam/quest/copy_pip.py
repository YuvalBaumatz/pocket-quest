"""Offline sequence game with an injected clock and random source."""

from dataclasses import dataclass
from enum import StrEnum
from random import Random

from .input import Action

DIRECTIONS = (Action.UP, Action.RIGHT, Action.DOWN, Action.LEFT)


class Phase(StrEnum):
    WATCH = "watch"
    INPUT = "input"
    AGAIN = "again"
    SUCCESS = "success"
    COMPLETE = "complete"


@dataclass
class CopyPip:
    sequence: list[Action]
    phase: Phase = Phase.WATCH
    position: int = 0
    lit: Action | None = None
    due: float = 0

    @classmethod
    def create(cls, rng: Random, now: float) -> "CopyPip":
        game = cls([rng.choice(DIRECTIONS)])
        game.replay(now)
        return game

    def replay(self, now: float) -> None:
        self.phase, self.position = Phase.WATCH, 0
        self.lit, self.due = self.sequence[0], now + 0.6

    def tick(self, now: float) -> bool:
        if self.phase == Phase.COMPLETE or now < self.due:
            return False
        if self.phase in (Phase.AGAIN, Phase.SUCCESS):
            self.replay(now)
        elif self.phase == Phase.WATCH:
            if self.lit is not None:
                self.lit, self.due = None, now + 0.25
            else:
                self.position += 1
                if self.position == len(self.sequence):
                    self.phase, self.position = Phase.INPUT, 0
                else:
                    self.lit, self.due = self.sequence[self.position], now + 0.6
        elif self.lit is not None:
            self.lit = None
        else:
            return False
        return True

    def handle(self, action: Action, now: float, rng: Random) -> None:
        # Inputs arriving during a demonstration never become guesses, even if
        # their timestamp is after its deadline; tick transitions independently.
        if self.phase != Phase.INPUT:
            return
        if action == Action.CONFIRM:
            self.replay(now)
        elif action in DIRECTIONS:
            self.lit, self.due = action, now + 0.3
            if action != self.sequence[self.position]:
                self.phase, self.due = Phase.AGAIN, now + 0.8
            else:
                self.position += 1
                if self.position == len(self.sequence):
                    if len(self.sequence) == 5:
                        self.phase = Phase.COMPLETE
                    else:
                        self.sequence.append(rng.choice(DIRECTIONS))
                        self.phase, self.due = Phase.SUCCESS, now + 0.8

    def snapshot(self) -> dict[str, object]:
        return {
            "sequence": [x.value for x in self.sequence],
            "complete": self.phase == Phase.COMPLETE,
        }

    @classmethod
    def restore(cls, data: object) -> "CopyPip":
        if not isinstance(data, dict):
            raise ValueError("Invalid Copy Pip save")
        sequence, complete = data.get("sequence"), data.get("complete")
        if (
            not isinstance(sequence, list)
            or not 1 <= len(sequence) <= 5
            or any(not isinstance(x, str) or x not in DIRECTIONS for x in sequence)
            or type(complete) is not bool
            or (complete and len(sequence) != 5)
        ):
            raise ValueError("Invalid Copy Pip progress")
        return cls([Action(x) for x in sequence], Phase.COMPLETE if complete else Phase.WATCH)
