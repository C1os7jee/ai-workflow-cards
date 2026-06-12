"""Render Xiaohongshu card decks to PNG with a local HTML runtime.

This is a minimal in-repo runtime skill following the planned social-card
skill shape: render JSON -> HTML deck -> browser screenshots -> PNG paths.
"""

from __future__ import annotations

import argparse
import base64
import functools
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


SKILL_ROOT = Path(__file__).resolve().parent
TEMPLATE_PATH = SKILL_ROOT / "template.html"
CONFIG_PATH = SKILL_ROOT / "skill.json"
DEFAULT_OUTPUT_ROOT = SKILL_ROOT.parents[1] / "output"
PROJECT_ROOT = SKILL_ROOT.parents[1]
ENV_PATH = PROJECT_ROOT / ".env"


def render_deck(payload: Dict[str, Any], output_root: Path = DEFAULT_OUTPUT_ROOT) -> Dict[str, Any]:
    task_dir = output_root / ("task_%s" % int(time.time() * 1000))
    task_dir.mkdir(parents=True, exist_ok=True)
    config = _load_skill_config()
    prepared_payload = dict(payload)
    generated_assets = _generate_model_assets(prepared_payload, task_dir, config)
    if _uses_direct_image_deck(prepared_payload):
        png_paths = [Path(path) for path in generated_assets.get("deck_images", [])]
        html_paths: List[Path] = []
    else:
        html_paths = _write_slide_html(prepared_payload, task_dir)
        png_paths = _capture_pngs(html_paths, task_dir)
    result = {
        "success": True,
        "png_paths": [str(path) for path in png_paths],
        "task_dir": str(task_dir),
        "generated_assets": generated_assets,
    }
    (task_dir / "render_input.json").write_text(
        json.dumps(prepared_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (task_dir / "render_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return result


def _write_slide_html(payload: Dict[str, Any], task_dir: Path) -> List[Path]:
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    paths = []
    slides = payload.get("slides", [])
    for index, slide in enumerate(slides, start=1):
        html = template.replace("__DECK_JSON__", json.dumps(payload, ensure_ascii=False))
        html = html.replace("__SLIDE_INDEX__", str(index - 1))
        html_path = task_dir / ("slide_%02d.html" % index)
        html_path.write_text(html, encoding="utf-8")
        paths.append(html_path)
    return paths


def _load_skill_config() -> Dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {}
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def _load_env() -> Dict[str, str]:
    values: Dict[str, str] = {}
    if not ENV_PATH.exists():
        return values
    for raw_line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _generate_model_assets(
    payload: Dict[str, Any],
    task_dir: Path,
    config: Dict[str, Any],
) -> Dict[str, str]:
    image_config = _image_provider_config(config, payload)
    if not image_config:
        return {}
    if _uses_direct_image_deck(payload):
        return _generate_direct_image_deck(payload, task_dir, image_config)
    mode = image_config.get("mode", "cover")
    if mode != "cover":
        raise RuntimeError("unsupported image_generation.mode: %s" % mode)
    prompt = _build_image_prompt(payload, image_config)
    image_path = task_dir / "generated_cover.png"
    try:
        _call_image_provider(prompt, image_path, image_config)
    except Exception:
        if image_config.get("fail_on_error", True):
            raise
        return {}
    payload["generated_cover_image"] = image_path.name
    payload["image_provider"] = str(image_config.get("id", ""))
    (task_dir / "image_prompt.txt").write_text(prompt, encoding="utf-8")
    return {
        "cover_image": str(image_path),
        "image_prompt": str(task_dir / "image_prompt.txt"),
        "image_provider": str(image_config.get("id", "")),
    }


def _uses_direct_image_deck(payload: Dict[str, Any]) -> bool:
    blueprint = payload.get("visual_blueprint", {})
    if not isinstance(blueprint, dict):
        return False
    return blueprint.get("mode") == "direct-image-deck"


def _generate_direct_image_deck(
    payload: Dict[str, Any],
    task_dir: Path,
    image_config: Dict[str, Any],
) -> Dict[str, Any]:
    blueprint = payload.get("visual_blueprint", {})
    if not isinstance(blueprint, dict):
        raise RuntimeError("visual_blueprint is required for direct-image-deck")
    jobs = blueprint.get("image_jobs", [])
    if not isinstance(jobs, list) or not jobs:
        raise RuntimeError("visual_blueprint.image_jobs must not be empty")
    prompt_manifest = []
    png_paths = []
    for index, raw_job in enumerate(jobs, start=1):
        if not isinstance(raw_job, dict):
            raise RuntimeError("image job %s is invalid" % index)
        prompt = str(raw_job.get("prompt", "")).strip()
        if not prompt:
            raise RuntimeError("image job %s missing prompt" % index)
        output_name = _safe_png_name(str(raw_job.get("output_name", "card_%02d.png" % index)))
        image_path = task_dir / output_name
        try:
            _call_image_provider(prompt, image_path, image_config)
        except Exception:
            if image_config.get("fail_on_error", True):
                raise
            continue
        png_paths.append(str(image_path))
        prompt_manifest.append(
            {
                "id": str(raw_job.get("id", "card_%02d" % index)),
                "role": str(raw_job.get("role", "")),
                "title": str(raw_job.get("title", "")),
                "image": image_path.name,
                "prompt": prompt,
            }
        )
    if not png_paths and image_config.get("fail_on_error", True):
        raise RuntimeError("direct image deck did not produce any images")
    prompt_path = task_dir / "image_prompts.json"
    prompt_path.write_text(json.dumps(prompt_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    payload["image_provider"] = str(image_config.get("id", ""))
    payload["generated_deck_images"] = [Path(path).name for path in png_paths]
    return {
        "deck_images": png_paths,
        "image_prompts": str(prompt_path),
        "image_provider": str(image_config.get("id", "")),
    }


def _safe_png_name(value: str) -> str:
    name = Path(value).name
    if not name:
        name = "card.png"
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", name)
    if not stem.lower().endswith(".png"):
        stem += ".png"
    return stem


def _build_image_prompt(payload: Dict[str, Any], image_config: Dict[str, Any]) -> str:
    slides = payload.get("slides", [])
    cover = slides[0] if slides else {}
    context = {
        "deck_title": str(cover.get("title", "")),
        "deck_hook": str(cover.get("hook", "")),
        "visual_direction": str(payload.get("visual_direction", "")),
        "style": str(payload.get("style", "")),
        "theme": str(payload.get("theme", "")),
    }
    template = image_config.get("prompt_template", "{deck_title}. {deck_hook}. {visual_direction}")
    prompt = str(template)
    for key, value in context.items():
        prompt = prompt.replace("{%s}" % key, value)
    return prompt


def _image_provider_config(config: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    image_generation = config.get("image_generation", {})
    if not isinstance(image_generation, dict) or not image_generation.get("enabled"):
        return {}
    providers = image_generation.get("providers")
    provider_id = str(
        payload.get("image_provider")
        or image_generation.get("default_provider")
        or image_generation.get("provider")
        or "volcengine-seedream"
    ).strip()
    if isinstance(providers, dict) and providers:
        provider_config = providers.get(provider_id)
        if not isinstance(provider_config, dict):
            raise RuntimeError("unknown image provider: %s" % provider_id)
        merged = {
            key: value
            for key, value in image_generation.items()
            if key not in {"providers", "default_provider"}
        }
        merged.update(provider_config)
        merged["id"] = provider_id
        return merged
    legacy = dict(image_generation)
    legacy["id"] = provider_id
    legacy.setdefault("transport", legacy.get("provider", "volcengine-seedream"))
    return legacy


def _call_image_provider(
    prompt: str,
    output_path: Path,
    image_config: Dict[str, Any],
) -> None:
    transport = str(
        image_config.get("transport")
        or image_config.get("provider")
        or image_config.get("id", "volcengine-seedream")
    )
    if transport in {"openai-compatible", "openai"}:
        _call_openai_compatible_image_api(prompt, output_path, image_config)
        return
    if transport in {"volcengine-seedream", "seedream", "volcengine"}:
        _call_volcengine_seedream_image_api(prompt, output_path, image_config)
        return
    raise RuntimeError("unsupported image provider transport: %s" % transport)


def _call_openai_compatible_image_api(
    prompt: str,
    output_path: Path,
    image_config: Dict[str, Any],
) -> None:
    env = _load_env()
    api_key_env = str(image_config.get("api_key_env", "OPENAI_API_KEY"))
    api_key = env.get(api_key_env, "")
    default_base_url = str(image_config.get("default_base_url", "https://api.openai.com"))
    base_url = env.get(str(image_config.get("base_url_env", "OPENAI_BASE_URL")), default_base_url).rstrip("/")
    model = env.get(str(image_config.get("model_env", "OPENAI_IMAGE_MODEL")), "") or str(
        image_config.get("default_model", "gpt-image-1")
    )
    if not api_key:
        raise RuntimeError("%s is required for real image generation" % api_key_env)
    request_payload = {
        "model": model,
        "prompt": prompt,
        "size": str(image_config.get("size", "1024x1024")),
        "n": 1,
    }
    quality = image_config.get("quality")
    if quality:
        request_payload["quality"] = str(quality)
    url = base_url + str(image_config.get("endpoint", "/v1/images/generations"))
    data = _post_image_generation_request(url, api_key, request_payload)
    image_data = _first_image_data(data)
    output_path.write_bytes(base64.b64decode(image_data))


def _call_volcengine_seedream_image_api(
    prompt: str,
    output_path: Path,
    image_config: Dict[str, Any],
) -> None:
    env = _load_env()
    request_data = _volcengine_seedream_request_data(prompt, image_config, env)
    data = _post_image_generation_request(
        request_data["url"],
        request_data["api_key"],
        request_data["payload"],
    )
    image_data = _first_image_data(data)
    output_path.write_bytes(base64.b64decode(image_data))


def _volcengine_seedream_request_data(
    prompt: str,
    image_config: Dict[str, Any],
    env: Dict[str, str],
) -> Dict[str, Any]:
    api_key_env = str(image_config.get("api_key_env", "ARK_API_KEY"))
    api_key = env.get(api_key_env, "")
    if not api_key:
        raise RuntimeError("%s is required for real image generation" % api_key_env)
    default_base_url = str(
        image_config.get("default_base_url", "https://ark.cn-beijing.volces.com/api/v3")
    )
    base_url = env.get(str(image_config.get("base_url_env", "ARK_BASE_URL")), default_base_url).rstrip("/")
    model = env.get(str(image_config.get("model_env", "ARK_IMAGE_MODEL")), "") or str(
        image_config.get("default_model", "doubao-seedream-5-0-260128")
    )
    request_payload: Dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "size": str(image_config.get("size", "2K")),
        "output_format": str(image_config.get("output_format", "png")),
        "response_format": str(image_config.get("response_format", "b64_json")),
        "watermark": bool(image_config.get("watermark", False)),
    }
    sequential = image_config.get("sequential_image_generation")
    if sequential:
        request_payload["sequential_image_generation"] = str(sequential)
    return {
        "url": base_url + str(image_config.get("endpoint", "/images/generations")),
        "api_key": api_key,
        "payload": request_payload,
    }


def _post_image_generation_request(
    url: str,
    api_key: str,
    request_payload: Dict[str, Any],
) -> Dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(request_payload).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError("image generation failed: HTTP %s %s" % (exc.code, body[:500]))
    except urllib.error.URLError as exc:
        raise RuntimeError("image generation failed: %s" % exc)
    if not isinstance(data, dict):
        raise RuntimeError("image generation response must be a JSON object")
    return data


def _first_image_data(data: Dict[str, Any]) -> str:
    items = data.get("data", [])
    if not isinstance(items, list) or not items:
        raise RuntimeError("image generation response did not include data")
    first = items[0]
    if not isinstance(first, dict):
        raise RuntimeError("image generation response item is invalid")
    if first.get("b64_json"):
        return str(first["b64_json"])
    if first.get("url"):
        with urllib.request.urlopen(str(first["url"]), timeout=120) as response:
            return base64.b64encode(response.read()).decode("ascii")
    raise RuntimeError("image generation response did not include b64_json or url")


def _capture_pngs(html_paths: List[Path], task_dir: Path) -> List[Path]:
    chrome = _find_chrome()
    png_paths = []
    with tempfile.TemporaryDirectory() as user_data_dir:
        server, port = _serve_directory(task_dir)
        try:
            for index, html_path in enumerate(html_paths, start=1):
                png_path = task_dir / ("slide_%02d.png" % index)
                url = "http://127.0.0.1:%s/%s" % (port, html_path.name)
                cmd = [
                    chrome,
                    "--headless=new",
                    "--disable-gpu",
                    "--window-size=1080,1440",
                    "--screenshot=%s" % png_path.resolve(),
                    url,
                ]
                completed = subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=25,
                )
                if completed.returncode != 0:
                    raise RuntimeError(
                        "Chrome render failed for %s: %s"
                        % (html_path, completed.stderr.strip())
                    )
                png_paths.append(png_path)
        finally:
            server.shutdown()
    return png_paths


def _serve_directory(directory: Path):
    handler = functools.partial(QuietRequestHandler, directory=str(directory.resolve()))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, server.server_address[1]


class QuietRequestHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        return


def _find_chrome() -> str:
    candidates = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        shutil.which("google-chrome"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return str(candidate)
    raise RuntimeError("Chrome or Chromium is required to render cards")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="render payload JSON path")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_ROOT), help="output root")
    args = parser.parse_args()

    try:
        payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
        result = render_deck(payload, output_root=Path(args.output))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
