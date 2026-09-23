"""Local grown-up choices; not an authentication boundary."""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .missions import MISSIONS
from .storage import atomic_write


@dataclass
class Preferences:
    offline: bool = False
    outing: list[int] = field(default_factory=list)
    excluded_photos: set[str] = field(default_factory=set)

    @classmethod
    def load(cls, root: Path) -> "Preferences":
        path = root / "preferences.json"
        if not path.exists():
            return cls()
        data = json.loads(path.read_text())
        if not isinstance(data, dict) or data.get("schema_version") != 1:
            raise ValueError("Invalid parent preferences")
        offline, outing, excluded = (
            data.get("offline"),
            data.get("outing"),
            data.get("excluded_photos"),
        )
        if type(offline) is not bool or not isinstance(outing, list) or len(outing) > 3:
            raise ValueError("Invalid parent preferences")
        if any(type(x) is not int or not 0 <= x < len(MISSIONS) for x in outing) or len(
            set(outing)
        ) != len(outing):
            raise ValueError("Invalid outing")
        if not isinstance(excluded, list) or any(
            not isinstance(x, str) or not re.fullmatch(r"[0-9a-f]{32}", x) for x in excluded
        ):
            raise ValueError("Invalid photo permissions")
        return cls(offline, outing, set(excluded))

    def save(self, root: Path) -> None:
        atomic_write(
            root / "preferences.json",
            json.dumps(
                {
                    "schema_version": 1,
                    "offline": self.offline,
                    "outing": self.outing,
                    "excluded_photos": sorted(self.excluded_photos),
                }
            ).encode(),
        )
