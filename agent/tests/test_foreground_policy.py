import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from foreground_context import get_foreground_context
from screen_capture import ScreenCapture


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


def test_capture_once_freezes_foreground_context_before_upload():
    capture = ScreenCapture()
    capture._capture_all = lambda: [("image", "2026-07-17T12:00:00", 0, 1)]
    capture.set_context_provider(lambda: {
        "process_name": "chrome.exe",
        "window_title": "TradingView - Google Chrome",
        "foreground_url": "https://cn.tradingview.com/chart/first",
    })

    frames = capture.capture_once()

    assert frames[0]["foreground_process_name"] == "chrome.exe"
    assert frames[0]["foreground_window_title"] == "TradingView - Google Chrome"
    assert frames[0]["foreground_url"] == "https://cn.tradingview.com/chart/first"
