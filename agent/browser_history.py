"""
浏览器历史记录采集模块
读取 Chrome / Edge / Firefox 的历史记录数据库
"""
import os
import time
import sqlite3
import shutil
import threading
from datetime import datetime, timedelta

from config import BROWSER_PATHS


class BrowserHistoryCollector:
    """浏览器历史采集器"""

    def __init__(self, interval: int = 60):
        self.interval = interval
        self._running = False
        self._thread = None
        self._listeners = []
        # 记录上次采集时间，避免重复上报
        self._last_fetch_time: dict[str, datetime] = {}

    def add_listener(self, callback):
        """callback(history_data: list[dict])"""
        self._listeners.append(callback)

    def _copy_db(self, db_path: str) -> str | None:
        """复制数据库文件（避免被浏览器锁定）"""
        try:
            if not os.path.exists(db_path):
                return None
            tmp_path = db_path + f".tmp_{os.getpid()}"
            shutil.copy2(db_path, tmp_path)
            return tmp_path
        except Exception as e:
            print(f"[BrowserHistory] 复制数据库失败 {db_path}: {e}")
            return None

    def _read_chromium_history(self, db_path: str, browser_name: str) -> list[dict]:
        """读取 Chromium 系浏览器的历史记录 (Chrome / Edge / Brave 等)"""
        tmp_path = self._copy_db(db_path)
        if not tmp_path:
            return []

        results = []
        try:
            conn = sqlite3.connect(f"file:{tmp_path}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # 查询最近访问的URL（使用 Chromium 时间戳格式）
            # Chromium 时间戳是 1601-01-01 至今的微秒数
            last_fetch = self._last_fetch_time.get(browser_name)
            if last_fetch:
                # 转换为 Chromium 时间戳
                delta = last_fetch - datetime(1601, 1, 1)
                chrometime = int(delta.total_seconds() * 1_000_000)
                cursor.execute(
                    """SELECT url, title, visit_count, last_visit_time
                       FROM urls
                       WHERE last_visit_time > ?
                       ORDER BY last_visit_time DESC
                       LIMIT 100""",
                    (chrometime,)
                )
            else:
                # 首次采集，获取最近24小时
                one_day_ago = datetime.now() - timedelta(hours=24)
                delta = one_day_ago - datetime(1601, 1, 1)
                chrometime = int(delta.total_seconds() * 1_000_000)
                cursor.execute(
                    """SELECT url, title, visit_count, last_visit_time
                       FROM urls
                       WHERE last_visit_time > ?
                       ORDER BY last_visit_time DESC
                       LIMIT 100""",
                    (chrometime,)
                )

            for row in cursor.fetchall():
                # 将 Chromium 时间戳转换回 datetime
                ts = datetime(1601, 1, 1) + timedelta(microseconds=row["last_visit_time"])
                results.append({
                    "url": row["url"],
                    "title": row["title"] or "",
                    "visit_count": row["visit_count"],
                    "last_visit": ts.isoformat(),
                    "browser": browser_name,
                })

            conn.close()
            self._last_fetch_time[browser_name] = datetime.now()

        except Exception as e:
            print(f"[BrowserHistory] 读取 {browser_name} 历史失败: {e}")
        finally:
            try:
                os.remove(tmp_path)
            except Exception:
                pass

        return results

    def _read_firefox_history(self, profile_dir: str) -> list[dict]:
        """读取 Firefox 历史记录"""
        import glob

        results = []
        try:
            # 查找 places.sqlite
            places_files = glob.glob(os.path.join(profile_dir, "*.default-release", "places.sqlite"))
            if not places_files:
                places_files = glob.glob(os.path.join(profile_dir, "*.default", "places.sqlite"))
            if not places_files:
                return results

            db_path = places_files[0]
            tmp_path = self._copy_db(db_path)
            if not tmp_path:
                return results

            conn = sqlite3.connect(f"file:{tmp_path}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row

            last_fetch = self._last_fetch_time.get("firefox")
            if last_fetch:
                # Firefox 使用 Unix 时间戳（微秒）
                ts_unix = int(last_fetch.timestamp() * 1_000_000)
                cursor = conn.execute(
                    """SELECT p.url, p.title, p.visit_count, h.visit_date
                       FROM moz_places p
                       JOIN moz_historyvisits h ON p.id = h.place_id
                       WHERE h.visit_date > ?
                       ORDER BY h.visit_date DESC
                       LIMIT 100""",
                    (ts_unix,)
                )
            else:
                one_day_ago = int((datetime.now() - timedelta(hours=24)).timestamp() * 1_000_000)
                cursor = conn.execute(
                    """SELECT p.url, p.title, p.visit_count, h.visit_date
                       FROM moz_places p
                       JOIN moz_historyvisits h ON p.id = h.place_id
                       WHERE h.visit_date > ?
                       ORDER BY h.visit_date DESC
                       LIMIT 100""",
                    (one_day_ago,)
                )

            for row in cursor.fetchall():
                ts = datetime.fromtimestamp(row["visit_date"] / 1_000_000)
                results.append({
                    "url": row["url"],
                    "title": row["title"] or "",
                    "visit_count": row["visit_count"] or 1,
                    "last_visit": ts.isoformat(),
                    "browser": "firefox",
                })

            conn.close()
            self._last_fetch_time["firefox"] = datetime.now()

            try:
                os.remove(tmp_path)
            except Exception:
                pass

        except Exception as e:
            print(f"[BrowserHistory] 读取 Firefox 历史失败: {e}")

        return results

    def collect(self) -> list[dict]:
        """执行一次完整采集"""
        all_results = []

        # Chromium 系浏览器 (共享相同的历史数据库格式)
        chromium_browsers = ["chrome", "chromium", "edge", "brave"]
        for browser in chromium_browsers:
            path = BROWSER_PATHS.get(browser, "")
            if path and os.path.exists(path):
                results = self._read_chromium_history(path, browser)
                all_results.extend(results)
                if results:
                    print(f"[BrowserHistory] {browser}: 采集 {len(results)} 条")

        # Firefox (使用不同的数据库结构)
        firefox_path = BROWSER_PATHS.get("firefox", "")
        if firefox_path and os.path.exists(firefox_path):
            results = self._read_firefox_history(firefox_path)
            all_results.extend(results)
            if results:
                print(f"[BrowserHistory] firefox: 采集 {len(results)} 条")

        return all_results

    def _loop(self):
        while self._running:
            results = self.collect()
            if results:
                for cb in self._listeners:
                    try:
                        cb(results)
                    except Exception as e:
                        print(f"[BrowserHistory] 回调异常: {e}")
            time.sleep(self.interval)

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print(f"[BrowserHistory] 已启动，间隔 {self.interval}s")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        print("[BrowserHistory] 已停止")
