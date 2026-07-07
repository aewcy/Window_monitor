"""
前台上下文与截图保存策略

职责：
1. 获取当前前台程序上下文
2. 尝试为前台浏览器解析当前完整 URL（最佳努力）
3. 根据服务端下发的特殊名单决定历史截图是否保存
"""
from __future__ import annotations

import os
import sqlite3
import shutil
import tempfile
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

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


def _extract_domain(url: str) -> str:
    if not url:
        return ""
    try:
        return (urlsplit(url).hostname or "").lower()
    except Exception:
        return ""


@dataclass
class MatchRule:
    id: int
    rule_type: str
    pattern: str
    enabled: bool = True


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


class ForegroundSavePolicy:
    """前台名单策略：

    - 非名单对象：正常保存历史截图
    - 名单对象：前 10 秒正常保存，之后仅 5 分钟补一张
    - 切走/切回视为新前台会话
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._resolver = ForegroundUrlResolver()
        self._rules: list[MatchRule] = []
        self._warmup_seconds = 10
        self._keepalive_seconds = 300
        self._session_key = ""
        self._session_started_at: datetime | None = None
        self._last_history_saved_at: datetime | None = None

    def update_config(self, rules: list[dict] | None, warmup_seconds: int | float = 10,
                      keepalive_seconds: int | float = 300):
        normalized_rules: list[MatchRule] = []
        for item in rules or []:
            pattern = (item.get("pattern") or "").strip()
            rule_type = (item.get("rule_type") or "").strip()
            if not pattern or rule_type not in {"process", "url_contains"}:
                continue
            normalized_rules.append(
                MatchRule(
                    id=int(item.get("id") or 0),
                    rule_type=rule_type,
                    pattern=pattern,
                    enabled=bool(item.get("enabled", True)),
                )
            )

        with self._lock:
            self._rules = normalized_rules
            self._warmup_seconds = max(0, int(warmup_seconds or 0))
            self._keepalive_seconds = max(1, int(keepalive_seconds or 300))

    def evaluate(self, window_info: dict | None = None, now: datetime | None = None) -> dict:
        current_time = now or datetime.now()
        info = dict(window_info or get_active_window() or {})
        process_name = info.get("process_name", "")
        window_title = info.get("window_title", "")
        foreground_url = info.get("foreground_url") or self._resolver.resolve(process_name, window_title)
        context = {
            "process_name": process_name,
            "window_title": window_title,
            "foreground_url": foreground_url,
            "foreground_domain": _extract_domain(foreground_url),
        }

        with self._lock:
            matched = self._match_rule(context)
            if not matched:
                self._reset_session_locked()
                return {
                    **context,
                    "store_history": True,
                    "save_policy_phase": "default",
                    "matched_rule_type": "",
                    "matched_rule_pattern": "",
                }

            session_key = self._build_session_key(context, matched)
            if session_key != self._session_key:
                self._session_key = session_key
                self._session_started_at = current_time
                self._last_history_saved_at = None

            elapsed = (current_time - (self._session_started_at or current_time)).total_seconds()
            if elapsed < self._warmup_seconds:
                return {
                    **context,
                    "store_history": True,
                    "save_policy_phase": "warmup",
                    "matched_rule_type": matched.rule_type,
                    "matched_rule_pattern": matched.pattern,
                }

            if self._last_history_saved_at is None:
                return {
                    **context,
                    "store_history": True,
                    "save_policy_phase": "post_warmup_first",
                    "matched_rule_type": matched.rule_type,
                    "matched_rule_pattern": matched.pattern,
                }

            since_last = (current_time - self._last_history_saved_at).total_seconds()
            if since_last >= self._keepalive_seconds:
                return {
                    **context,
                    "store_history": True,
                    "save_policy_phase": "keepalive",
                    "matched_rule_type": matched.rule_type,
                    "matched_rule_pattern": matched.pattern,
                }

            return {
                **context,
                "store_history": False,
                "save_policy_phase": "suppressed",
                "matched_rule_type": matched.rule_type,
                "matched_rule_pattern": matched.pattern,
            }

    def mark_saved(self, decision: dict, when: datetime | None = None):
        if not decision.get("store_history"):
            return
        with self._lock:
            if decision.get("matched_rule_type"):
                self._last_history_saved_at = when or datetime.now()
            else:
                self._reset_session_locked()

    def _match_rule(self, context: dict) -> MatchRule | None:
        process_name = _normalize_process_name(context.get("process_name", ""))
        foreground_url = (context.get("foreground_url") or "").strip().lower()

        for rule in self._rules:
            if not rule.enabled:
                continue
            if rule.rule_type == "url_contains" and foreground_url and rule.pattern.lower() in foreground_url:
                return rule
        for rule in self._rules:
            if not rule.enabled:
                continue
            if rule.rule_type == "process" and process_name == rule.pattern.lower():
                return rule
        return None

    def _build_session_key(self, context: dict, rule: MatchRule) -> str:
        if rule.rule_type == "url_contains":
            return f"url:{rule.id}:{context.get('foreground_url', '')}"
        return f"process:{rule.id}:{_normalize_process_name(context.get('process_name', ''))}"

    def _reset_session_locked(self):
        self._session_key = ""
        self._session_started_at = None
        self._last_history_saved_at = None
