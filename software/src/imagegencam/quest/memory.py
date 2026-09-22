"""Deterministic six-card rules, independent of rendering and hardware."""

from dataclasses import dataclass, field
from random import Random

from .input import Action


@dataclass
class MemoryGame:
    deck: list[str]
    cursor: int = 0
    matched: set[int] = field(default_factory=set)
    exposed: list[int] = field(default_factory=list)
    hide_at: float | None = None

    @classmethod
    def create(cls, photos: list[str], rng: Random) -> "MemoryGame":
        choices = list(dict.fromkeys(photos))[:3]
        choices += [f"fixture:{i}" for i in range(3 - len(choices))]
        deck = choices * 2
        rng.shuffle(deck)
        return cls(deck)

    @property
    def complete(self) -> bool:
        return len(self.matched) == 6

    def tick(self, now: float) -> None:
        if self.hide_at is not None and now >= self.hide_at:
            self.exposed.clear()
            self.hide_at = None

    def handle(self, action: Action, now: float) -> None:
        self.tick(now)
        row, col = divmod(self.cursor, 3)
        if action == Action.LEFT:
            col = max(0, col - 1)
        elif action == Action.RIGHT:
            col = min(2, col + 1)
        elif action == Action.UP:
            row = max(0, row - 1)
        elif action == Action.DOWN:
            row = min(1, row + 1)
        elif action == Action.CONFIRM and self.hide_at is None:
            if self.cursor not in self.matched and self.cursor not in self.exposed:
                self.exposed.append(self.cursor)
                if len(self.exposed) == 2:
                    a, b = self.exposed
                    if self.deck[a] == self.deck[b]:
                        self.matched.update(self.exposed)
                        self.exposed.clear()
                    else:
                        self.hide_at = now + 1.0
        self.cursor = row * 3 + col

    def snapshot(self) -> dict[str, object]:
        return {
            "deck": self.deck,
            "cursor": self.cursor,
            "matched": sorted(self.matched),
        }

    @classmethod
    def restore(cls, data: object) -> "MemoryGame":
        if not isinstance(data, dict):
            raise ValueError("Invalid memory save")
        deck, cursor, matched = (
            data.get("deck"),
            data.get("cursor"),
            data.get("matched"),
        )
        if (
            not isinstance(deck, list)
            or len(deck) != 6
            or not all(isinstance(x, str) for x in deck)
        ):
            raise ValueError("Invalid deck")
        if len(set(deck)) != 3 or any(deck.count(x) != 2 for x in deck):
            raise ValueError("Invalid pairs")
        if type(cursor) is not int or not 0 <= cursor < 6:
            raise ValueError("Invalid cursor")
        if not isinstance(matched, list) or any(
            type(x) is not int or not 0 <= x < 6 for x in matched
        ):
            raise ValueError("Invalid matches")
        selected = set(matched)
        if any(sum(deck[i] == value for i in selected) not in (0, 2) for value in set(deck)):
            raise ValueError("Incomplete matched pair")
        return cls(deck, cursor, selected)
