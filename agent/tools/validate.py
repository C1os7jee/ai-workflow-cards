"""Validation and feedback helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from agent.schemas import (
    FeedbackRecord,
    RenderInput,
    SchemaValidationError,
    VisualPlan,
)


def validate_visual_plan(plan: VisualPlan) -> VisualPlan:
    return plan.validate()


def validate_render_input(render_input: RenderInput) -> RenderInput:
    return render_input.validate()


def append_feedback_record(path: Path, record: FeedbackRecord) -> None:
    record.validate()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record.to_dict(), ensure_ascii=False))
        handle.write("\n")


def read_feedback_records(path: Path) -> Iterable[FeedbackRecord]:
    if not path.exists():
        return []
    records = []
    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            data = json.loads(raw_line)
            record = FeedbackRecord(
                post_id=data["post_id"],
                topic=data["topic"],
                visual_strategy=data["visual_strategy"],
                cover_type=data["cover_type"],
                metrics=data["metrics"],
                human_notes=data["human_notes"],
                created_at=data.get("created_at", ""),
            )
            records.append(record.validate())
    return records
