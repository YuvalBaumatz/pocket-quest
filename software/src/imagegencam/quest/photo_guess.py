"""Family guessing aloud: five reveal levels and no automatic judging."""

from dataclasses import dataclass

LEVELS = (12, 24, 60, 120, 240)


@dataclass
class PhotoGuess:
    photo_id: str
    level: int = 0

    def reconcile(self, choices: list[str]) -> None:
        if self.photo_id not in choices:
            self.photo_id, self.level = choices[0], 0

    def advance(self, choices: list[str]) -> None:
        self.reconcile(choices)
        if self.level < len(LEVELS) - 1:
            self.level += 1
        else:
            self.photo_id = choices[(choices.index(self.photo_id) + 1) % len(choices)]
            self.level = 0

    def snapshot(self) -> dict[str, object]:
        return {"photo_id": self.photo_id, "level": self.level}

    @classmethod
    def restore(cls, data: object) -> "PhotoGuess":
        if not isinstance(data, dict):
            raise ValueError("Invalid Photo Guess save")
        photo_id, level = data.get("photo_id"), data.get("level")
        if not isinstance(photo_id, str) or type(level) is not int or not 0 <= level < 5:
            raise ValueError("Invalid Photo Guess progress")
        if photo_id not in ("fixture:0", "fixture:1", "fixture:2") and (
            len(photo_id) != 32 or any(x not in "0123456789abcdef" for x in photo_id)
        ):
            raise ValueError("Invalid Photo Guess image")
        return cls(photo_id, level)
