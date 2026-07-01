"""
Agent 后台更新模块。

职责:
- 定期检查服务端是否允许当前 Agent 更新。
- 下载新版 exe 并校验 SHA256。
- 调用独立 updater.ps1 完成替换和重启。
"""
import hashlib
import json
import os
import subprocess
import sys
import threading
import time

import requests

from config import (
    AGENT_VERSION,
    IS_WINDOWS,
    UPDATE_CHECK_INTERVAL,
    UPDATE_DOWNLOAD_CONNECT_TIMEOUT,
    UPDATE_DOWNLOAD_READ_TIMEOUT,
    UPDATE_ENABLED,
)


def _version_tuple(value: str) -> tuple[int, ...]:
    text = str(value or "").strip().lower().lstrip("v")
    parts = []
    for item in text.split("."):
        try:
            parts.append(int(item))
        except ValueError:
            parts.append(0)
    return tuple(parts or [0])


def is_newer_version(latest: str, current: str) -> bool:
    return _version_tuple(latest) > _version_tuple(current)


class AutoUpdater:
    """后台更新器：只在服务端允许当前 Agent 更新时执行。"""

    def __init__(self, server_url: str, agent_name: str, reporter, machine_id: str):
        self.url = server_url.rstrip("/")
        self.agent = agent_name
        self.reporter = reporter
        self.machine_id = machine_id
        self.install_dir = os.path.dirname(sys.executable if getattr(sys, "frozen", False) else __file__)
        self.download_dir = os.path.join(self.install_dir, "downloads")
        self.updater_path = os.path.join(self.install_dir, "updater.ps1")
        self.state_path = os.path.join(self.install_dir, "update-state.json")
        self._stop = threading.Event()
        self._running_update = False

    def start(self):
        if not self._can_update():
            return
        os.makedirs(self.download_dir, exist_ok=True)
        self._report_pending_state()
        thread = threading.Thread(target=self._loop, daemon=True, name="auto-updater")
        thread.start()

    def _can_update(self) -> bool:
        return bool(UPDATE_ENABLED and IS_WINDOWS and getattr(sys, "frozen", False))

    def _report(self, status: str, message: str = "", target_version: str = "", error: str = ""):
        self.reporter.status(
            "online",
            message or f"update {status}",
            self.machine_id,
            update_status=status,
            update_target_version=target_version,
            update_error=error,
        )

    def _report_pending_state(self):
        if not os.path.exists(self.state_path):
            self._report("idle", "Agent running")
            return
        try:
            with open(self.state_path, "r", encoding="utf-8") as f:
                state = json.load(f)
            status = state.get("status") or "idle"
            target = state.get("target_version") or ""
            message = state.get("message") or ""
            self._report(status, message, target, "" if status in ("updated", "idle") else message)
            if status in ("updated", "rolled_back", "failed"):
                os.remove(self.state_path)
        except Exception as e:
            self._report("failed", "读取更新状态失败", error=str(e))

    def _loop(self):
        while not self._stop.is_set():
            try:
                self.check_once()
            except Exception as e:
                self._report("failed", "更新检查异常", error=str(e))
            self._stop.wait(max(60, int(UPDATE_CHECK_INTERVAL or 300)))

    def check_once(self):
        if self._running_update:
            return
        response = requests.get(
            f"{self.url}/api/agent/update/check",
            params={"agent": self.agent, "version": AGENT_VERSION},
            timeout=10,
        )
        if response.status_code != 200:
            return

        data = response.json()
        latest = data.get("version", "")
        if not data.get("update_available") or not data.get("allowed"):
            self._report("idle", "Agent update idle")
            return
        if not is_newer_version(latest, AGENT_VERSION):
            self._report("idle", "Agent already latest")
            return

        self._running_update = True
        try:
            self._install(data)
        finally:
            self._running_update = False

    def _install(self, data: dict):
        target_version = data.get("version", "")
        expected_sha = (data.get("sha256") or "").upper()
        exe_url = data.get("exe_url") or "/api/agent/exe"
        download_url = exe_url if exe_url.startswith("http") else f"{self.url}{exe_url}"
        target_path = os.path.join(self.download_dir, f"WindowsMonitor-{target_version}.exe")

        if not os.path.exists(self.updater_path):
            self._report("failed", "缺少 updater.ps1", target_version, "missing updater.ps1")
            return

        self._report("downloading", "正在下载更新", target_version)
        if not self._download_and_verify(download_url, target_path, expected_sha, target_version):
            return

        self._report("installing", "正在安装更新", target_version)
        self._launch_updater(target_path, target_version)
        time.sleep(1)
        os._exit(0)

    def _download_and_verify(self, download_url: str, target_path: str, expected_sha: str, target_version: str) -> bool:
        digest = hashlib.sha256()
        tmp_path = target_path + ".tmp"
        downloaded = 0
        last_reported_mb = -1

        try:
            with requests.get(
                download_url,
                stream=True,
                timeout=(UPDATE_DOWNLOAD_CONNECT_TIMEOUT, UPDATE_DOWNLOAD_READ_TIMEOUT),
            ) as response:
                response.raise_for_status()
                total = int(response.headers.get("content-length") or 0)
                total_mb = max(1, round(total / 1024 / 1024)) if total else 0
                with open(tmp_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if not chunk:
                            continue
                        digest.update(chunk)
                        f.write(chunk)
                        downloaded += len(chunk)
                        current_mb = downloaded // 1024 // 1024
                        if current_mb == 0 or current_mb - last_reported_mb < 10:
                            continue
                        last_reported_mb = current_mb
                        if total_mb:
                            self._report("downloading", f"正在下载更新 {current_mb}/{total_mb} MB", target_version)
                        else:
                            self._report("downloading", f"正在下载更新 {current_mb} MB", target_version)
        except Exception as e:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
            self._report("failed", "更新包下载失败", target_version, str(e))
            return False

        if downloaded <= 0:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
            self._report("failed", "更新包下载为空", target_version, "downloaded 0 bytes")
            return False

        actual_sha = digest.hexdigest().upper()
        if expected_sha and actual_sha != expected_sha:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
            self._report("failed", "更新包校验失败", error=f"sha256 {actual_sha} != {expected_sha}")
            return False

        os.replace(tmp_path, target_path)
        return True

    def _launch_updater(self, new_exe: str, target_version: str):
        creationflags = 0x00000008 | 0x08000000 if IS_WINDOWS else 0
        subprocess.Popen(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                self.updater_path,
                "-InstallDir",
                self.install_dir,
                "-NewExe",
                new_exe,
                "-TargetVersion",
                target_version,
            ],
            creationflags=creationflags,
            close_fds=True,
        )
