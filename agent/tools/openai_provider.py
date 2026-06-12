"""OpenAI-compatible API helpers."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Dict, List

from agent.config import openai_api_key, openai_base_url


def list_models() -> List[str]:
    api_key = openai_api_key()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")
    url = openai_base_url() + "/v1/models"
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": "Bearer " + api_key,
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "OpenAI/Python 1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError("model list failed: HTTP %s %s" % (exc.code, body[:300]))
    return [
        item["id"]
        for item in payload.get("data", [])
        if isinstance(item, dict) and item.get("id")
    ]


def check_openai_compatible_api() -> Dict[str, object]:
    models = list_models()
    return {
        "success": True,
        "base_url": openai_base_url(),
        "model_count": len(models),
        "models": models,
    }

