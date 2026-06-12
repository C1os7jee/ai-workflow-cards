# Tasks: 小红书 Visual Agent MVP

> Status: historical task breakdown. 当前协作边界以
> [../architecture.md](../architecture.md)、[../../INTERFACE.md](../../INTERFACE.md)
> 和 [../decisions/ADR-001-dynamic-visual-blueprint.md](../decisions/ADR-001-dynamic-visual-blueprint.md)
> 为准。本清单只作为早期任务背景，不作为当前实现契约。

- [ ] Task 1: 定义核心 schema
  - Acceptance: `content brief`、`visual plan`、`feedback record` 三类结构化对象可以序列化和校验。
  - Verify: 单元测试覆盖字段必填、默认值和边界值。
  - Files: `agent/schemas.py`, `tests/test_agent.py`

- [ ] Task 2: 建立视觉策略映射
  - Acceptance: 给定内容目标，系统能输出推荐视觉策略和备选策略。
  - Verify: 测试 workflow、提效、工具实操等常见内容的策略选择。
  - Files: `agent/agent.py`, `agent/tools/layouts.py`, `tests/test_agent.py`

- [ ] Task 3: 设计反馈记录文件格式
  - Acceptance: 人工修改理由和发布表现能追加写入，不覆盖历史记录。
  - Verify: 测试 JSONL 追加、字段完整性和可读性。
  - Files: `agent/tools/validate.py`, `tests/test_agent.py`, `docs/memories/`

- [ ] Task 4: 打通渲染输入转换
  - Acceptance: Visual plan 能稳定转换成当前 `INTERFACE.md` 所需的 render input。
  - Verify: 测试 `style/theme/layout_id/visual_blueprint.image_jobs` 的映射结果；`slides` 只作为兼容字段。
  - Files: `agent/tools/render.py`, `agent/tools/layouts.py`, `tests/test_render.py`

- [ ] Task 5: 增加最小 CLI 入口
  - Acceptance: 能通过命令行喂入内容 brief，输出视觉策略或渲染输入草案。
  - Verify: `python main.py --help` 和一个最小示例命令可运行。
  - Files: `main.py`, `README.md`

- [ ] Task 6: 补充最小端到端测试
  - Acceptance: 固定输入能跑通“策略选择 -> 渲染输入 -> 结果记录”的闭环。
  - Verify: `python3 -m unittest discover -s tests -v`。
  - Files: `tests/`
