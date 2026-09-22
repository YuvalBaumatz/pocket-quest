"""Image-edit adapters. No credentials, SDK clients or network work at import time."""

import base64
import json
import math
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from io import BytesIO
from typing import Any, Protocol

from PIL import Image, ImageOps

from .storage import encode

MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_RESPONSE_BYTES = 30 * 1024 * 1024


class EditError(Exception):
    """A safe error code, never a raw provider response or credential."""

    def __init__(self, code: str, *, unknown: bool = False, retry_after: float | None = None):
        super().__init__(code)
        self.code, self.unknown, self.retry_after = code, unknown, retry_after


@dataclass(frozen=True)
class EditRequest:
    image: bytes
    prompt: str
    model: str


class Provider(Protocol):
    def edit(self, request: EditRequest) -> bytes: ...


def validated_png(payload: bytes) -> bytes:
    if not payload or len(payload) > MAX_IMAGE_BYTES:
        raise EditError("invalid_image")
    try:
        with Image.open(BytesIO(payload)) as image:
            if (
                image.format not in ("PNG", "JPEG", "WEBP")
                or image.width * image.height > 16_000_000
            ):
                raise EditError("invalid_image")
            return encode(image.convert("RGB"))
    except (OSError, ValueError, Image.DecompressionBombError) as error:
        raise EditError("invalid_image") from error


def decode_image(value: str) -> bytes:
    if len(value) > MAX_RESPONSE_BYTES:
        raise EditError("invalid_image")
    try:
        return validated_png(base64.b64decode(value, validate=True))
    except ValueError as error:
        raise EditError("invalid_image") from error


def http_error(status: int, retry_after: str | None = None) -> EditError:
    if status == 429:
        try:
            delay = max(1.0, float(retry_after or "30"))
        except ValueError:
            try:
                delay = max(1.0, parsedate_to_datetime(retry_after or "").timestamp() - time.time())
            except (ValueError, TypeError, OverflowError):
                delay = 30.0
        if not math.isfinite(delay):
            delay = 30.0
        return EditError("rate_limit", retry_after=delay)
    if status in (401, 403):
        return EditError("credentials")
    if status >= 500 or status == 408:
        return EditError("provider_uncertain", unknown=True)
    return EditError("request_rejected")


class DemoProvider:
    """Explicit local stand-in, not an AI result. Useful without credentials."""

    def edit(self, request: EditRequest) -> bytes:
        with Image.open(BytesIO(request.image)) as image:
            colored = ImageOps.colorize(ImageOps.grayscale(image), "#19766F", "#F5BD4F")
            return encode(ImageOps.expand(colored, border=12, fill="#FFF2D3"))


class OpenAIProvider:
    def __init__(self, client: Any = None) -> None:
        self.client = client

    def edit(self, request: EditRequest) -> bytes:
        try:
            import openai
        except ImportError as error:
            raise EditError("install_openai") from error
        if self.client is None:
            key = os.environ.get("OPENAI_API_KEY", "").strip()
            if not key:
                raise EditError("credentials")
            self.client = openai.OpenAI(api_key=key, timeout=90.0, max_retries=0)
        try:
            result = self.client.images.edit(
                model=request.model,
                image=("photo.png", request.image, "image/png"),
                prompt=request.prompt,
                size="1024x1024",
                quality="low",
                output_format="png",
            )
            if not result.data or not result.data[0].b64_json:
                raise EditError("no_image")
            return decode_image(result.data[0].b64_json)
        except openai.APIStatusError as error:
            raise http_error(error.status_code, error.response.headers.get("retry-after")) from None
        except (openai.APIConnectionError, TimeoutError) as error:
            raise EditError("connection_uncertain", unknown=True) from error


class GeminiProvider:
    def edit(self, request: EditRequest) -> bytes:
        key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not key:
            raise EditError("credentials")
        if not re.fullmatch(r"[A-Za-z0-9._-]+", request.model):
            raise EditError("invalid_model")
        body = {
            "contents": [
                {
                    "parts": [
                        {"text": request.prompt},
                        {
                            "inlineData": {
                                "mimeType": "image/png",
                                "data": base64.b64encode(request.image).decode(),
                            }
                        },
                    ]
                }
            ],
            "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
        }
        http_request = urllib.request.Request(
            f"https://generativelanguage.googleapis.com/v1beta/models/{request.model}:generateContent",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", "x-goog-api-key": key},
            method="POST",
        )
        try:
            with urllib.request.urlopen(http_request, timeout=90) as response:
                payload = response.read(MAX_RESPONSE_BYTES + 1)
            if len(payload) > MAX_RESPONSE_BYTES:
                raise EditError("invalid_image")
            data = json.loads(payload)
            for candidate in data.get("candidates", []):
                for part in candidate.get("content", {}).get("parts", []):
                    image = part.get("inlineData", {})
                    if str(image.get("mimeType", "")).startswith("image/"):
                        return decode_image(image["data"])
            raise EditError("no_image")
        except urllib.error.HTTPError as error:
            raise http_error(error.code, error.headers.get("Retry-After")) from None
        except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
            raise EditError("connection_uncertain", unknown=True) from error
        except (ValueError, KeyError, TypeError, AttributeError) as error:
            raise EditError("invalid_response") from error


def provider_for(name: str) -> Provider:
    factories = {"demo": DemoProvider, "openai": OpenAIProvider, "gemini": GeminiProvider}
    if name not in factories:
        raise ValueError("Unknown provider")
    return factories[name]()
