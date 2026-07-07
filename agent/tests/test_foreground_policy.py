from datetime import datetime, timedelta
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from foreground_context import ForegroundSavePolicy


def _window(process_name: str, url: str = "", title: str = "Test"):
    return {
        "process_name": process_name,
        "window_title": title,
        "foreground_url": url,
    }


def test_process_rule_warmup_then_suppress():
    policy = ForegroundSavePolicy()
    policy.update_config([
        {"id": 1, "rule_type": "process", "pattern": "wechat.exe", "enabled": True},
    ], warmup_seconds=10, keepalive_seconds=300)

    start = datetime(2026, 7, 7, 12, 0, 0)
    decision = policy.evaluate(_window("WeChat.exe"), now=start)
    assert decision["store_history"] is True
    assert decision["save_policy_phase"] == "warmup"
    policy.mark_saved(decision, when=start)

    warm = policy.evaluate(_window("WeChat.exe"), now=start + timedelta(seconds=6))
    assert warm["store_history"] is True
    assert warm["save_policy_phase"] == "warmup"
    policy.mark_saved(warm, when=start + timedelta(seconds=6))

    suppressed = policy.evaluate(_window("WeChat.exe"), now=start + timedelta(seconds=11))
    assert suppressed["store_history"] is False
    assert suppressed["save_policy_phase"] == "suppressed"


def test_process_rule_keepalive_after_suppression():
    policy = ForegroundSavePolicy()
    policy.update_config([
        {"id": 2, "rule_type": "process", "pattern": "wechat.exe", "enabled": True},
    ], warmup_seconds=10, keepalive_seconds=300)

    start = datetime(2026, 7, 7, 12, 0, 0)
    first = policy.evaluate(_window("WeChat.exe"), now=start)
    policy.mark_saved(first, when=start)

    second = policy.evaluate(_window("WeChat.exe"), now=start + timedelta(seconds=10))
    assert second["store_history"] is False

    keepalive = policy.evaluate(_window("WeChat.exe"), now=start + timedelta(seconds=301))
    assert keepalive["store_history"] is True
    assert keepalive["save_policy_phase"] == "keepalive"


def test_url_rule_uses_full_url_contains():
    policy = ForegroundSavePolicy()
    policy.update_config([
        {"id": 3, "rule_type": "url_contains", "pattern": "youtube.com/watch", "enabled": True},
    ], warmup_seconds=10, keepalive_seconds=300)

    now = datetime(2026, 7, 7, 13, 0, 0)
    decision = policy.evaluate({
        "process_name": "chrome.exe",
        "window_title": "Video",
        "foreground_url": "https://www.youtube.com/watch?v=abc123",
    }, now=now)

    assert decision["store_history"] is True
    assert decision["matched_rule_type"] == "url_contains"
    assert decision["matched_rule_pattern"] == "youtube.com/watch"


def test_unmatched_target_keeps_default_storage():
    policy = ForegroundSavePolicy()
    policy.update_config([
        {"id": 4, "rule_type": "process", "pattern": "wechat.exe", "enabled": True},
    ], warmup_seconds=10, keepalive_seconds=300)

    decision = policy.evaluate(_window("notepad.exe"), now=datetime(2026, 7, 7, 14, 0, 0))
    assert decision["store_history"] is True
    assert decision["save_policy_phase"] == "default"
