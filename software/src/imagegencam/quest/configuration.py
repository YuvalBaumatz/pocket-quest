"""Local credentials setup. Never print keys or store them in job records."""

import getpass
import os
import re
from pathlib import Path

from imagegencam.config import load_env_file

from .storage import atomic_write


def env_path() -> Path:
    return Path(__file__).resolve().parents[3] / ".env"


def load_credentials() -> None:
    load_env_file(env_path())


def setup_gemini(path: Path | None = None) -> None:
    path = path or env_path()
    key = getpass.getpass("Gemini API key (hidden; saved locally): ").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", key):
        raise ValueError("The key is empty or contains unsupported whitespace/characters")
    lines = path.read_text().splitlines() if path.exists() else []
    lines = [line for line in lines if line.split("=", 1)[0].strip() != "GEMINI_API_KEY"]
    lines.append(f"GEMINI_API_KEY={key}")
    # atomic_write uses a private 0600 temporary file and replaces the target.
    atomic_write(path, ("\n".join(lines) + "\n").encode())
    os.environ["GEMINI_API_KEY"] = key
    print(f"Gemini key saved locally to {path}. No API request has been sent.")
