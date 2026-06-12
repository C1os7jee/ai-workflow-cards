"""Structured data models for the Visual Agent MVP.

The project currently uses the standard library only so the skeleton can run
in the provided environment. The models below keep the public contract explicit
and easy to validate.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


class SchemaValidationError(ValueError):
    """Raised when a structured object fails validation."""


def _ensure_non_empty(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SchemaValidationError(f"{field_name} must be a non-empty string")
    return value.strip()


def _ensure_limit(value: str, field_name: str, limit: int) -> str:
    value = _ensure_non_empty(value, field_name)
    if len(value) > limit:
        raise SchemaValidationError(
            f"{field_name} must be <= {limit} characters, got {len(value)}"
        )
    return value


@dataclass
class VisualCoverDirection:
    title: str
    hook: str
    visual: str

    def validate(self) -> "VisualCoverDirection":
        self.title = _ensure_limit(self.title, "cover.title", 15)
        self.hook = _ensure_limit(self.hook, "cover.hook", 30)
        self.visual = _ensure_non_empty(self.visual, "cover.visual")
        return self


@dataclass
class VisualPlan:
    content_goal: str
    recommended_strategy: str
    alternatives: List[str] = field(default_factory=list)
    reason: str = ""
    image_provider: str = ""
    cover_direction: Optional[VisualCoverDirection] = None
    slides_plan: List[str] = field(default_factory=list)
    render_input_snapshot: Dict[str, Any] = field(default_factory=dict)
    risk: str = ""
    human_checkpoints: List[str] = field(default_factory=list)

    def validate(self) -> "VisualPlan":
        self.content_goal = _ensure_non_empty(self.content_goal, "content_goal")
        self.recommended_strategy = _ensure_non_empty(
            self.recommended_strategy, "recommended_strategy"
        )
        self.alternatives = [
            _ensure_non_empty(item, "alternatives item") for item in self.alternatives
        ]
        self.reason = _ensure_non_empty(self.reason, "reason")
        self.slides_plan = [
            _ensure_non_empty(item, "slides_plan item") for item in self.slides_plan
        ]
        self.risk = _ensure_non_empty(self.risk, "risk")
        self.human_checkpoints = [
            _ensure_non_empty(item, "human_checkpoints item")
            for item in self.human_checkpoints
        ]
        if self.cover_direction is None:
            raise SchemaValidationError("cover_direction is required")
        self.cover_direction.validate()
        return self

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        if self.cover_direction is not None:
            data["cover_direction"] = asdict(self.cover_direction)
        return data


@dataclass
class RenderSlide:
    type: str
    title: Optional[str] = None
    hook: Optional[str] = None
    heading: Optional[str] = None
    points: List[str] = field(default_factory=list)
    text: Optional[str] = None

    def validate(self) -> "RenderSlide":
        self.type = _ensure_non_empty(self.type, "slide.type")
        if self.type == "cover":
            self.title = _ensure_limit(self.title or "", "cover.title", 15)
            self.hook = _ensure_limit(self.hook or "", "cover.hook", 30)
        elif self.type == "content":
            self.heading = _ensure_limit(self.heading or "", "content.heading", 12)
            if not (2 <= len(self.points) <= 3):
                raise SchemaValidationError(
                    "content.points must contain 2 or 3 items"
                )
            self.points = [
                _ensure_limit(point, "content.points item", 20) for point in self.points
            ]
        elif self.type == "cta":
            self.text = _ensure_limit(self.text or "", "cta.text", 20)
        else:
            raise SchemaValidationError(f"unsupported slide type: {self.type}")
        return self

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        if self.type == "cover":
            return {
                "type": self.type,
                "title": data["title"],
                "hook": data["hook"],
            }
        if self.type == "content":
            return {
                "type": self.type,
                "heading": data["heading"],
                "points": data["points"],
            }
        return {"type": self.type, "text": data["text"]}


@dataclass
class RenderInput:
    style: str
    theme: str
    layout_id: str
    slides: List[RenderSlide]
    visual_direction: str = ""
    image_provider: str = ""
    visual_blueprint: Dict[str, Any] = field(default_factory=dict)

    def validate(self) -> "RenderInput":
        self.style = _ensure_non_empty(self.style, "style")
        self.theme = _ensure_non_empty(self.theme, "theme")
        self.layout_id = _ensure_non_empty(self.layout_id, "layout_id")
        if not self.slides:
            raise SchemaValidationError("slides must not be empty")
        for slide in self.slides:
            slide.validate()
        if self.slides[0].type != "cover":
            raise SchemaValidationError("first slide must be cover")
        if self.slides[-1].type != "cta":
            raise SchemaValidationError("last slide must be cta")
        return self

    def to_dict(self) -> Dict[str, Any]:
        return {
            "style": self.style,
            "theme": self.theme,
            "layout_id": self.layout_id,
            "visual_direction": self.visual_direction,
            "image_provider": self.image_provider,
            "visual_blueprint": self.visual_blueprint,
            "slides": [slide.to_dict() for slide in self.slides],
        }


@dataclass
class FeedbackRecord:
    post_id: str
    topic: str
    visual_strategy: str
    cover_type: str
    metrics: Dict[str, Any]
    human_notes: str
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def validate(self) -> "FeedbackRecord":
        self.post_id = _ensure_non_empty(self.post_id, "post_id")
        self.topic = _ensure_non_empty(self.topic, "topic")
        self.visual_strategy = _ensure_non_empty(
            self.visual_strategy, "visual_strategy"
        )
        self.cover_type = _ensure_non_empty(self.cover_type, "cover_type")
        if not isinstance(self.metrics, dict):
            raise SchemaValidationError("metrics must be a dict")
        self.human_notes = _ensure_non_empty(self.human_notes, "human_notes")
        self.created_at = _ensure_non_empty(self.created_at, "created_at")
        return self

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
