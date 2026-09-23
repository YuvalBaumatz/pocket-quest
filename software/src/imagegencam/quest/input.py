"""One semantic input contract for desktop and eventual physical controls."""

from enum import StrEnum


class Action(StrEnum):
    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"
    CONFIRM = "confirm"
    BACK = "back"
    HOME = "home"


class InputMapper:
    """Suppress key repeat; a consumed back hold never also emits a short back."""

    def __init__(self) -> None:
        self.held: dict[Action, float] = {}
        self.next_repeat: dict[Action, float] = {}
        self.back_consumed = False

    def press(self, action: Action, now: float) -> list[Action]:
        if action in self.held:
            return []
        self.held[action] = now
        self.next_repeat[action] = now + 0.35
        if action == Action.BACK:
            self.back_consumed = False
            return []
        return [action]

    def release(self, action: Action, now: float) -> list[Action]:
        started = self.held.pop(action, None)
        self.next_repeat.pop(action, None)
        if action == Action.BACK and started is not None and not self.back_consumed:
            return [Action.HOME if now - started >= 0.8 else Action.BACK]
        return []

    def tick(self, now: float, *, repeat_directions: bool = True) -> list[Action]:
        events: list[Action] = []
        for action, started in self.held.items():
            if action == Action.BACK:
                if not self.back_consumed and now - started >= 0.8:
                    self.back_consumed = True
                    events.append(Action.HOME)
            elif repeat_directions and action in (
                Action.UP,
                Action.DOWN,
                Action.LEFT,
                Action.RIGHT,
            ):
                if now >= self.next_repeat[action]:
                    events.append(action)
                    self.next_repeat[action] = now + 0.15
        return events

    def clear(self) -> None:
        """Release all controls when the simulator loses window focus."""
        self.held.clear()
        self.next_repeat.clear()
        self.back_consumed = False
