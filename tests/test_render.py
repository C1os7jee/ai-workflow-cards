from __future__ import annotations

import unittest
import json
import tempfile
import importlib.util
import sys
from pathlib import Path

from agent.agent import VisualAgent
from agent.schemas import RenderInput, RenderSlide
from agent.tools.render import _build_deck_html


SKILL_PREPARE_PATH = Path(__file__).resolve().parents[1] / "skills" / "xhs-card-skill" / "prepare_payload.py"
SKILL_RENDER_PATH = Path(__file__).resolve().parents[1] / "skills" / "xhs-card-skill" / "render_deck.py"
_spec = importlib.util.spec_from_file_location("xhs_card_prepare_payload", SKILL_PREPARE_PATH)
_prepare_module = importlib.util.module_from_spec(_spec)
assert _spec is not None and _spec.loader is not None
sys.modules[_spec.name] = _prepare_module
_spec.loader.exec_module(_prepare_module)
prepare_payload = _prepare_module.prepare_payload

_render_spec = importlib.util.spec_from_file_location("xhs_card_render_deck", SKILL_RENDER_PATH)
_render_module = importlib.util.module_from_spec(_render_spec)
assert _render_spec is not None and _render_spec.loader is not None
sys.modules[_render_spec.name] = _render_module
_render_spec.loader.exec_module(_render_module)


class RenderTests(unittest.TestCase):
    def test_guizang_s09_uses_recipe_dom_instead_of_generic_cards(self):
        render_input = RenderInput(
            style="swiss",
            theme="IKB",
            layout_id="S09",
            visual_direction="中心流程图 + 关键节点高亮",
            visual_blueprint={"strategy": "流程拆解型"},
            slides=[
                RenderSlide(type="cover", title="Hermes Agent", hook="5 步配置 AI 智能体"),
                RenderSlide(
                    type="content",
                    heading="关键变化",
                    points=["网页端一站式创建智能体角色", "关联 Hermes Agent"],
                ),
                RenderSlide(
                    type="content",
                    heading="怎么做到",
                    points=["配置流程被压缩成 5 个步骤", "模型技能 MCP 统一配置"],
                ),
                RenderSlide(type="cta", text="保存这张卡"),
            ],
        ).validate()

        html = _build_deck_html(render_input)

        self.assertIn('class="kpi-tower-row"', html)
        self.assertIn('class="bar-tower"', html)
        self.assertIn("S06 · Pipeline", html)
        self.assertIn('class="hero-stat-bottom"', html)
        self.assertNotIn('<div class="grid cols-1 gap-5">', html)

    def test_guizang_s12_uses_matrix_and_ledger_recipe_dom(self):
        render_input = RenderInput(
            style="swiss",
            theme="forest",
            layout_id="S12",
            visual_direction="模块关系图 + 层级结构",
            visual_blueprint={"strategy": "系统感封面型"},
            slides=[
                RenderSlide(type="cover", title="内容系统", hook="持续进化的结构"),
                RenderSlide(
                    type="content",
                    heading="能力矩阵",
                    points=["账号定位", "视觉策略", "反馈记录"],
                ),
                RenderSlide(
                    type="content",
                    heading="证据保留",
                    points=["render input", "image prompts", "PNG 路径"],
                ),
                RenderSlide(type="cta", text="保存这套流程"),
            ],
        ).validate()

        html = _build_deck_html(render_input)

        self.assertIn('class="matrix-fill"', html)
        self.assertIn('class="matrix-cell is-accent"', html)
        self.assertIn('class="stacked-ledger"', html)
        self.assertIn('class="ledger-icn"', html)
        self.assertIn('class="hero-stat-bottom"', html)

    def test_render_payload_contains_valid_cover_and_cta(self):
        plan = VisualAgent().generate_plan("workflow 自动化内容")
        payload = VisualAgent().to_render_payload(plan)
        cover = payload["slides"][0]
        cta = payload["slides"][-1]
        self.assertLessEqual(len(cover["title"]), 15)
        self.assertLessEqual(len(cover["hook"]), 30)
        self.assertNotIn("heading", cover)
        self.assertEqual(cta["type"], "cta")
        self.assertLessEqual(len(cta["text"]), 20)
        self.assertNotIn("points", cta)

    def test_content_points_do_not_repeat_heading(self):
        plan = VisualAgent().generate_plan("workflow 自动化内容")
        payload = VisualAgent().to_render_payload(plan)
        first_content = payload["slides"][1]
        self.assertNotEqual(first_content["heading"], first_content["points"][0])

    def test_render_payload_reflects_source_brief_terms(self):
        brief = (
            "MiniMax 提出块稀疏注意力 MoSA，Main Branch 只对选中块执行精确块稀疏注意力，"
            "109B 多模态模型上长上下文注意力计算减少 28.4 倍。"
        )
        plan = VisualAgent().generate_plan(brief)
        payload = VisualAgent().to_render_payload(plan)
        text = str(payload)

        self.assertIn("MoSA", text)
        self.assertIn("28.4", text)
        self.assertNotIn("我把内容做成系统了", text)

    def test_render_payload_prefers_main_performance_number(self):
        brief = (
            "MiniMax 提出块稀疏注意力 MoSA，Main Branch 只对选中块执行精确块稀疏注意力。"
            "在 109B 参数多模态模型上，1M 上下文下每 token 注意力计算减少 28.4 倍。"
            "H800 上实现 14.2 倍 prefill 和 7.6 倍 decoding 端到端加速。"
        )
        plan = VisualAgent().generate_plan(brief)
        payload = VisualAgent().to_render_payload(plan)
        text = str(payload)

        self.assertIn("28.4", text)

    def test_structured_brief_drives_cover_and_slide_copy(self):
        brief = (
            "来源 URL：https://news.qq.com/rain/a/20260612A069T900\n"
            "标题：Hermes Agent 上线 Profile Builder，5 步配置 AI 智能体\n"
            "主题：Hermes Agent 上线 Profile Builder，5 步配置 AI 智能体\n"
            "核心钩子：5 步配置 AI 智能体\n"
            "关键点：网页端一站式创建智能体角色 / 配置流程被压缩成 5 个步骤 / "
            "模型、技能和 MCP 统一配置 / 技能以 SKILL.md 形式按需加载\n"
            "关键实体：Hermes Agent / Profile Builder / Nous Research / MCP / Skills Hub / SKILL.md\n"
            "关键数字：5 步 / 2026 / 06 / 12\n"
            "受众角度：AI 工具玩家 / 内容创作者"
        )
        plan = VisualAgent().generate_plan(brief)
        payload = VisualAgent().to_render_payload(plan)
        cover = payload["slides"][0]
        slide_text = str(payload["slides"])

        self.assertNotEqual(cover["title"], "8分钟生成组图")
        self.assertIn("5 步配置", cover["hook"])
        self.assertIn("网页端一站式", slide_text)
        self.assertIn("模型、技能和 MCP", slide_text)

    def test_skill_config_controls_cover_copy(self):
        config = {
            "copy_rules": {
                "keyword_limit": 8,
                "named_keyword_limit": 5,
                "numeric_keyword_limit": 3,
                "avoid_broken_latin_tokens": True,
                "section_headings": ["机制", "证据", "价值"],
                "stopwords": ["内容", "生成"],
            },
            "cta_template": "保存 {lead}",
            "image_generation": {
                "enabled": True,
                "default_provider": "openai-compatible",
                "providers": {
                    "openai-compatible": {"transport": "openai-compatible"}
                },
            },
            "strategies": {
                "default": {
                    "style": "swiss",
                    "theme": "IKB",
                    "layout_id": "S12",
                    "cover_title_template": "{lead} 稳定出图",
                    "cover_hook_template": "{number} 是关键变化",
                    "cover_visual_template": "{lead} 信息图",
                }
            },
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "skill.json"
            config_path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
            prepared = prepare_payload(
                "MiniMax MoSA 让注意力计算减少 28.4 倍。",
                strategy="系统感封面型",
                config_path=config_path,
                image_provider="openai-compatible",
            )

        cover = prepared.render_input["slides"][0]
        self.assertEqual(cover["title"], "MiniMax 稳定出图")
        self.assertEqual(prepared.render_input["slides"][-1]["text"], "保存 MiniMax")
        self.assertEqual(prepared.render_input["image_provider"], "openai-compatible")
        self.assertEqual(prepared.render_input["visual_blueprint"]["mode"], "direct-image-deck")
        self.assertGreaterEqual(len(prepared.render_input["visual_blueprint"]["image_jobs"]), 2)

    def test_seedream_provider_request_uses_official_fields(self):
        request_data = _render_module._volcengine_seedream_request_data(
            "生成小红书封面",
            {
                "api_key_env": "ARK_API_KEY",
                "base_url_env": "ARK_BASE_URL",
                "model_env": "ARK_IMAGE_MODEL",
                "default_base_url": "https://ark.cn-beijing.volces.com/api/v3",
                "default_model": "doubao-seedream-5-0-260128",
                "endpoint": "/images/generations",
                "size": "2K",
                "output_format": "png",
                "response_format": "b64_json",
                "watermark": False,
                "quality": "medium",
            },
            {
                "ARK_API_KEY": "test-key",
                "ARK_BASE_URL": "https://ark.cn-beijing.volces.com/api/v3",
                "ARK_IMAGE_MODEL": "doubao-seedream-5-0-260128",
            },
        )

        self.assertEqual(
            request_data["url"],
            "https://ark.cn-beijing.volces.com/api/v3/images/generations",
        )
        self.assertEqual(request_data["api_key"], "test-key")
        self.assertEqual(
            request_data["payload"],
            {
                "model": "doubao-seedream-5-0-260128",
                "prompt": "生成小红书封面",
                "size": "2K",
                "output_format": "png",
                "response_format": "b64_json",
                "watermark": False,
            },
        )
        self.assertNotIn("quality", request_data["payload"])

    def test_renderer_injects_api_generated_cover_asset(self):
        payload = {
            "style": "swiss",
            "theme": "IKB",
            "layout_id": "S12",
            "visual_direction": "MiniMax / MoSA 关系图",
            "slides": [
                {"type": "cover", "title": "MiniMax 关键拆解", "hook": "28.4 是关键变化"},
                {"type": "cta", "text": "收藏这张卡"},
            ],
        }
        config = {
            "image_generation": {
                "enabled": True,
                "mode": "cover",
                "default_provider": "openai-compatible",
                "providers": {
                    "openai-compatible": {
                        "transport": "openai-compatible",
                        "prompt_template": "{deck_title} {deck_hook} {visual_direction}",
                    }
                },
            }
        }

        def fake_image_api(prompt, output_path, image_config):
            output_path.write_bytes(b"fakepng")

        original = _render_module._call_image_provider
        _render_module._call_image_provider = fake_image_api
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                task_dir = Path(tmpdir)
                assets = _render_module._generate_model_assets(payload, task_dir, config)
                html_paths = _render_module._write_slide_html(payload, task_dir)
                html = html_paths[0].read_text(encoding="utf-8")
                prompt_text = Path(assets["image_prompt"]).read_text(encoding="utf-8")
        finally:
            _render_module._call_image_provider = original

        self.assertEqual(Path(assets["cover_image"]).name, "generated_cover.png")
        self.assertIn("generated_cover.png", html)
        self.assertIn("MiniMax 关键拆解 28.4 是关键变化", prompt_text)

    def test_direct_image_deck_generates_model_cards_without_html_shell(self):
        payload = {
            "style": "swiss",
            "theme": "IKB",
            "layout_id": "S12",
            "image_provider": "openai-compatible",
            "visual_blueprint": {
                "mode": "direct-image-deck",
                "image_jobs": [
                    {
                        "id": "card_01",
                        "role": "cover",
                        "title": "MiniMax 关键拆解",
                        "message": "28.4 是关键变化",
                        "prompt": "finished card one",
                        "output_name": "card_01.png",
                    },
                    {
                        "id": "card_02",
                        "role": "takeaway",
                        "title": "证据",
                        "message": "H800 加速",
                        "prompt": "finished card two",
                        "output_name": "card_02.png",
                    },
                ],
            },
            "slides": [
                {"type": "cover", "title": "MiniMax 关键拆解", "hook": "28.4 是关键变化"},
                {"type": "cta", "text": "收藏这张卡"},
            ],
        }
        config = {
            "image_generation": {
                "enabled": True,
                "default_provider": "openai-compatible",
                "providers": {
                    "openai-compatible": {
                        "transport": "openai-compatible",
                    }
                },
            }
        }

        def fake_image_api(prompt, output_path, image_config):
            output_path.write_bytes(("fake " + prompt).encode("utf-8"))

        original = _render_module._call_image_provider
        _render_module._call_image_provider = fake_image_api
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                result = _render_module.render_deck(payload, output_root=Path(tmpdir))
                task_dir = Path(result["task_dir"])
                prompt_manifest = json.loads((task_dir / "image_prompts.json").read_text(encoding="utf-8"))
        finally:
            _render_module._call_image_provider = original

        self.assertEqual([Path(path).name for path in result["png_paths"]], ["card_01.png", "card_02.png"])
        self.assertEqual(result["generated_assets"]["deck_images"], result["png_paths"])
        self.assertFalse(any(task_dir.glob("slide_*.html")))
        self.assertEqual([item["prompt"] for item in prompt_manifest], ["finished card one", "finished card two"])

    def test_ai_planner_can_supply_dynamic_image_jobs(self):
        def fake_ai_planner(**kwargs):
            prompt_template = kwargs["prompt_template"]
            return [
                {
                    "id": "card_01",
                    "role": "cover",
                    "title": "AI 选的封面",
                    "message": "先讲核心冲突",
                    "source_detail": "source",
                    "prompt": prompt_template.replace("{role}", "cover")
                    .replace("{title}", "AI 选的封面")
                    .replace("{message}", "先讲核心冲突")
                    .replace("{source_detail}", "source")
                    .replace("{visual_direction}", "dynamic"),
                    "output_name": "card_01.png",
                },
                {
                    "id": "card_02",
                    "role": "evidence",
                    "title": "AI 选的证据",
                    "message": "再讲数字",
                    "source_detail": "source",
                    "prompt": "evidence prompt",
                    "output_name": "card_02.png",
                },
            ]

        original = _prepare_module._call_ai_planner
        _prepare_module._call_ai_planner = fake_ai_planner
        try:
            prepared = prepare_payload(
                "MiniMax MoSA 让注意力计算减少 28.4 倍。",
                strategy="系统感封面型",
                image_provider="openai-compatible",
                planner_mode="ai",
            )
        finally:
            _prepare_module._call_ai_planner = original

        blueprint = prepared.render_input["visual_blueprint"]
        self.assertEqual(blueprint["planner"], "ai")
        self.assertEqual(blueprint["target_cards"], 2)
        self.assertEqual(blueprint["image_jobs"][0]["title"], "AI 选的封面")

    def test_deepseek_planner_uses_deepseek_env_and_chat_completions(self):
        captured = {}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json.dumps(
                    {
                        "choices": [
                            {
                                "message": {
                                    "content": json.dumps(
                                        {
                                            "image_jobs": [
                                                {
                                                    "id": "card_01",
                                                    "role": "cover",
                                                    "title": "DeepSeek 封面",
                                                    "message": "动态决定第一张",
                                                    "source_detail": "source",
                                                    "visual_direction": "visual",
                                                },
                                                {
                                                    "id": "card_02",
                                                    "role": "takeaway",
                                                    "title": "DeepSeek 总结",
                                                    "message": "动态决定第二张",
                                                    "source_detail": "source",
                                                    "visual_direction": "visual",
                                                },
                                            ]
                                        },
                                        ensure_ascii=False,
                                    )
                                }
                            }
                        ]
                    }
                ).encode("utf-8")

        def fake_load_env():
            return {
                "DEEPSEEK_API_KEY": "deepseek-key",
                "DEEPSEEK_BASE_URL": "https://api.deepseek.com",
                "DEEPSEEK_TEXT_MODEL": "deepseek-v4-pro",
            }

        def fake_urlopen(request, timeout):
            captured["url"] = request.full_url
            captured["headers"] = dict(request.header_items())
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            captured["timeout"] = timeout
            return FakeResponse()

        original_env = _prepare_module.load_env
        original_urlopen = _prepare_module.urllib.request.urlopen
        _prepare_module.load_env = fake_load_env
        _prepare_module.urllib.request.urlopen = fake_urlopen
        try:
            jobs = _prepare_module._call_ai_planner(
                source="source",
                strategy="系统感封面型",
                visual="visual",
                planner_config={
                    "api_key_env": "DEEPSEEK_API_KEY",
                    "base_url_env": "DEEPSEEK_BASE_URL",
                    "model_env": "DEEPSEEK_TEXT_MODEL",
                    "default_base_url": "https://api.deepseek.com",
                    "default_model": "deepseek-v4-pro",
                    "endpoint": "/chat/completions",
                    "temperature": 0.35,
                },
                prompt_template="{role} {title} {message} {source_detail} {visual_direction}",
                min_cards=2,
                max_cards=4,
            )
        finally:
            _prepare_module.load_env = original_env
            _prepare_module.urllib.request.urlopen = original_urlopen

        self.assertEqual(captured["url"], "https://api.deepseek.com/chat/completions")
        self.assertEqual(captured["headers"]["Authorization"], "Bearer deepseek-key")
        self.assertEqual(captured["payload"]["model"], "deepseek-v4-pro")
        self.assertEqual(captured["payload"]["response_format"], {"type": "json_object"})
        self.assertIn("JSON object", captured["payload"]["messages"][0]["content"])
        self.assertEqual(jobs[0]["title"], "DeepSeek 封面")


if __name__ == "__main__":
    unittest.main()
