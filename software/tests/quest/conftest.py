from collections.abc import Iterator
from typing import Any

import pytest

from imagegencam.quest.runtime import Quest


@pytest.fixture(autouse=True)
def close_apps(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Ensure tests release worker threads and the exclusive data-directory lock."""
    instances: list[Quest] = []
    initialize = Quest.__init__

    def tracked(self: Quest, *args: Any, **kwargs: Any) -> None:
        initialize(self, *args, **kwargs)
        instances.append(self)

    monkeypatch.setattr(Quest, "__init__", tracked)
    yield
    for app in reversed(instances):
        app.close()
