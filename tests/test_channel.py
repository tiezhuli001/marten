import unittest

from app.core.config import Settings
from app.channel.notifications import ChannelNotificationService


class ChannelNotificationServiceTests(unittest.TestCase):
    def test_feishu_payload_uses_interactive_card(self) -> None:
        service = ChannelNotificationService(
            Settings(app_env="test", channel_provider="feishu")
        )

        payload = service._build_payload(
            "Ralph 任务完成：feat: sample",
            [
                "来源: Issue #9",
                "仓库: tiezhuli001/youmeng-gateway",
                "Issue: https://github.com/tiezhuli001/youmeng-gateway/issues/9",
                "三、Token 消耗统计",
                "输入 Token: 10",
                "输出 Token: 5",
                "总 Token: 15",
                "总成本: $0.001",
                "阶段分布:",
                "Plan: 输入 10 · 输出 5 · 总 15 · 成本 $0.001",
            ],
        )

        self.assertEqual(payload["msg_type"], "interactive")
        card = payload["card"]
        self.assertEqual(card["header"]["template"], "green")
        self.assertEqual(card["header"]["title"]["content"], "Ralph 任务完成：feat: sample")
        elements = card["elements"]
        self.assertTrue(any(element["tag"] == "markdown" for element in elements))
        self.assertTrue(any(element["tag"] == "hr" for element in elements))
        self.assertEqual(elements[-1]["tag"], "note")
        merged = "\n".join(
            element.get("content", "")
            for element in elements
            if element["tag"] == "markdown"
        )
        self.assertIn("**交付概览**", merged)
        self.assertIn("**输入 Token**: 10", merged)
        self.assertIn("**总成本**: $0.001", merged)
        self.assertIn("**阶段分布**", merged)
        self.assertIn("**Plan**: 输入 10 · 输出 5 · 总 15 · 成本 $0.001", merged)

    def test_feishu_card_formats_links_and_started_title(self) -> None:
        service = ChannelNotificationService(
            Settings(app_env="test", channel_provider="feishu")
        )

        payload = service._build_payload(
            "Ralph 任务开始：Issue #42",
            [
                "Repo: tiezhuli001/youmeng-gateway",
                "Issue: https://github.com/tiezhuli001/youmeng-gateway/issues/42",
                "Plan: Implement issue workflow",
            ],
        )

        self.assertEqual(payload["card"]["header"]["template"], "orange")
        markdown_blocks = [
            element["content"]
            for element in payload["card"]["elements"]
            if element["tag"] == "markdown"
        ]
        merged = "\n".join(markdown_blocks)
        self.assertIn("**执行开始**", merged)
        self.assertIn("**Repo**: tiezhuli001/youmeng-gateway", merged)
        self.assertIn(
            "**Issue**: [https://github.com/tiezhuli001/youmeng-gateway/issues/42](https://github.com/tiezhuli001/youmeng-gateway/issues/42)",
            merged,
        )

    def test_feishu_card_preserves_numbered_plan_items(self) -> None:
        service = ChannelNotificationService(
            Settings(app_env="test", channel_provider="feishu")
        )

        payload = service._build_payload(
            "Ralph 执行计划：Issue #42",
            [
                "来源: Issue #42",
                "执行计划:",
                "1. 阅读 Issue 与约束目录。",
                "2. 仅修改目标目录下的代码。",
                "3. 运行测试并准备 PR。",
            ],
        )

        markdown_blocks = [
            element["content"]
            for element in payload["card"]["elements"]
            if element["tag"] == "markdown"
        ]
        merged = "\n".join(markdown_blocks)
        self.assertIn("1. 阅读 Issue 与约束目录。", merged)
        self.assertIn("2. 仅修改目标目录下的代码。", merged)

    def test_feishu_card_renders_file_table_as_list_items(self) -> None:
        service = ChannelNotificationService(
            Settings(app_env="test", channel_provider="feishu")
        )

        payload = service._build_payload(
            "Ralph 任务完成：feat: sample",
            [
                "一、修改文件清单",
                "| 文件路径 | 说明 |",
                "|---------|------|",
                "| app/main.py | 调整主流程 |",
                "| tests/test_mvp_e2e.py | 覆盖主链路回归 |",
            ],
        )

        markdown_blocks = [
            element["content"]
            for element in payload["card"]["elements"]
            if element["tag"] == "markdown"
        ]
        merged = "\n".join(markdown_blocks)
        self.assertIn("**一、修改文件清单**", merged)
        self.assertIn("- **app/main.py** · 说明: 调整主流程", merged)
        self.assertIn("- **tests/test_mvp_e2e.py** · 说明: 覆盖主链路回归", merged)


if __name__ == "__main__":
    unittest.main()
