"""截图策略自动化测试。"""

import pathlib
import sys
import unittest

AGENT_DIR = pathlib.Path(__file__).resolve().parents[1]
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

from main import resolve_screenshot_strategy


class ResolveScreenshotStrategyTests(unittest.TestCase):
    """覆盖文档中的截图策略阈值。"""

    def test_active_has_priority_over_viewer(self):
        """活跃态即使有人观看，也保持 0.25 秒。"""
        interval, mode = resolve_screenshot_strategy(5, 1)
        self.assertEqual(interval, 0.25)
        self.assertEqual(mode, "ACTIVE")

    def test_viewer_only_applies_after_active_window(self):
        """超过 1 分钟且有人观看时，进入 1 秒 LIVE。"""
        interval, mode = resolve_screenshot_strategy(90, 1)
        self.assertEqual(interval, 1.0)
        self.assertEqual(mode, "VIEWER")

    def test_light_idle_threshold(self):
        """1 到 5 分钟空闲属于 LIGHT_IDLE。"""
        interval, mode = resolve_screenshot_strategy(150, 5)
        self.assertEqual(interval, 10.0)
        self.assertEqual(mode, "LIGHT_IDLE")

    def test_deep_idle_threshold(self):
        """5 到 30 分钟空闲属于 DEEP_IDLE。"""
        interval, mode = resolve_screenshot_strategy(450, 5)
        self.assertEqual(interval, 60.0)
        self.assertEqual(mode, "DEEP_IDLE")

    def test_very_deep_idle_threshold(self):
        """30 分钟以上空闲属于 VERY_DEEP_IDLE。"""
        interval, mode = resolve_screenshot_strategy(2400, 5)
        self.assertEqual(interval, 600.0)
        self.assertEqual(mode, "VERY_DEEP_IDLE")

    def test_startup_can_enter_idle_immediately_when_desktop_was_already_idle(self):
        """Agent 启动前已闲置时，启动后直接进入空闲态。"""
        interval, mode = resolve_screenshot_strategy(320, 5)
        self.assertEqual(interval, 60.0)
        self.assertEqual(mode, "DEEP_IDLE")


if __name__ == "__main__":
    unittest.main()
