"""截图上报通道的网络策略测试。"""

import pathlib
import sys

AGENT_DIR = pathlib.Path(__file__).resolve().parents[1]
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

from main import Reporter


def _reporter():
    reporter = Reporter.__new__(Reporter)
    reporter.url = "http://108.187.15.71:8899"
    return reporter


def test_agent_session_ignores_unreliable_system_proxy_by_default():
    session = _reporter()._make_session()
    try:
        assert session.trust_env is False
    finally:
        session.close()


def test_screenshot_upload_uses_fast_fail_policy():
    attempts, timeout = _reporter()._request_policy("screenshot")

    assert attempts == 1
    assert timeout == 4


def test_control_upload_keeps_reliable_default_policy():
    attempts, timeout = _reporter()._request_policy("heartbeat")

    assert attempts == 3
    assert timeout == 10
