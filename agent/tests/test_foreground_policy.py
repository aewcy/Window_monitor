import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from foreground_context import get_foreground_context


def _window(process_name: str, url: str = "", title: str = "Test"):
    return {
        "process_name": process_name,
        "window_title": title,
        "foreground_url": url,
    }


def test_context_keeps_agent_foreground_fields_without_policy_decision():
    context = get_foreground_context(_window(
        "Chrome.exe",
        url="https://www.youtube.com/watch?v=abc123",
        title="Video - Google Chrome",
    ))

    assert context == {
        "process_name": "Chrome.exe",
        "window_title": "Video - Google Chrome",
        "foreground_url": "https://www.youtube.com/watch?v=abc123",
    }


def test_context_keeps_non_browser_window_information():
    context = get_foreground_context(_window("notepad.exe", title="notes.txt - Notepad"))

    assert context["process_name"] == "notepad.exe"
    assert context["window_title"] == "notes.txt - Notepad"
    assert context["foreground_url"] == ""
