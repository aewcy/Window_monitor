"""
前台上下文采集

职责：
1. 获取当前前台程序上下文
2. 尝试为前台浏览器解析当前完整 URL（最佳努力）

历史截图是否保存由 Server 统一决定，Agent 只上报原始前台上下文。
"""
from __future__ import annotations

import os
import sqlite3
import shutil
import tempfile
import threading
from datetime import datetime, timedelta, timezone

from app_tracker import get_active_window
from browser_history import _chromium_time_to_local_naive
from config import BROWSER_PATHS


_BROWSER_PROCESS_MAP = {
    "chrome.exe": "chrome",
    "msedge.exe": "edge",
    "firefox.exe": "firefox",
    "brave.exe": "brave",
    "bravebrowser.exe": "brave",
    "chromium.exe": "chromium",
}

_BROWSER_TITLE_SUFFIXES = {
    "chrome": [" - Google Chrome", " - Chrome"],
    "edge": [" - Microsoft Edge", " - Edge"],
    "firefox": [" - Mozilla Firefox", " - Firefox"],
    "brave": [" - Brave", " - Brave Browser"],
    "chromium": [" - Chromium"],
}

_CHROMIUM_EPOCH_UTC = datetime(1601, 1, 1, tzinfo=timezone.utc)


def _normalize_process_name(value: str) -> str:
    return (value or "").strip().lower()


def _copy_db(db_path: str) -> str | None:
    try:
        if not db_path or not os.path.exists(db_path):
            return None
        fd, tmp_path = tempfile.mkstemp(suffix=".db", prefix="fg_browser_")
        os.close(fd)
        shutil.copy2(db_path, tmp_path)
        return tmp_path
    except Exception:
        return None


def _normalize_window_title(browser_name: str, title: str) -> str:
    title = (title or "").strip()
    if not title:
        return ""
    for suffix in _BROWSER_TITLE_SUFFIXES.get(browser_name, []):
        if title.endswith(suffix):
            return title[: -len(suffix)].strip()
    return title


class ForegroundUrlResolver:
    """基于浏览器历史做前台 URL 最佳努力推断。"""

    def __init__(self):
        self._cache_lock = threading.Lock()
        self._cache: dict[tuple[str, str], tuple[datetime, str]] = {}
        self.cache_ttl_seconds = 3
        self.lookback_seconds = 180

    def resolve(self, process_name: str, window_title: str) -> str:
        browser_name = _BROWSER_PROCESS_MAP.get(_normalize_process_name(process_name))
        if not browser_name:
            return ""

        normalized_title = _normalize_window_title(browser_name, window_title)
        if not normalized_title:
            return ""

        cache_key = (browser_name, normalized_title)
        now = datetime.now()
        with self._cache_lock:
            cached = self._cache.get(cache_key)
            if cached and (now - cached[0]).total_seconds() <= self.cache_ttl_seconds:
                return cached[1]

        url = ""
        try:
            if browser_name == "firefox":
                url = self._resolve_firefox(normalized_title)
            else:
                url = self._resolve_chromium(browser_name, normalized_title)
        except Exception:
            url = ""

        with self._cache_lock:
            self._cache[cache_key] = (now, url)
        return url

    def _resolve_chromium(self, browser_name: str, window_title: str) -> str:
        db_path = os.path.expandvars(BROWSER_PATHS.get(browser_name, ""))
        tmp_path = _copy_db(db_path)
        if not tmp_path:
            return ""

        try:
            conn = sqlite3.connect(f"file:{tmp_path}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            lookback = datetime.now().astimezone() - timedelta(seconds=self.lookback_seconds)
            delta = lookback.astimezone(timezone.utc) - _CHROMIUM_EPOCH_UTC
            chrometime = int(delta.total_seconds() * 1_000_000)
            cursor.execute(
                """SELECT url, title, last_visit_time
                   FROM urls
                   WHERE last_visit_time > ?
                   ORDER BY last_visit_time DESC
                   LIMIT 80""",
                (chrometime,),
            )
            rows = cursor.fetchall()
            conn.close()
            return self._pick_best_url(window_title, rows, chromium=True)
        finally:
            try:
                os.remove(tmp_path)
            except Exception:
                pass

    def _resolve_firefox(self, window_title: str) -> str:
        import glob

        profile_dir = os.path.expandvars(BROWSER_PATHS.get("firefox", ""))
        if not profile_dir:
            return ""
        places_files = glob.glob(os.path.join(profile_dir, "*.default-release", "places.sqlite"))
        if not places_files:
            places_files = glob.glob(os.path.join(profile_dir, "*.default", "places.sqlite"))
        if not places_files:
            return ""

        tmp_path = _copy_db(places_files[0])
        if not tmp_path:
            return ""

        try:
            conn = sqlite3.connect(f"file:{tmp_path}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            lookback = int((datetime.now() - timedelta(seconds=self.lookback_seconds)).timestamp() * 1_000_000)
            cursor.execute(
                """SELECT p.url, p.title, h.visit_date
                   FROM moz_places p
                   JOIN moz_historyvisits h ON p.id = h.place_id
                   WHERE h.visit_date > ?
                   ORDER BY h.visit_date DESC
                   LIMIT 80""",
                (lookback,),
            )
            rows = cursor.fetchall()
            conn.close()
            return self._pick_best_url(window_title, rows, chromium=False)
        finally:
            try:
                os.remove(tmp_path)
            except Exception:
                pass

    def _pick_best_url(self, window_title: str, rows, chromium: bool) -> str:
        normalized_window = (window_title or "").strip().lower()
        if not normalized_window:
            return ""

        exact_matches = []
        partial_matches = []
        fresh_candidates = []

        for row in rows:
            row_title = (row["title"] or "").strip()
            row_title_lower = row_title.lower()
            url = row["url"] or ""
            if not url:
                continue

            if chromium:
                ts = _chromium_time_to_local_naive(row["last_visit_time"])
            else:
                ts = datetime.fromtimestamp((row["visit_date"] or 0) / 1_000_000)

            age_seconds = abs((datetime.now() - ts).total_seconds())
            record = (age_seconds, url)

            if row_title_lower == normalized_window:
                exact_matches.append(record)
            elif row_title_lower and (row_title_lower in normalized_window or normalized_window in row_title_lower):
                partial_matches.append(record)
            elif age_seconds <= 8:
                fresh_candidates.append(record)

        for bucket in (exact_matches, partial_matches, fresh_candidates):
            if bucket:
                bucket.sort(key=lambda item: item[0])
                return bucket[0][1]
        return ""


_foreground_url_resolver = ForegroundUrlResolver()


def get_foreground_context(window_info: dict | None = None) -> dict:
    """采集截图对应的前台原始信息，不参与历史保存决策。"""
    info = dict(window_info or get_active_window() or {})
    process_name = info.get("process_name", "")
    window_title = info.get("window_title", "")
    foreground_url = info.get("foreground_url") or _foreground_url_resolver.resolve(process_name, window_title)
    return {
        "process_name": process_name,
        "window_title": window_title,
        "foreground_url": foreground_url,
    }
