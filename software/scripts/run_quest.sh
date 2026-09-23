#!/usr/bin/env bash
set -euo pipefail
quest_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
quest_python="${QUEST_PYTHON:-$quest_root/.venv/bin/python}"
if [[ ! -x "$quest_python" ]]; then
  echo "Create software/.venv and install requirements-quest.txt first (see README)." >&2
  exit 1
fi
export PYTHONPATH="$quest_root/src${PYTHONPATH:+:$PYTHONPATH}"
exec "$quest_python" -m imagegencam.quest "$@"
