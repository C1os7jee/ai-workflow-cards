"""CLI entry point for the Visual Agent MVP."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent.agent import VisualAgent
from agent.web_app import run as run_web_app


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ai-workflow-cards Visual Agent")
    parser.add_argument("--input", help="content goal or brief text")
    parser.add_argument(
        "--mode",
        choices=["visual-plan", "render-input", "record-feedback", "web"],
        default="visual-plan",
        help="output mode",
    )
    parser.add_argument(
        "--feedback-file",
        default="docs/memories/帖子表现记录.jsonl",
        help="path to feedback jsonl",
    )
    parser.add_argument("--post-id", help="post id for feedback mode")
    parser.add_argument("--topic", help="topic for feedback mode")
    parser.add_argument("--human-notes", help="human notes for feedback mode")
    parser.add_argument("--metrics-json", help="metrics as a JSON string")
    parser.add_argument("--host", default="127.0.0.1", help="web mode host")
    parser.add_argument("--port", type=int, default=8765, help="web mode port")
    return parser


def _load_metrics(metrics_json: str):
    if not metrics_json:
        return {}
    try:
        metrics = json.loads(metrics_json)
    except json.JSONDecodeError as exc:
        raise SystemExit("invalid --metrics-json: %s" % exc)
    if not isinstance(metrics, dict):
        raise SystemExit("--metrics-json must decode to an object")
    return metrics


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.mode == "web":
        run_web_app(host=args.host, port=args.port)
        return 0

    if not args.input:
        parser.error("--input is required unless --mode web is used")

    agent = VisualAgent()
    plan = agent.generate_plan(args.input)

    if args.mode == "visual-plan":
        print(json.dumps(plan.to_dict(), ensure_ascii=False, indent=2))
        return 0

    if args.mode == "render-input":
        payload = agent.to_render_payload(plan)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    if not args.post_id or not args.topic or not args.human_notes:
        parser.error("--post-id, --topic, and --human-notes are required for record-feedback mode")

    feedback_path = Path(args.feedback_file)
    agent.record_feedback(
        feedback_path=feedback_path,
        post_id=args.post_id,
        topic=args.topic,
        plan=plan,
        metrics=_load_metrics(args.metrics_json),
        human_notes=args.human_notes,
    )
    print(
        json.dumps(
            {"success": True, "feedback_file": str(feedback_path)},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
