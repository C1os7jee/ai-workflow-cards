"""状态持久化。基于本地 JSON 文件,不依赖数据库。

核心场景:
1. 记录每次跑的输入输出 -> 防撞稿、便于回顾
2. 记录你手改后发布的版本 -> 后续做 few-shot 样本
3. 记录历次校验问题 -> 沉淀经验
"""
from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime

from schemas import RewriteResult


class AgentState:
    def __init__(self, state_dir: str = "./news_rewriter_state"):
        self.state_dir = _normalize_state_dir(state_dir)
        self.db_path = str(self.state_dir)  # Backward-compatible display field.
        self.runs_dir = self.state_dir / "runs"
        self.runs_index_path = self.state_dir / "runs.jsonl"
        self.published_path = self.state_dir / "published.jsonl"
        self.runs_dir.mkdir(parents=True, exist_ok=True)

    # ---------- 记录 ----------
    def record_run(self, result: RewriteResult):
        """每次跑完都记一笔到本地 JSON 文件。"""
        result_path = self.runs_dir / f"{result.run_id}.json"
        result_path.write_text(
            result.to_json(with_traces=True),
            encoding="utf-8",
        )

        record = {
            "run_id": result.run_id,
            "created_at": result.created_at or datetime.now().isoformat(),
            "source_type": result.source.get("type", ""),
            "source_origin": result.source.get("origin", ""),
            "fact_summary": result.fact_anchors.raw_text_summary,
            "worth_writing": bool(result.recommendation.worth_writing),
            "risk_level": result.recommendation.risk_level,
            "result_path": str(result_path),
        }
        _replace_jsonl_record(self.runs_index_path, "run_id", record)

    def save_published(
        self,
        run_id: str,
        final_title: str,
        final_body: str,
        rating: str = "good",
        notes: str = "",
    ):
        """记录你手改后发布的版本。"""
        record = {
            "run_id": run_id,
            "published_at": datetime.now().isoformat(),
            "final_title": final_title,
            "final_body": final_body,
            "rating": rating,
            "notes": notes,
        }
        _append_jsonl(self.published_path, record)

    # ---------- 查询 ----------
    def find_similar(self, fact_summary: str, limit: int = 5) -> list[dict]:
        """简易撞稿检测: 看历史里有没有类似主题。"""
        if not fact_summary or len(fact_summary) < 5:
            return []
        keyword = fact_summary[:10]
        rows = [
            row for row in _read_jsonl(self.runs_index_path)
            if keyword in str(row.get("fact_summary", ""))
        ]
        rows.sort(key=lambda item: str(item.get("created_at", "")), reverse=True)
        return rows[:limit]

    def get_good_examples(self, n: int = 3) -> list[dict]:
        """取最近 n 篇评为 good 的发布稿,用作 few-shot 样本。"""
        rows = [
            row for row in _read_jsonl(self.published_path)
            if row.get("rating") == "good"
        ]
        rows.sort(key=lambda item: str(item.get("published_at", "")), reverse=True)
        return [
            {
                "final_title": row.get("final_title", ""),
                "final_body": row.get("final_body", ""),
                "published_at": row.get("published_at", ""),
            }
            for row in rows[:n]
        ]

    def stats(self) -> dict:
        """简单统计。"""
        return {
            "total_runs": len(_read_jsonl(self.runs_index_path)),
            "published": len(_read_jsonl(self.published_path)),
        }

    def close(self):
        """File-backed state does not keep an open handle."""
        return None


def _normalize_state_dir(path: str) -> Path:
    state_path = Path(path)
    if state_path.suffix.lower() == ".db":
        state_path = state_path.with_suffix("")
    return state_path


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def _append_jsonl(path: Path, record: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _replace_jsonl_record(path: Path, key: str, record: dict):
    rows = [row for row in _read_jsonl(path) if row.get(key) != record.get(key)]
    rows.append(record)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
