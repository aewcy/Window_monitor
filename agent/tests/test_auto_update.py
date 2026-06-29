"""后台更新模块测试。"""

import pathlib
import sys
import unittest

AGENT_DIR = pathlib.Path(__file__).resolve().parents[1]
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

from auto_update import is_newer_version


class AutoUpdateVersionTests(unittest.TestCase):
    """覆盖 Agent 更新版本比较。"""

    def test_detects_newer_patch_version(self):
        self.assertTrue(is_newer_version("0.53", "0.52"))

    def test_equal_version_is_not_newer(self):
        self.assertFalse(is_newer_version("0.52", "0.52"))

    def test_accepts_v_prefix(self):
        self.assertTrue(is_newer_version("v0.53", "0.52"))


if __name__ == "__main__":
    unittest.main()
