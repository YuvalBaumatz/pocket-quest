#!/usr/bin/env bash
# Offline checks only. Generated data stays separate from the real photo library.
set -euo pipefail
quest_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$quest_root"
quest_python="$quest_root/.venv/bin/python"
if [[ ! -x "$quest_python" ]]; then
  echo "Install software/requirements-dev.lock.txt in software/.venv first." >&2
  exit 1
fi
export PYTHONPATH="$quest_root/src${PYTHONPATH:+:$PYTHONPATH}"
"$quest_python" -m ruff check src/imagegencam/quest tests/quest
"$quest_python" -m ruff format --check src/imagegencam/quest tests/quest
"$quest_python" -m mypy
"$quest_python" -m pytest tests -q
quest_artifacts="$(mktemp -d "${TMPDIR:-/tmp}/pocket-quest-check.XXXXXX")"
"$quest_python" -m imagegencam.quest --demo --screenshots "$quest_artifacts/screenshots" --data-dir "$quest_artifacts/screenshots-data"
SDL_VIDEODRIVER=dummy "$quest_python" -m imagegencam.quest --demo --frames 3 --data-dir "$quest_artifacts/smoke-data"
echo "Offline checks passed. Visual review artifacts: $quest_artifacts/screenshots"
echo "Live Gemini, webcam, child usability and Pi hardware still need separate acceptance checks."
