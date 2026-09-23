"""Local credentials setup. Never print keys or store them in job records."""

import getpass
import os
import re
import subprocess
import sys
from pathlib import Path

from imagegencam.config import load_env_file

from .storage import atomic_write


def env_path() -> Path:
    return Path(__file__).resolve().parents[3] / ".env"


def load_credentials() -> None:
    load_env_file(env_path())


def setup_gemini(path: Path | None = None, *, clipboard: bool = False) -> None:
    path = path or env_path()
    if clipboard and sys.platform != "darwin":
        raise ValueError("Clipboard key setup is available on macOS only.")
    if not clipboard:
        print(
            "Paste your Gemini API key, then press Enter. No characters will appear as you paste."
        )
        print("Press Ctrl+C to cancel without changing your saved key.")
    for _ in range(1 if clipboard else 3):
        try:
            if clipboard:
                key = subprocess.run(
                    ["/usr/bin/pbpaste"], capture_output=True, text=True, check=True, timeout=5
                ).stdout.strip()
            else:
                key = getpass.getpass("Gemini API key (hidden; saved locally): ").strip()
        except (EOFError, KeyboardInterrupt):
            raise ValueError("Key setup cancelled. Your saved settings were not changed.") from None
        except (OSError, subprocess.SubprocessError, UnicodeError):
            raise ValueError(
                "Could not read clipboard. Your saved settings were not changed."
            ) from None
        # Some terminals pass bracketed-paste markers through to getpass.
        if key.startswith("\x1b[200~") and key.endswith("\x1b[201~"):
            key = key[len("\x1b[200~") : -len("\x1b[201~")].strip()
        key = re.sub(r"^(?:export\s+)?GEMINI_API_KEY\s*=\s*", "", key)
        if len(key) >= 2 and key[0] == key[-1] and key[0] in "\"'":
            key = key[1:-1].strip()
        if key.startswith(("bash ", "curl ", "python ", "python3 ")):
            raise ValueError(
                "The clipboard contains a command, not a key. Nothing was saved. "
                "Start setup first; copy the key when setup asks you to."
            )
        # Treat the credential as opaque. Gemini validates its format; locally
        # require only a nonempty printable ASCII token safe for a header/.env.
        if key and all(33 <= ord(character) <= 126 for character in key):
            break
        if not key:
            print("No key was received. Paste the key before pressing Enter.")
        elif any(character in key for character in "…•●"):
            print("The copied text appears masked or shortened. Copy the full secret key value.")
        elif any(character.isspace() for character in key):
            print("The input contains unsupported characters: embedded whitespace or line breaks.")
        elif not key.isascii():
            print("The input contains unsupported characters: non-ASCII text or invisible Unicode.")
        else:
            print("The input contains unsupported characters: terminal control characters.")
    else:
        raise ValueError(
            "Key setup stopped. Your saved settings were not changed."
            + (
                " Copy the key, then retry --setup-gemini-clipboard."
                if clipboard
                else " On Mac, you can bypass this prompt with --setup-gemini-clipboard."
            )
        )
    lines = path.read_text().splitlines() if path.exists() else []
    lines = [line for line in lines if line.split("=", 1)[0].strip() != "GEMINI_API_KEY"]
    lines.append(f"GEMINI_API_KEY={key}")
    # atomic_write uses a private 0600 temporary file and replaces the target.
    atomic_write(path, ("\n".join(lines) + "\n").encode())
    os.environ["GEMINI_API_KEY"] = key
    print(f"Gemini key saved locally to {path}. No API request has been sent.")
