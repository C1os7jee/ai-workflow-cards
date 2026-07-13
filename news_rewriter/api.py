"""FastAPI test server for the news rewriter agent."""
from __future__ import annotations

import asyncio
import os
import sys
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


MODULE_DIR = Path(__file__).resolve().parent
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))

from agent import NewsRewriteAgent  # noqa: E402
from extractor import Extractor  # noqa: E402
from llm_client import load_env_file  # noqa: E402
from state import AgentState  # noqa: E402


ApiSourceType = Literal["auto", "url", "pdf", "image", "doc", "text"]


class ExtractRequest(BaseModel):
    source: str = Field(..., min_length=1)
    source_type: ApiSourceType = "auto"


class RewriteRequest(BaseModel):
    source: str = Field(..., min_length=1)
    source_type: ApiSourceType = "auto"
    api_key: str | None = Field(default=None, repr=False)
    base_url: str | None = None
    model: str | None = None
    state_dir: str = "./news_rewriter_state"
    db_path: str | None = None
    log_dir: str = "./logs"
    verbose: bool = False
    with_traces: bool = Field(
        default=False,
        description="兼容旧请求；traces 仅保存在本地完整运行记录中。",
    )


class PublishedRequest(BaseModel):
    run_id: str = Field(..., min_length=1)
    final_title: str = Field(..., min_length=1)
    final_body: str = Field(..., min_length=1)
    rating: str = "good"
    notes: str = ""
    state_dir: str = "./news_rewriter_state"
    db_path: str | None = None


class SourceResponse(BaseModel):
    url: str | None = None
    title: str | None = None


class PostDraftResponse(BaseModel):
    title_candidates: list[str] = Field(default_factory=list)
    opening_candidates: list[str] = Field(default_factory=list)
    body: str = ""
    ending_options: dict[str, str] = Field(default_factory=dict)


class ReviewResponse(BaseModel):
    risk_level: Literal["low", "medium", "high"]
    fact_ok: bool
    warnings: list[str] = Field(default_factory=list)
    fabricated_segments: list[str] = Field(default_factory=list)


class FactGuardrailsResponse(BaseModel):
    summary: str = ""
    numbers: list[str] = Field(default_factory=list)
    must_not_change: list[str] = Field(default_factory=list)


class RewriteResponse(BaseModel):
    run_id: str
    source: SourceResponse
    post_draft: PostDraftResponse
    review: ReviewResponse
    fact_guardrails: FactGuardrailsResponse


app = FastAPI(
    title="News Rewriter Test API",
    description="Local test API for extracting and rewriting news into Xiaohongshu-style drafts.",
    version="0.1.0",
)


def _to_dict(value: Any) -> Any:
    if value is None:
        return None
    if is_dataclass(value):
        return asdict(value)
    return value


def _optional_config(value: str | None) -> str | None:
    if value is None:
        return None
    clean = value.strip()
    if not clean or clean.lower() in {"string", "none", "null"}:
        return None
    return clean


def _rewrite_sync(payload: RewriteRequest) -> dict[str, Any]:
    agent = NewsRewriteAgent(
        api_key=_optional_config(payload.api_key),
        base_url=_optional_config(payload.base_url),
        model=_optional_config(payload.model),
        state_dir=payload.db_path or payload.state_dir,
        log_dir=payload.log_dir,
        verbose=payload.verbose,
    )
    try:
        result = agent.run(payload.source, source_type=payload.source_type)
        return result.to_post_package()
    finally:
        agent.close()


@app.get("/")
def root() -> dict[str, str]:
    return {
        "service": "news_rewriter",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health")
def health() -> dict[str, Any]:
    load_env_file()
    return {
        "ok": True,
        "llm_configured": bool(os.getenv("LLM_API_KEY") or os.getenv("DEEPSEEK_API_KEY")),
        "default_base_url": os.getenv("LLM_BASE_URL") or os.getenv("DEEPSEEK_BASE_URL") or "https://api.deepseek.com",
        "default_model": (
            os.getenv("LLM_MODEL")
            or os.getenv("DEEPSEEK_MODEL")
            or os.getenv("DEEPSEEK_TEXT_MODEL")
            or "deepseek-chat"
        ),
    }


@app.post("/extract")
def extract(payload: ExtractRequest) -> dict[str, Any]:
    result = Extractor().extract(payload.source, payload.source_type)
    return _to_dict(result)


@app.post("/rewrite", response_model=RewriteResponse)
async def rewrite(payload: RewriteRequest) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(_rewrite_sync, payload)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"{type(exc).__name__}: {exc}",
        ) from exc


@app.get("/stats")
def stats(state_dir: str = "./news_rewriter_state", db_path: str | None = None) -> dict[str, int]:
    state = AgentState(state_dir=db_path or state_dir)
    try:
        return state.stats()
    finally:
        state.close()


@app.post("/published")
def published(payload: PublishedRequest) -> dict[str, Any]:
    state = AgentState(state_dir=payload.db_path or payload.state_dir)
    try:
        state.save_published(
            run_id=payload.run_id,
            final_title=payload.final_title,
            final_body=payload.final_body,
            rating=payload.rating,
            notes=payload.notes,
        )
        return {"ok": True, "run_id": payload.run_id}
    finally:
        state.close()
