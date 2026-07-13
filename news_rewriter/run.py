"""入口示例。

用法:
    export ANTHROPIC_API_KEY=sk-ant-...
    python run.py
"""
from agent import NewsRewriteAgent


SAMPLE_NEWS = """
Notion 今日发布 AI Meetings 功能,支持自动录制会议、生成纪要和待办事项。
官方称对中英文识别准确率达 95%,平均可将整理纪要的时间从 30 分钟缩短到 2 分钟。
功能内置于 Notion 工作区, Plus 订阅 ($10/月) 用户即可使用。
目前支持 Zoom、Google Meet、Microsoft Teams 三个主流平台,
但暂不支持本地录音文件上传,且会议时长超过 90 分钟时需要分段处理。
"""


def main():
    # verbose=True 时会打印每一步的输入输出摘要到控制台 + 日志文件
    agent = NewsRewriteAgent(
        base_url="https://api.deepseek.com",
        model="deepseek-chat",
        state_dir="./news_rewriter_state",
        log_dir="./logs",
        verbose=True,
    )

    # === 1. 跑一篇 ===
    result = agent.run(SAMPLE_NEWS, source_type="text")

    print("\n=== 决策摘要 ===")
    print(f"run_id: {result.run_id}")
    print(f"是否建议写: {result.recommendation.worth_writing}")
    print(f"角度: {result.recommendation.angle}")
    print(f"风险: {result.recommendation.risk_level}")
    print(f"事实校验: {'OK' if result.self_check.fact_ok else '有问题'}")
    print(f"编造段落数: {result.self_check.fabrication_count}")
    print(f"标题候选: {len(result.draft.title_candidates)} 个")
    if result.self_check.warnings:
        print("提醒:")
        for w in result.self_check.warnings:
            print(f"  - {w}")

    print("\n=== 完整结果(不含 traces) ===")
    print(result.to_json())

    # === 2. 假设你手改完发布了, 把成品记下来 ===
    # agent.mark_published(
    #     run_id=result.run_id,
    #     final_title="我把开4个会的纪要,扔给AI干了6分钟",
    #     final_body="(你最终发的正文)",
    #     rating="good",
    #     notes="开头改成了画面式,删了一段似真例子",
    # )

    # === 3. 看统计 ===
    print("\n=== 统计 ===")
    print(agent.get_stats())

    agent.close()


if __name__ == "__main__":
    main()
