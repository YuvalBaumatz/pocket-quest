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
    print("Paste your Gemini API key, then press Enter. No characters will appear as you paste.")
    print("Press Ctrl+C to cancel without changing your saved key.")
    for _ in range(3):
        try:
            key = getpass.getpass("Gemini API key (hidden; saved locally): ").strip()
        except (EOFError, KeyboardInterrupt):
            raise ValueError("Key setup cancelled. Your saved settings were not changed.") from None
        key = re.sub(r"^(?:export\s+)?GEMINI_API_KEY\s*=\s*", "", key)
        if len(key) >= 2 and key[0] == key[-1] and key[0] in "\"'":
            key = key[1:-1].strip()
        if re.fullmatch(r"[A-Za-z0-9_-]+", key):
            break
        if not key:
            print("No key was received. Paste the key before pressing Enter.")
        else:
            print("The input contains unsupported characters. Copy the API key and try again.")
    else:
        raise ValueError(
            "Key setup stopped after 3 attempts. Your saved settings were not changed."
        )
    lines = path.read_text().splitlines() if path.exists() else []
    lines = [line for line in lines if line.split("=", 1)[0].strip() != "GEMINI_API_KEY"]
    lines.append(f"GEMINI_API_KEY={key}")
    # atomic_write uses a private 0600 temporary file and replaces the target.
    atomic_write(path, ("\n".join(lines) + "\n").encode())
    os.environ["GEMINI_API_KEY"] = key
    print(f"Gemini key saved locally to {path}. No API request has been sent.")
