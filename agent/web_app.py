"""Small local web app for operating the Visual Agent.

This intentionally uses the Python standard library. It gives the user a local
operator console without adding a framework dependency before the workflow is
stable.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Tuple
from urllib.parse import unquote

from agent.agent import VisualAgent
from agent.tools.openai_provider import check_openai_compatible_api


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = PROJECT_ROOT / "web"
DEFAULT_FEEDBACK_PATH = PROJECT_ROOT / "docs" / "memories" / "帖子表现记录.jsonl"


def build_visual_response(
    content_goal: str,
    image_provider: str = "",
    planner_mode: str = "",
) -> Dict[str, Any]:
    agent = VisualAgent()
    plan = agent.generate_plan(
        content_goal,
        image_provider=image_provider,
        planner_mode=planner_mode,
    )
    return {
        "visual_plan": plan.to_dict(),
        "render_input": agent.to_render_payload(plan),
    }


def render_deck_response(
    content_goal: str,
    image_provider: str = "",
    planner_mode: str = "ai",
) -> Dict[str, Any]:
    agent = VisualAgent()
    plan = agent.generate_plan(
        content_goal,
        image_provider=image_provider,
        planner_mode=planner_mode,
    )
    result = agent.generate_deck(plan)
    result["visual_plan"] = plan.to_dict()
    return result


def record_feedback(payload: Dict[str, Any], feedback_path: Path = DEFAULT_FEEDBACK_PATH) -> Dict[str, Any]:
    content_goal = _required_string(payload, "content_goal")
    post_id = _required_string(payload, "post_id")
    topic = _required_string(payload, "topic")
    human_notes = _required_string(payload, "human_notes")
    metrics = payload.get("metrics", {})
    if not isinstance(metrics, dict):
        raise ValueError("metrics must be an object")

    agent = VisualAgent()
    plan = agent.generate_plan(content_goal)
    agent.record_feedback(
        feedback_path=feedback_path,
        post_id=post_id,
        topic=topic,
        plan=plan,
        metrics=metrics,
        human_notes=human_notes,
    )
    return {"success": True, "feedback_file": str(feedback_path)}


def _required_string(payload: Dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError("%s is required" % key)
    return value.strip()


def _optional_string(payload: Dict[str, Any], key: str) -> str:
    value = payload.get(key, "")
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError("%s must be a string" % key)
    return value.strip()


class VisualAgentRequestHandler(BaseHTTPRequestHandler):
    server_version = "VisualAgentHTTP/0.1"

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/":
            self._send_file(WEB_ROOT / "index.html")
            return
        if path.startswith("/web/"):
            relative = unquote(path[len("/web/") :])
            self._send_file(WEB_ROOT / relative)
            return
        if path.startswith("/output/"):
            relative = unquote(path[len("/output/") :])
            self._send_file(PROJECT_ROOT / "output" / relative)
            return
        self._send_json({"error": "not found"}, status=404)

    def do_POST(self) -> None:
        try:
            payload = self._read_json()
            if self.path == "/api/plan":
                content_goal = _required_string(payload, "content_goal")
                self._send_json(
                    build_visual_response(
                        content_goal,
                        image_provider=_optional_string(payload, "image_provider"),
                        planner_mode=_optional_string(payload, "planner_mode"),
                    )
                )
                return
            if self.path == "/api/render-deck":
                content_goal = _required_string(payload, "content_goal")
                self._send_json(
                    render_deck_response(
                        content_goal,
                        image_provider=_optional_string(payload, "image_provider"),
                        planner_mode=_optional_string(payload, "planner_mode") or "ai",
                    )
                )
                return
            if self.path == "/api/check-provider":
                self._send_json(check_openai_compatible_api())
                return
            if self.path == "/api/feedback":
                self._send_json(record_feedback(payload))
                return
            self._send_json({"error": "not found"}, status=404)
        except ValueError as exc:
            self._send_json({"error": str(exc)}, status=400)
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=500)

    def log_message(self, format: str, *args: Tuple[Any, ...]) -> None:
        return

    def _read_json(self) -> Dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length).decode("utf-8")
        if not raw_body:
            return {}
        data = json.loads(raw_body)
        if not isinstance(data, dict):
            raise ValueError("request body must be a JSON object")
        return data

    def _send_json(self, payload: Dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path) -> None:
        resolved = path.resolve()
        output_root = (PROJECT_ROOT / "output").resolve()
        if (
            WEB_ROOT not in resolved.parents
            and resolved != WEB_ROOT
            and output_root not in resolved.parents
            and resolved != output_root
        ):
            self._send_json({"error": "invalid path"}, status=403)
            return
        if not resolved.exists() or not resolved.is_file():
            self._send_json({"error": "not found"}, status=404)
            return
        content_type = mimetypes.guess_type(str(resolved))[0] or "application/octet-stream"
        body = resolved.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def run(host: str = "127.0.0.1", port: int = 8765) -> None:
    server = ThreadingHTTPServer((host, port), VisualAgentRequestHandler)
    print("Visual Agent UI running at http://%s:%s" % (host, port))
    server.serve_forever()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Visual Agent local UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    run(host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
