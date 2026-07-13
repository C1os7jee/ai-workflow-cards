"""主流程编排。串起 提取 → 锚定 → 选题 → 改写 → 自检 → 持久化。

加入:
- Tracer: 每步都留痕
- AgentState: 本地文件持久化
- Retry: API 失败自动重试 + 优雅降级
"""
import json
import re
import time
from datetime import datetime
from typing import Optional, Callable, Any
from llm_client import LLMClient

from schemas import (
    ExtractResult, FactAnchors, Recommendation,
    RewriteDraft, SelfCheck, RewriteResult, ExtractedContent,
)
from extractor import Extractor
from style_card import STYLE_CARD, BANNED_WORDS, BANNED_OPENING
from prompts import FACT_ANCHOR_PROMPT, SELECTION_PROMPT, REWRITE_PROMPT
from tracer import Tracer
from state import AgentState



MAX_RETRIES = 2


class NewsRewriteAgent:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        state_dir: str = "./news_rewriter_state",
        db_path: Optional[str] = None,
        log_dir: str = "./logs",
        verbose: bool = False,
    ):
        self.client = LLMClient(
            api_key=api_key,
            base_url=base_url,
            model=model,
        )
        self.extractor = Extractor()
        self.state = AgentState(state_dir=db_path or state_dir)
        self.log_dir = log_dir
        self.verbose = verbose

    # ============ 主入口 ============
    def run(self, source: str, source_type: str = "auto") -> RewriteResult:
        run_id = RewriteResult.new_run_id()
        tracer = Tracer(verbose=self.verbose, log_dir=self.log_dir, run_id=run_id)
        tracer.info(f"=== Run {run_id} START ===")

        # 1. 提取
        with tracer.step("extract") as t:
            t.set_input(f"source={source[:60]}, type={source_type}")
            ext_result = self.extractor.extract(source, source_type)
            if not ext_result.success:
                t.set_output(f"FAILED: {ext_result.error}")
                # 提取失败 → 直接返回空结果,不要崩
                return self._empty_result(run_id, source, source_type,
                                          ext_result.error, tracer)
            content = ext_result.content
            t.set_output(f"got {len(content.body)}字, method={content.extract_method}")
            if ext_result.fallback_used:
                t.add_issue("使用了降级提取路径")

        # 2. 事实锚定 (带重试)
        with tracer.step("anchor_facts") as t:
            t.set_input(f"body_len={len(content.body)}")
            anchors = self._step_with_retry(
                lambda: self._anchor_facts(content.body),
                fallback=FactAnchors(raw_text_summary="[锚定失败]"),
                tracer=tracer,
                step_name="anchor_facts",
            )
            t.set_output(
                f"tools={len(anchors.tools)} numbers={len(anchors.numbers)} "
                f"summary={anchors.raw_text_summary[:30]}"
            )

        # 撞稿检测
        with tracer.step("dedup_check") as t:
            similar = self.state.find_similar(anchors.raw_text_summary)
            t.set_output(f"found {len(similar)} similar past runs")
            if similar:
                tracer.warn(
                    f"⚠ 可能撞稿: 历史有 {len(similar)} 篇类似主题"
                )

        # 3. 选题建议
        with tracer.step("recommend") as t:
            rec = self._step_with_retry(
                lambda: self._recommend(anchors),
                fallback=Recommendation(
                    worth_writing=True, angle="[选题判断失败,默认继续]",
                    risk_level="medium",
                ),
                tracer=tracer,
                step_name="recommend",
            )
            t.set_output(f"worth={rec.worth_writing} risk={rec.risk_level}")

        # 4. 改写
        with tracer.step("rewrite") as t:
            draft = self._step_with_retry(
                lambda: self._rewrite(content, anchors, rec),
                fallback=RewriteDraft(body="[改写失败]"),
                tracer=tracer,
                step_name="rewrite",
            )
            t.set_output(
                f"titles={len(draft.title_candidates)} "
                f"openings={len(draft.opening_candidates)} "
                f"fabricated={len(draft.fabricated_segments)}"
            )

        # 5. 自检
        with tracer.step("self_check") as t:
            check = self._self_check(draft, anchors)
            issues = (
                len(check.body_banned_words)
                + len(check.opening_banned_words)
                + len(check.fact_issues)
            )
            t.set_output(
                f"fact_ok={check.fact_ok} issues={issues} "
                f"fabricated={check.fabrication_count}"
            )
            if similar:
                check.warnings.insert(
                    0,
                    f"撞稿提醒: 历史有 {len(similar)} 篇类似主题, "
                    f"最近一篇 {similar[0]['created_at'][:10]}",
                )

        # 6. 组装 + 本地文件持久化
        result = RewriteResult(
            run_id=run_id,
            source={
                "type": content.source_type,
                "origin": content.origin,
                "original_title": content.title,
                "extract_method": content.extract_method,
                "extract_warnings": content.warnings,
                "fallback_used": ext_result.fallback_used,
            },
            fact_anchors=anchors,
            recommendation=rec,
            draft=draft,
            self_check=check,
            traces=tracer.traces,
            created_at=datetime.now().isoformat(),
        )

        with tracer.step("persist") as t:
            self.state.record_run(result)
            t.set_output(f"saved to {self.state.state_dir}")

        tracer.info(f"=== Run {run_id} DONE ===")
        return result

    # ============ 公开方法: 反馈 ============
    def mark_published(
        self,
        run_id: str,
        final_title: str,
        final_body: str,
        rating: str = "good",
        notes: str = "",
    ):
        """你手改完发布后,调这个把成品记下来,后续做 few-shot 样本。"""
        self.state.save_published(
            run_id=run_id,
            final_title=final_title,
            final_body=final_body,
            rating=rating,
            notes=notes,
        )

    def get_stats(self) -> dict:
        return self.state.stats()

    # ============ 各步骤实现 ============
    def _anchor_facts(self, content: str) -> FactAnchors:
        prompt = FACT_ANCHOR_PROMPT.format(content=content)
        data = self._llm_json(prompt, max_tokens=2000)
        return FactAnchors(
            tools=data.get("tools", []),
            numbers=data.get("numbers", []),
            features=data.get("features", []),
            people_orgs=data.get("people_orgs", []),
            claims=data.get("claims", []),
            raw_text_summary=data.get("raw_text_summary", ""),
        )

    def _recommend(self, anchors: FactAnchors) -> Recommendation:
        prompt = SELECTION_PROMPT.format(
            style_card=STYLE_CARD,
            fact_summary=anchors.raw_text_summary,
        )
        data = self._llm_json(prompt, max_tokens=500)
        return Recommendation(
            worth_writing=data.get("worth_writing", True),
            angle=data.get("angle", ""),
            risk_level=data.get("risk_level", "medium"),
            note=data.get("note", ""),
        )

    def _rewrite(
        self,
        content: ExtractedContent,
        anchors: FactAnchors,
        rec: Recommendation,
    ) -> RewriteDraft:
        prompt = REWRITE_PROMPT.format(
            style_card=STYLE_CARD,
            original_content=content.body,
            fact_anchors=json.dumps(
                {
                    "tools": anchors.tools,
                    "numbers": anchors.numbers,
                    "features": anchors.features,
                    "people_orgs": anchors.people_orgs,
                    "claims": anchors.claims,
                },
                ensure_ascii=False, indent=2,
            ),
            recommendation=f"{rec.angle} (风险:{rec.risk_level})",
        )
        data = self._llm_json(prompt, max_tokens=4000)
        body = data.get("body", "")
        fabricated = re.findall(
            r"\[似真例子,待核对\]:.*?\[/似真例子\]",
            body, flags=re.DOTALL,
        )
        return RewriteDraft(
            title_candidates=data.get("title_candidates", []),
            opening_candidates=data.get("opening_candidates", []),
            body=body,
            ending_options=data.get("ending_options", {}),
            fabricated_segments=fabricated,
        )

    def _self_check(self, draft: RewriteDraft, anchors: FactAnchors) -> SelfCheck:
        check = SelfCheck()

        if draft.title_candidates:
            check.title_formula_pass = all(
                ("我" in t) and bool(re.search(r"\d", t))
                for t in draft.title_candidates
            )
            if not check.title_formula_pass:
                check.warnings.append("部分标题不满足'我+数字'公式")

        for op in draft.opening_candidates:
            for w in BANNED_OPENING:
                if op.startswith(w):
                    check.opening_banned_words.append(
                        f"{w} (出现在: {op[:20]}...)"
                    )

        for w in BANNED_WORDS:
            if w in draft.body:
                check.body_banned_words.append(w)

        for tool in anchors.tools:
            if tool and tool not in draft.body:
                check.fact_issues.append(f"工具名 '{tool}' 在改写后未出现")

        anchor_nums = [re.search(r"\d+", n) for n in anchors.numbers]
        anchor_nums = [m.group() for m in anchor_nums if m]
        if anchor_nums:
            found = sum(1 for n in anchor_nums if n in draft.body)
            if found == 0:
                check.fact_issues.append(
                    f"锚定的数字 {anchor_nums} 在正文里一个都没出现"
                )

        check.fact_ok = len(check.fact_issues) == 0
        check.fabrication_count = len(draft.fabricated_segments)

        if check.fabrication_count > 0:
            check.warnings.append(
                f"有 {check.fabrication_count} 段[似真例子],"
                f"发稿前必须用你的真实经历替换"
            )

        return check

    # ============ 错误恢复 ============
    def _step_with_retry(
        self,
        fn: Callable[[], Any],
        fallback: Any,
        tracer: Tracer,
        step_name: str,
        max_retries: int = MAX_RETRIES,
    ) -> Any:
        """通用重试: 指数退避, 最后失败用 fallback 兜底。"""
        last_err = None
        for i in range(max_retries + 1):
            try:
                return fn()
            except (
                OSError,
                TimeoutError,
                json.JSONDecodeError,
                KeyError,
                ValueError,
            ) as e:
                last_err = e
                if i < max_retries:
                    wait = 2 ** i
                    tracer.warn(
                        f"{step_name} attempt {i+1} failed: {e}, "
                        f"retry in {wait}s"
                    )
                    time.sleep(wait)
                else:
                    tracer.warn(
                        f"{step_name} all retries failed: {e}, using fallback"
                    )
        return fallback

    def _llm_json(self, prompt: str, max_tokens: int = 1000) -> dict:
        return self.client.json_call(prompt, max_tokens=max_tokens)

    # ============ 工具方法 ============
    def _empty_result(
        self, run_id: str, source: str, source_type: str,
        error: str, tracer: Tracer,
    ) -> RewriteResult:
        """提取失败时返回空结果,不崩。"""
        return RewriteResult(
            run_id=run_id,
            source={
                "type": source_type, "origin": source,
                "extract_error": error,
            },
            fact_anchors=FactAnchors(),
            recommendation=Recommendation(
                worth_writing=False,
                angle=f"提取失败,无法改写: {error}",
                risk_level="high",
            ),
            draft=RewriteDraft(),
            self_check=SelfCheck(
                warnings=[f"提取阶段失败: {error}"],
            ),
            traces=tracer.traces,
            created_at=datetime.now().isoformat(),
        )

    def close(self):
        self.state.close()
