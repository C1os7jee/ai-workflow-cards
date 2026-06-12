"""Local configuration helpers.

Secrets are loaded from `.env`, which is ignored by git. This module deliberately
does not print secret values.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT_ROOT / ".env"


def load_env(path: Path = ENV_PATH) -> Dict[str, str]:
    values: Dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def openai_base_url() -> str:
    values = load_env()
    return values.get("OPENAI_BASE_URL", "https://api.openai.com").rstrip("/")


def openai_api_key() -> str:
    return load_env().get("OPENAI_API_KEY", "")


def openai_image_model() -> str:
    return load_env().get("OPENAI_IMAGE_MODEL", "gpt-image-2")

