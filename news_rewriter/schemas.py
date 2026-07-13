"""输入输出数据结构。"""
from dataclasses import dataclass, field, asdict
from typing import Literal, Optional
import json
import uuid
from datetime import datetime


SourceType = Literal["url", "pdf", "image", "doc", "text"]


@dataclass
class ExtractedContent:
    source_type: SourceType
    origin: str
    title: Optional[str]
    body: str
    publish_date: Optional[str] = None
    author: Optional[str] = None
    extract_method: str = ""
    warnings: list[str] = field(default_factory=list)


@dataclass
class ExtractResult:
    """提取的统一返回。永远成功返回,失败用 success=False。"""
    success: bool
    content: Optional[ExtractedContent] = None
    error: Optional[str] = None
    fallback_used: bool = False   # 是否走了降级路径(如 PDF → OCR)


@dataclass
class FactAnchors:
    tools: list[str] = field(default_factory=list)
    numbers: list[str] = field(default_factory=list)
    features: list[str] = field(default_factory=list)
    people_orgs: list[str] = field(default_factory=list)
    claims: list[str] = field(default_factory=list)
    raw_text_summary: str = ""


@dataclass
class Recommendation:
    worth_writing: bool
    angle: str
    risk_level: Literal["low", "medium", "high"]
    note: str = ""


@dataclass
class RewriteDraft:
    title_candidates: list[str] = field(default_factory=list)
    opening_candidates: list[str] = field(default_factory=list)
    body: str = ""
    ending_options: dict[str, str] = field(default_factory=dict)
    fabricated_segments: list[str] = field(default_factory=list)


@dataclass
class SelfCheck:
    title_formula_pass: bool = False
    opening_banned_words: list[str] = field(default_factory=list)
    body_banned_words: list[str] = field(default_factory=list)
    fact_ok: bool = True
    fact_issues: list[str] = field(default_factory=list)
    fabrication_count: int = 0
    warnings: list[str] = field(default_factory=list)


@dataclass
class StepTrace:
    """每一步的执行痕迹,用于排查问题。"""
    step_name: str
    started_at: str
    duration_ms: int
    success: bool
    retries: int = 0
    input_summary: str = ""        # 输入摘要(不存全文,省空间)
    output_summary: str = ""       # 输出摘要
    raw_prompt: str = ""           # 完整 prompt(只在 verbose 模式存)
    raw_response: str = ""         # 模型原始输出
    error: Optional[str] = None
    issues: list[str] = field(default_factory=list)


@dataclass
class RewriteResult:
    """最终输出包。"""
    run_id: str
    source: dict
    fact_anchors: FactAnchors
    recommendation: Recommendation
    draft: RewriteDraft
    self_check: SelfCheck
    traces: list[StepTrace] = field(default_factory=list)
    created_at: str = ""

    @staticmethod
    def new_run_id() -> str:
        return f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

    def to_json(self, indent: int = 2, with_traces: bool = False) -> str:
        d = asdict(self)
        if not with_traces:
            d.pop("traces", None)
        return json.dumps(d, ensure_ascii=False, indent=indent)

    def to_post_package(self) -> dict:
        """返回供后续小红书帖子生成使用的精简数据包。"""
        source_url = (
            self.source.get("origin")
            if self.source.get("type") == "url"
            else None
        )
        return {
            "run_id": self.run_id,
            "source": {
                "url": source_url,
                "title": self.source.get("original_title"),
            },
            "post_draft": {
                "title_candidates": self.draft.title_candidates,
                "opening_candidates": self.draft.opening_candidates,
                "body": self.draft.body,
                "ending_options": self.draft.ending_options,
            },
            "review": {
                "risk_level": self.recommendation.risk_level,
                "fact_ok": self.self_check.fact_ok,
                "warnings": self.self_check.warnings,
                "fabricated_segments": self.draft.fabricated_segments,
            },
            "fact_guardrails": {
                "summary": self.fact_anchors.raw_text_summary,
                "numbers": self.fact_anchors.numbers,
                "must_not_change": self.fact_anchors.features,
            },
        }
