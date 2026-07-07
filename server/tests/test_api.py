"""
后端 API 测试 — 基于 docs/backend-requirements.md 需求规格
运行: cd server && python -m pytest tests/ -v
"""
import base64
import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta

import pytest

# 将 server 目录加入 Python 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ============================================================
# 全局 fixtures
# ============================================================

@pytest.fixture(autouse=True)
def setup_test_env(tmp_path):
    """每个测试使用独立的临时数据库"""
    data_dir = str(tmp_path / "data")
    os.environ["DATA_DIR"] = data_dir
    # 重新加载 config 模块以读取新的 DATA_DIR
    import importlib
    import config
    config.DATA_DIR = data_dir
    config.SCREENSHOT_DIR = os.path.join(data_dir, "screenshots")
    config.DB_PATH = os.path.join(data_dir, "monitor.db")
    # 重置线程本地连接
    import models
    models.DB_PATH = config.DB_PATH
    models.SCREENSHOT_DIR = config.SCREENSHOT_DIR
    if hasattr(models._local, "conn"):
        models._local.conn = None
    # 清除 viewer 状态
    import routes
    routes._viewer_last_seen.clear()
    routes._agent_intervals.clear()
    routes._latest_live_frames.clear()
    routes._live_frame_buffers.clear()
    routes._history_policy_sessions.clear()
    routes.LIVE_DELAY_SECONDS = 5
    routes.LIVE_BUFFER_SECONDS = 15
    routes.AGENT_RELEASES_DIR = os.path.join(data_dir, "releases", "agent")
    yield


@pytest.fixture
def client(setup_test_env):
    """创建测试客户端，触发 lifespan 初始化数据库"""
    from fastapi.testclient import TestClient
    from main import app
    with TestClient(app) as c:
        yield c


# ============================================================
# 辅助函数
# ============================================================

def _make_jpeg_b64() -> str:
    """生成一个最小的有效 JPEG base64 数据"""
    jpeg_bytes = b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9'
    return base64.b64encode(jpeg_bytes).decode()


def _register_agent(c, name: str = "test-agent"):
    """通过心跳注册一个 Agent"""
    c.post("/api/heartbeat", json={"agent_name": name})


def _upload_screenshot(c, agent: str = "test-agent", ts: str = None, monitor: int = 0):
    """上传一张截图并返回 ID"""
    if ts is None:
        ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    resp = c.post("/api/screenshot", json={
        "agent_name": agent,
        "timestamp": ts,
        "image_base64": _make_jpeg_b64(),
        "monitor_index": monitor,
        "monitor_total": 1,
    })
    return resp.json().get("id"), ts


def _login_web(client):
    headers = {"host": "monitor.local:14325"}
    tab_token = "tab-session-test"
    resp = client.post(
        "/api/auth/login",
        headers=headers,
        json={"username": "admin", "password": "wxnlyzds310", "tab_token": tab_token},
    )
    return headers, tab_token, resp


def _prepare_agent_release(version: str, routes_module=None):
    """在测试临时 releases 目录准备一组 Agent 发布包。"""
    if routes_module is None:
        import routes as routes_module
    target_dir = os.path.join(routes_module.AGENT_RELEASES_DIR, version)
    os.makedirs(target_dir, exist_ok=True)
    exe_path = os.path.join(target_dir, routes_module.AGENT_RELEASE_EXE_NAME)
    setup_path = os.path.join(target_dir, routes_module.AGENT_RELEASE_SETUP_NAME)
    shutil.copy2(routes_module.AGENT_EXE_PATH, exe_path)
    shutil.copy2(routes_module.AGENT_SETUP_PATH, setup_path)
    return target_dir


# ============================================================
# 1. 健康检查
# ============================================================

class TestHealth:
    def test_health_ok(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "time" in data

    def test_agent_port_allows_api(self, client):
        resp = client.get("/api/health", headers={"host": "monitor.local:8899"})
        assert resp.status_code == 200

    def test_agent_port_blocks_web(self, client):
        resp = client.get("/", headers={"host": "monitor.local:8899"})
        assert resp.status_code == 503
        assert resp.content == b""

    def test_public_web_port_requires_login(self, client):
        resp = client.get("/", headers={"host": "monitor.local:14325"})
        assert resp.status_code == 200
        assert "CRKRD" in resp.text
        assert "password" in resp.text

    def test_public_web_api_requires_login(self, client):
        resp = client.get("/api/agents", headers={"host": "monitor.local:14325"})
        assert resp.status_code == 401
        assert resp.content == b""

    def test_public_web_login_allows_dashboard_and_download(self, client):
        headers, tab_token, resp = _login_web(client)
        assert resp.status_code == 200
        assert "crkrd_session" in resp.cookies

        dashboard = client.get("/", headers=headers)
        assert dashboard.status_code == 200
        assert "crkrd_tab_session" in dashboard.text

        download = client.get("/download", headers=headers)
        assert download.status_code == 200
        assert "CRKRD 下载" in download.text

        api_headers = {**headers, "X-CRKRD-Tab-Session": tab_token}
        agents = client.get("/api/agents", headers=api_headers)
        assert agents.status_code == 200

    def test_public_web_api_requires_matching_tab_token(self, client):
        headers, _, resp = _login_web(client)
        assert resp.status_code == 200

        missing = client.get("/api/agents", headers=headers)
        assert missing.status_code == 401

        wrong = client.get("/api/agents", headers={**headers, "X-CRKRD-Tab-Session": "wrong-token"})
        assert wrong.status_code == 401

    def test_public_web_login_rejects_wrong_password(self, client):
        resp = client.post(
            "/api/auth/login",
            headers={"host": "monitor.local:14325"},
            json={"username": "admin", "password": "wrong", "tab_token": "tab-session-test"},
        )
        assert resp.status_code == 401


# ============================================================
# 2. 观察者心跳与动态配置
# ============================================================

class TestViewerHeartbeat:
    def test_heartbeat_returns_ok(self, client):
        resp = client.post("/api/viewer/heartbeat")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_live_mode_after_heartbeat(self, client):
        """发送 viewer heartbeat 后，config 应返回 LIVE 模式"""
        client.post("/api/viewer/heartbeat")
        resp = client.get("/api/config")
        data = resp.json()
        assert data["screenshot_interval"] == 1

    def test_normal_mode_without_heartbeat(self, client):
        """无 viewer heartbeat 时，config 应返回正常模式"""
        resp = client.get("/api/config")
        data = resp.json()
        assert data["screenshot_interval"] == 5

    def test_config_app_track_interval(self, client):
        resp = client.get("/api/config")
        assert resp.json()["app_track_interval"] == 2

    def test_config_includes_special_screenshot_rules(self, client):
        client.post("/api/screenshot-rules", json={
            "rule_type": "process",
            "pattern": "wechat.exe",
            "enabled": True,
        })
        resp = client.get("/api/config")
        data = resp.json()
        assert data["special_screenshot_rule_warmup_seconds"] == 10
        assert data["special_screenshot_rule_keepalive_seconds"] == 300
        assert data["special_screenshot_rules"][0]["pattern"] == "wechat.exe"


class TestScreenshotRules:
    def test_rule_crud(self, client):
        create = client.post("/api/screenshot-rules", json={
            "rule_type": "url_contains",
            "pattern": "youtube.com/watch",
            "enabled": True,
        })
        assert create.status_code == 200
        item = create.json()["item"]
        assert item["rule_type"] == "url_contains"

        listing = client.get("/api/screenshot-rules")
        assert listing.status_code == 200
        items = listing.json()["items"]
        assert any(row["id"] == item["id"] for row in items)

        updated = client.patch(f"/api/screenshot-rules/{item['id']}", json={
            "enabled": False,
            "pattern": "youtube.com/live",
        })
        assert updated.status_code == 200
        assert updated.json()["item"]["enabled"] == 0
        assert updated.json()["item"]["pattern"] == "youtube.com/live"

        deleted = client.delete(f"/api/screenshot-rules/{item['id']}")
        assert deleted.status_code == 200
        assert deleted.json()["status"] == "ok"


# ============================================================
# 3. Agent 心跳与状态
# ============================================================

class TestAgentHeartbeat:
    def test_heartbeat_creates_agent(self, client):
        client.post("/api/heartbeat", json={"agent_name": "hb-agent"})
        resp = client.get("/api/agents")
        agents = [a["name"] for a in resp.json()]
        assert "hb-agent" in agents

    def test_heartbeat_updates_status(self, client):
        client.post("/api/heartbeat", json={"agent_name": "status-agent"})
        resp = client.get("/api/agents")
        agent = next(a for a in resp.json() if a["name"] == "status-agent")
        assert agent["status"] == "online"

    def test_status_updates_message(self, client):
        client.post("/api/status", json={
            "agent_name": "msg-agent",
            "status": "error",
            "message": "磁盘满"
        })
        resp = client.get("/api/agents")
        agent = next(a for a in resp.json() if a["name"] == "msg-agent")
        assert agent["status"] == "error"
        assert agent["message"] == "磁盘满"

    def test_heartbeat_updates_control_status(self, client):
        client.post("/api/heartbeat", json={
            "agent_name": "paused-agent",
            "control_status": "paused",
        })
        resp = client.get("/api/agents")
        agent = next(a for a in resp.json() if a["name"] == "paused-agent")
        assert agent["control_status"] == "paused"
        assert agent["control_updated_at"]


# ============================================================
# 4. Agent 管理
# ============================================================

class TestAgentManagement:
    def test_list_agents(self, client):
        resp = client.get("/api/agents")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_rename_agent(self, client):
        _register_agent(client, "rename-me")
        resp = client.patch("/api/agents/rename-me", json={"display_name": "新名称"})
        assert resp.status_code == 200
        assert resp.json()["display_name"] == "新名称"

    def test_rename_agent_reflected_in_list(self, client):
        """改名后 agents 列表应显示新的 display_name"""
        _register_agent(client, "rn-list-agent")
        client.patch("/api/agents/rn-list-agent", json={"display_name": "前端工位"})
        resp = client.get("/api/agents")
        agent = next(a for a in resp.json() if a["name"] == "rn-list-agent")
        assert agent["display_name"] == "前端工位"

    def test_rename_agent_preserves_name(self, client):
        """改名不应改变原始 name 字段"""
        _register_agent(client, "rn-keep-agent")
        client.patch("/api/agents/rn-keep-agent", json={"display_name": "随便改"})
        resp = client.get("/api/agents")
        agent = next(a for a in resp.json() if a["name"] == "rn-keep-agent")
        assert agent["name"] == "rn-keep-agent"
        assert agent["display_name"] == "随便改"

    def test_rename_agent_twice(self, client):
        """多次改名以最后一次为准"""
        _register_agent(client, "rn-twice-agent")
        client.patch("/api/agents/rn-twice-agent", json={"display_name": "名称1"})
        client.patch("/api/agents/rn-twice-agent", json={"display_name": "名称2"})
        resp = client.get("/api/agents")
        agent = next(a for a in resp.json() if a["name"] == "rn-twice-agent")
        assert agent["display_name"] == "名称2"

    def test_rename_agent_empty_name_400(self, client):
        _register_agent(client, "empty-name-agent")
        resp = client.patch("/api/agents/empty-name-agent", json={"display_name": "  "})
        assert resp.status_code == 400

    def test_rename_nonexistent_agent_404(self, client):
        resp = client.patch("/api/agents/nonexistent-xyz", json={"display_name": "x"})
        assert resp.status_code == 404

    def test_delete_agent(self, client):
        _register_agent(client, "del-agent")
        _upload_screenshot(client, "del-agent")
        resp = client.delete("/api/agents/del-agent")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        agents = [a["name"] for a in client.get("/api/agents").json()]
        assert "del-agent" not in agents

    def test_agent_command_lifecycle(self, client):
        _register_agent(client, "cmd-agent")

        created = client.post(
            "/api/agents/cmd-agent/commands",
            json={"command": "pause_capture"},
        )
        assert created.status_code == 200
        command = created.json()["command"]
        assert command["status"] == "pending"

        polled = client.get("/api/agent/commands/poll?agent=cmd-agent")
        assert polled.status_code == 200
        claimed = polled.json()["command"]
        assert claimed["id"] == command["id"]
        assert claimed["status"] == "claimed"
        assert claimed["command"] == "pause_capture"

        finished = client.post(
            f"/api/agent/commands/{claimed['id']}/result",
            json={"status": "done", "result": "采集已暂停"},
        )
        assert finished.status_code == 200

        empty = client.get("/api/agent/commands/poll?agent=cmd-agent")
        assert empty.status_code == 200
        assert empty.json()["command"] is None

    def test_agent_command_rejects_invalid_command(self, client):
        _register_agent(client, "cmd-invalid-agent")
        resp = client.post(
            "/api/agents/cmd-invalid-agent/commands",
            json={"command": "shutdown"},
        )
        assert resp.status_code == 400

    def test_agent_command_unknown_agent_404(self, client):
        resp = client.post(
            "/api/agents/no-such-agent/commands",
            json={"command": "pause_capture"},
        )
        assert resp.status_code == 404

    def test_delete_agent_returns_cascade_counts(self, client):
        """删除应返回级联删除的计数"""
        _register_agent(client, "del-count-agent")
        _upload_screenshot(client, "del-count-agent")
        ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        client.post("/api/app_event", json={
            "agent_name": "del-count-agent",
            "type": "window_switch",
            "window_title": "Test",
            "process_name": "test.exe",
            "timestamp": ts,
        })
        client.post("/api/browser_history", json={
            "agent_name": "del-count-agent",
            "records": [{"url": "https://test.com", "title": "T", "last_visit": ts, "browser": "chrome"}]
        })
        resp = client.delete("/api/agents/del-count-agent")
        assert resp.status_code == 200
        deleted = resp.json()["deleted"]
        assert deleted["screenshots"] >= 1
        assert deleted["app_events"] >= 1
        assert deleted["browser_history"] >= 1

    def test_delete_agent_clears_screenshots(self, client):
        """删除后截图列表应为空"""
        _register_agent(client, "del-ss-clear")
        _upload_screenshot(client, "del-ss-clear")
        client.delete("/api/agents/del-ss-clear")
        resp = client.get("/api/screenshots?agent=del-ss-clear")
        assert len(resp.json()) == 0

    def test_delete_agent_clears_app_events(self, client):
        """删除后应用事件应为空"""
        _register_agent(client, "del-ev-clear")
        ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        client.post("/api/app_event", json={
            "agent_name": "del-ev-clear",
            "type": "window_switch",
            "window_title": "Test",
            "process_name": "test.exe",
            "timestamp": ts,
        })
        client.delete("/api/agents/del-ev-clear")
        resp = client.get("/api/app_events?agent=del-ev-clear")
        assert len(resp.json()) == 0

    def test_delete_agent_clears_browser_history(self, client):
        """删除后浏览器历史应为空"""
        _register_agent(client, "del-bh-clear")
        ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        client.post("/api/browser_history", json={
            "agent_name": "del-bh-clear",
            "records": [{"url": "https://test.com", "title": "T", "last_visit": ts, "browser": "chrome"}]
        })
        client.delete("/api/agents/del-bh-clear")
        resp = client.get("/api/browser_history?agent=del-bh-clear")
        assert len(resp.json()) == 0

    def test_delete_agent_path_traversal_404(self, client):
        resp = client.delete("/api/agents/../evil")
        assert resp.status_code == 404

    def test_delete_nonexistent_agent_404(self, client):
        resp = client.delete("/api/agents/ghost-agent-xyz")
        assert resp.status_code == 404


# ============================================================
# 5. 截图上传与节流
# ============================================================

class TestScreenshot:
    def test_upload_screenshot(self, client):
        _register_agent(client, "ss-agent")
        sid, _ = _upload_screenshot(client, "ss-agent")
        assert sid is not None
        assert sid > 0

    def test_upload_empty_image_400(self, client):
        resp = client.post("/api/screenshot", json={
            "agent_name": "ss-agent",
            "image_base64": "",
        })
        assert resp.status_code == 400

    def test_throttle_2s_window(self, client):
        """2 秒内同 Agent 同显示器只保留第一张"""
        _register_agent(client, "throttle-agent")
        base_ts = datetime.now()
        ts1 = base_ts.strftime("%Y-%m-%dT%H:%M:%S")
        ts2 = (base_ts + timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%S")

        id1, _ = _upload_screenshot(client, "throttle-agent", ts1)
        id2, _ = _upload_screenshot(client, "throttle-agent", ts2)
        assert id1 == id2

    def test_throttle_2s_window_out_of_order_keeps_earliest(self, client):
        """乱序上传时，也应保留 2 秒窗口内时间更早的那张。"""
        _register_agent(client, "throttle-out-of-order")
        base_ts = datetime.now()
        ts_late = (base_ts + timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%S")
        ts_early = base_ts.strftime("%Y-%m-%dT%H:%M:%S")

        late_id, _ = _upload_screenshot(client, "throttle-out-of-order", ts_late)
        early_id, _ = _upload_screenshot(client, "throttle-out-of-order", ts_early)
        assert late_id != early_id

        rows = client.get("/api/screenshots?agent=throttle-out-of-order").json()
        assert len(rows) == 2
        assert rows[0]["timestamp"] == ts_late
        assert rows[1]["timestamp"] == ts_early

    def test_screenshot_can_skip_history_but_keep_live(self, client):
        _register_agent(client, "live-only-agent")
        ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        resp = client.post("/api/screenshot", json={
            "agent_name": "live-only-agent",
            "timestamp": ts,
            "image_base64": _make_jpeg_b64(),
            "monitor_index": 0,
            "monitor_total": 1,
            "store_history": False,
            "foreground_process_name": "WeChat.exe",
            "save_policy_phase": "suppressed",
        })
        assert resp.status_code == 200
        assert resp.json()["id"] is None

        rows = client.get("/api/screenshots?agent=live-only-agent").json()
        assert rows == []

        live = client.get("/api/screenshots/live/latest?agent=live-only-agent&monitor=0&fresh=true")
        assert live.status_code == 200
        live_data = live.json()
        assert live_data["timestamp"] == ts
        assert live_data["save_policy_phase"] == "suppressed"

    def test_server_policy_uses_recent_app_event_for_old_agent(self, client):
        _register_agent(client, "server-policy-agent")
        client.post("/api/screenshot-rules", json={
            "rule_type": "process",
            "pattern": "chrome.exe",
            "enabled": True,
        })
        base = datetime.now()
        client.post("/api/app_event", json={
            "agent_name": "server-policy-agent",
            "type": "app_switch",
            "process_name": "chrome.exe",
            "window_title": "cn.tradingview.com/chart",
            "timestamp": base.strftime("%Y-%m-%dT%H:%M:%S"),
        })

        first_id, _ = _upload_screenshot(
            client,
            "server-policy-agent",
            (base + timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%S"),
        )
        assert first_id is not None

        suppressed_id, _ = _upload_screenshot(
            client,
            "server-policy-agent",
            (base + timedelta(seconds=12)).strftime("%Y-%m-%dT%H:%M:%S"),
        )
        assert suppressed_id is None

        rows = client.get("/api/screenshots?agent=server-policy-agent").json()
        assert len(rows) == 1
        assert rows[0]["matched_rule_type"] == "process"
        assert rows[0]["save_policy_phase"] == "warmup"

        live = client.get("/api/screenshots/live/latest?agent=server-policy-agent&monitor=0&fresh=true")
        assert live.status_code == 200
        assert live.json()["save_policy_phase"] == "suppressed"

    def test_server_policy_url_rule_can_use_recent_browser_history(self, client):
        _register_agent(client, "server-url-policy-agent")
        client.post("/api/screenshot-rules", json={
            "rule_type": "url_contains",
            "pattern": "cn.tradingview.com",
            "enabled": True,
        })
        base = datetime.now()
        client.post("/api/app_event", json={
            "agent_name": "server-url-policy-agent",
            "type": "app_switch",
            "process_name": "chrome.exe",
            "window_title": "TradingView",
            "timestamp": base.strftime("%Y-%m-%dT%H:%M:%S"),
        })
        client.post("/api/browser_history", json={
            "agent_name": "server-url-policy-agent",
            "records": [{
                "url": "https://cn.tradingview.com/chart/abc?symbol=SSE%3A688686",
                "title": "TradingView",
                "last_visit": base.strftime("%Y-%m-%dT%H:%M:%S"),
                "browser": "chrome",
            }],
        })

        first_id, _ = _upload_screenshot(
            client,
            "server-url-policy-agent",
            (base + timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%S"),
        )
        assert first_id is not None
        suppressed_id, _ = _upload_screenshot(
            client,
            "server-url-policy-agent",
            (base + timedelta(seconds=12)).strftime("%Y-%m-%dT%H:%M:%S"),
        )
        assert suppressed_id is None

        rows = client.get("/api/screenshots?agent=server-url-policy-agent").json()
        assert rows[0]["matched_rule_type"] == "url_contains"
        assert "cn.tradingview.com" in rows[0]["foreground_url"]

    def test_server_policy_url_rule_uses_long_browser_history_for_old_agent(self, client):
        _register_agent(client, "server-url-long-agent")
        client.post("/api/screenshot-rules", json={
            "rule_type": "url_contains",
            "pattern": "cn.tradingview.com",
            "enabled": True,
        })
        base = datetime.now()
        client.post("/api/app_event", json={
            "agent_name": "server-url-long-agent",
            "type": "app_switch",
            "process_name": "chrome.exe",
            "window_title": "000300 4,792.2624 - Google Chrome",
            "timestamp": base.strftime("%Y-%m-%dT%H:%M:%S"),
        })
        client.post("/api/browser_history", json={
            "agent_name": "server-url-long-agent",
            "records": [{
                "url": "https://cn.tradingview.com/chart/YS9lFlYj/?symbol=SSE%3A000300",
                "title": "000300 4,792.2624",
                "last_visit": (base - timedelta(minutes=8)).strftime("%Y-%m-%dT%H:%M:%S"),
                "browser": "chrome",
            }],
        })

        first_id, _ = _upload_screenshot(
            client,
            "server-url-long-agent",
            (base + timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%S"),
        )
        suppressed_id, _ = _upload_screenshot(
            client,
            "server-url-long-agent",
            (base + timedelta(seconds=12)).strftime("%Y-%m-%dT%H:%M:%S"),
        )

        assert first_id is not None
        assert suppressed_id is None
        rows = client.get("/api/screenshots?agent=server-url-long-agent").json()
        assert rows[0]["matched_rule_type"] == "url_contains"
        assert "cn.tradingview.com" in rows[0]["foreground_url"]

    def test_screenshot_image_retrievable(self, client):
        _register_agent(client, "img-agent")
        sid, _ = _upload_screenshot(client, "img-agent")
        resp = client.get(f"/api/screenshots/image/{sid}")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/jpeg"

    def test_screenshot_derived_images_retrievable(self, client):
        _register_agent(client, "derived-img-agent")
        sid, _ = _upload_screenshot(client, "derived-img-agent")
        for variant in ("thumb", "preview"):
            resp = client.get(f"/api/screenshots/{variant}/{sid}")
            assert resp.status_code == 200
            assert resp.headers["content-type"] == "image/jpeg"

    def test_screenshot_thumbs_batch_retrievable(self, client):
        _register_agent(client, "thumbs-batch-agent")
        sid1, _ = _upload_screenshot(client, "thumbs-batch-agent")
        sid2, _ = _upload_screenshot(
            client,
            "thumbs-batch-agent",
            (datetime.now() + timedelta(seconds=3)).strftime("%Y-%m-%dT%H:%M:%S"),
        )
        resp = client.post("/api/screenshots/thumbs-batch", json={"ids": [sid1, sid2]})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["thumbs"]) == 2
        assert all(item["image_base64"] for item in data["thumbs"])

    def test_screenshot_image_not_found_404(self, client):
        resp = client.get("/api/screenshots/image/999999")
        assert resp.status_code == 404


# ============================================================
# 6. 截图查询
# ============================================================

class TestScreenshotQuery:
    def test_list_screenshots(self, client):
        _register_agent(client, "query-agent")
        _upload_screenshot(client, "query-agent")
        resp = client.get("/api/screenshots?agent=query-agent")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    def test_latest_screenshot(self, client):
        _register_agent(client, "latest-agent")
        _upload_screenshot(client, "latest-agent")
        resp = client.get("/api/screenshots/latest?agent=latest-agent")
        assert resp.status_code == 200
        assert "timestamp" in resp.json()

    def test_latest_screenshot_not_found_404(self, client):
        resp = client.get("/api/screenshots/latest?agent=no-screenshots-xyz")
        assert resp.status_code == 404

    def test_live_latest_uses_delayed_buffer(self, client):
        import routes

        routes.LIVE_DELAY_SECONDS = 5
        _register_agent(client, "live-delay-agent")
        _, ts = _upload_screenshot(client, "live-delay-agent", monitor=0)

        immediate = client.get("/api/screenshots/live/latest?agent=live-delay-agent&monitor=0")
        assert immediate.status_code == 404

        frame = routes._live_frame_buffers[("live-delay-agent", 0)][0]
        frame["_received_at"] = datetime.now() - timedelta(seconds=6)

        delayed = client.get("/api/screenshots/live/latest?agent=live-delay-agent&monitor=0")
        assert delayed.status_code == 200
        body = delayed.json()
        assert body["timestamp"] == ts
        assert "image_base64" in body
        assert "_received_at" not in body
        assert "_captured_at" not in body

    def test_live_latest_fresh_bypasses_delay_for_switching(self, client):
        import routes

        routes.LIVE_DELAY_SECONDS = 5
        _register_agent(client, "live-fresh-agent")
        _, ts = _upload_screenshot(client, "live-fresh-agent", monitor=0)

        immediate = client.get("/api/screenshots/live/latest?agent=live-fresh-agent&monitor=0")
        assert immediate.status_code == 404

        fresh = client.get("/api/screenshots/live/latest?agent=live-fresh-agent&monitor=0&fresh=true")
        assert fresh.status_code == 200
        body = fresh.json()
        assert body["timestamp"] == ts
        assert "image_base64" in body

    def test_live_latest_fresh_rejects_stale_frame(self, client):
        import routes

        routes.LIVE_DELAY_SECONDS = 100
        _register_agent(client, "live-stale-agent")
        _upload_screenshot(client, "live-stale-agent", monitor=0)
        frame = routes._latest_live_frames[("live-stale-agent", 0)]
        frame["_received_at"] = datetime.now() - timedelta(seconds=60)
        routes._live_frame_buffers[("live-stale-agent", 0)].clear()

        fresh = client.get("/api/screenshots/live/latest?agent=live-stale-agent&monitor=0&fresh=true&max_age=10")
        assert fresh.status_code == 404

    def test_screenshot_dates(self, client):
        _register_agent(client, "date-agent")
        _upload_screenshot(client, "date-agent")
        resp = client.get("/api/screenshots/dates?agent=date-agent")
        assert resp.status_code == 200
        dates = resp.json()
        assert len(dates) >= 1
        assert "date" in dates[0]
        assert "count" in dates[0]

    def test_screenshot_dates_range(self, client):
        _register_agent(client, "date-range-agent")
        _upload_screenshot(client, "date-range-agent", "2026-06-30T10:00:00")
        _upload_screenshot(client, "date-range-agent", "2026-07-01T10:00:00")

        resp = client.get(
            "/api/screenshots/dates?agent=date-range-agent"
            "&date_from=2026-07-01T00:00:00&date_to=2026-07-31T23:59:59"
        )
        assert resp.status_code == 200
        assert resp.json() == [{"date": "2026-07-01", "count": 1}]

    def test_screenshot_hours(self, client):
        _register_agent(client, "hour-agent")
        _upload_screenshot(client, "hour-agent")
        dates = client.get("/api/screenshots/dates?agent=hour-agent").json()
        if dates:
            date = dates[0]["date"]
            resp = client.get(f"/api/screenshots/hours?agent=hour-agent&date={date}")
            assert resp.status_code == 200
            hours = resp.json()
            assert len(hours) >= 1
            assert "hour" in hours[0]

    def test_delete_screenshot(self, client):
        _register_agent(client, "del-ss-agent")
        sid, _ = _upload_screenshot(client, "del-ss-agent")
        resp = client.delete(f"/api/screenshots/{sid}")
        assert resp.status_code == 200
        resp = client.get(f"/api/screenshots/image/{sid}")
        assert resp.status_code == 404

    def test_delete_batch(self, client):
        _register_agent(client, "batch-agent")
        id1, _ = _upload_screenshot(client, "batch-agent")
        id2, _ = _upload_screenshot(client, "batch-agent", ts=(datetime.now() + timedelta(seconds=3)).strftime("%Y-%m-%dT%H:%M:%S"))
        ids = [i for i in [id1, id2] if i]
        if ids:
            resp = client.post("/api/screenshots/delete-batch", json={"ids": ids})
            assert resp.status_code == 200

    def test_delete_batch_empty_ids_400(self, client):
        resp = client.post("/api/screenshots/delete-batch", json={"ids": []})
        assert resp.status_code == 400


# ============================================================
# 7. 应用事件
# ============================================================

class TestAppEvents:
    def test_save_app_event(self, client):
        _register_agent(client, "event-agent")
        resp = client.post("/api/app_event", json={
            "agent_name": "event-agent",
            "type": "window_switch",
            "window_title": "VS Code",
            "process_name": "Code.exe",
            "timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "duration_seconds": 120.5,
        })
        assert resp.status_code == 200

    def test_list_app_events(self, client):
        _register_agent(client, "list-event-agent")
        client.post("/api/app_event", json={
            "agent_name": "list-event-agent",
            "type": "window_switch",
            "window_title": "Test",
            "process_name": "test.exe",
            "timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        })
        resp = client.get("/api/app_events?agent=list-event-agent")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    def test_app_usage_summary(self, client):
        _register_agent(client, "usage-agent")
        client.post("/api/app_event", json={
            "agent_name": "usage-agent",
            "type": "window_switch",
            "window_title": "Chrome",
            "process_name": "chrome.exe",
            "timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "duration_seconds": 300,
        })
        resp = client.get("/api/app_usage?agent=usage-agent")
        assert resp.status_code == 200
        data = resp.json()
        if data:
            assert "process_name" in data[0]
            assert "total_seconds" in data[0]
            assert "total_minutes" in data[0]


# ============================================================
# 8. 浏览器历史
# ============================================================

class TestBrowserHistory:
    def test_save_browser_history(self, client):
        _register_agent(client, "browser-agent")
        resp = client.post("/api/browser_history", json={
            "agent_name": "browser-agent",
            "records": [{
                "url": "https://example.com",
                "title": "Example",
                "visit_count": 3,
                "last_visit": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                "browser": "chrome",
            }]
        })
        assert resp.status_code == 200
        assert resp.json()["count"] == 1

    def test_browser_history_dedup(self, client):
        """重复记录应该被忽略"""
        _register_agent(client, "dedup-agent")
        ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        record = {
            "agent_name": "dedup-agent",
            "records": [{
                "url": "https://dedup.com",
                "title": "Dedup",
                "last_visit": ts,
                "browser": "chrome",
            }]
        }
        client.post("/api/browser_history", json=record)
        client.post("/api/browser_history", json=record)
        resp = client.get("/api/browser_history?agent=dedup-agent")
        records = [r for r in resp.json() if r["url"] == "https://dedup.com"]
        assert len(records) == 1

    def test_list_browser_history(self, client):
        _register_agent(client, "bh-list-agent")
        ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        client.post("/api/browser_history", json={
            "agent_name": "bh-list-agent",
            "records": [{
                "url": "https://test.com",
                "title": "Test",
                "last_visit": ts,
                "browser": "chrome",
            }]
        })
        resp = client.get("/api/browser_history?agent=bh-list-agent")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1


# ============================================================
# 9. 诊断日志
# ============================================================

class TestDiagnostics:
    def test_save_diagnostic(self, client):
        _register_agent(client, "diag-agent")
        resp = client.post("/api/diagnostics", json={
            "agent_name": "diag-agent",
            "category": "network",
            "level": "ERROR",
            "message": "上传截图失败: 连接超时",
        })
        assert resp.status_code == 200
        assert resp.json()["id"] > 0

    def test_diagnostic_level_uppercase(self, client):
        """level 应自动转为大写"""
        _register_agent(client, "diag-lvl-agent")
        client.post("/api/diagnostics", json={
            "agent_name": "diag-lvl-agent",
            "category": "system",
            "level": "warning",
            "message": "测试小写级别",
        })
        resp = client.get("/api/logs?limit=10")
        log = next((l for l in resp.json() if l["message"] == "测试小写级别"), None)
        assert log is not None
        assert log["level"] == "WARNING"

    def test_diagnostic_invalid_category_fallback(self, client):
        """非法 category 应回退为 system"""
        _register_agent(client, "diag-cat-agent")
        client.post("/api/diagnostics", json={
            "agent_name": "diag-cat-agent",
            "category": "invalid_cat",
            "message": "测试非法分类",
        })
        resp = client.get("/api/logs?limit=10")
        log = next((l for l in resp.json() if l["message"] == "测试非法分类"), None)
        assert log is not None
        assert log["category"] == "system"

    def test_diagnostic_empty_message_400(self, client):
        resp = client.post("/api/diagnostics", json={
            "category": "system",
            "message": "",
        })
        assert resp.status_code == 400

    def test_list_logs(self, client):
        resp = client.get("/api/logs?limit=10")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_log_categories(self, client):
        resp = client.get("/api/logs/categories")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


# ============================================================
# 10. 统计与存储
# ============================================================

class TestStatsAndStorage:
    def test_dashboard_stats(self, client):
        resp = client.get("/api/dashboard/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_screenshots" in data
        assert "today_app_events" in data
        assert "total_browser_records" in data
        assert "online_agents" in data

    def test_storage_stats(self, client):
        resp = client.get("/api/storage/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_size_bytes" in data
        assert "total_count" in data
        assert "agents" in data

    def test_storage_cleanup_invalid_hours_400(self, client):
        resp = client.post("/api/storage/cleanup", json={"older_than_hours": 0})
        assert resp.status_code == 400

    def test_storage_cleanup_removes_old_screenshots(self, client):
        _register_agent(client, "cleanup-agent")
        old_ts = (datetime.now() - timedelta(hours=50)).strftime("%Y-%m-%dT%H:%M:%S")
        new_ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        old_id, _ = _upload_screenshot(client, "cleanup-agent", old_ts)
        new_id, _ = _upload_screenshot(client, "cleanup-agent", new_ts)

        resp = client.post("/api/storage/cleanup", json={"older_than_hours": 24, "agent": "cleanup-agent"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["deleted_count"] == 1
        assert data["freed_bytes"] > 0

        rows = client.get("/api/screenshots?agent=cleanup-agent").json()
        ids = [row["id"] for row in rows]
        assert old_id not in ids
        assert new_id in ids


# ============================================================
# 11. Agent 后台更新
# ============================================================

class TestAgentUpdate:
    def test_agent_version_metadata(self, client):
        resp = client.get("/api/agent/version")
        assert resp.status_code == 200
        data = resp.json()
        assert data["version"] == "0.59.0"
        assert data["exe_url"] == "/api/agent/exe"
        assert data["sha256"]
        assert data["size_bytes"] > 0

    def test_register_and_activate_release_version(self, client):
        import routes
        _prepare_agent_release("0.60.0", routes)

        registered = client.post("/api/agent/versions/register", json={"version": "0.60.0"})
        assert registered.status_code == 200
        assert registered.json()["version"]["version"] == "0.60.0"
        assert registered.json()["version"]["is_active"] is False

        before = client.get("/api/agent/version")
        assert before.json()["version"] == "0.59.0"

        activated = client.post("/api/agent/versions/0.60.0/activate")
        assert activated.status_code == 200
        assert activated.json()["version"]["version"] == "0.60.0"
        assert activated.json()["version"]["is_active"] is True

        current = client.get("/api/agent/version")
        assert current.json()["version"] == "0.60.0"
        assert current.json()["package_exe_url"].endswith("/api/agent/packages/0.60.0/exe")

    def test_activate_missing_release_fails(self, client):
        resp = client.post("/api/agent/versions/9.99.9/activate")
        assert resp.status_code == 404

    def test_allow_agent_update_then_check(self, client):
        client.post("/api/heartbeat", json={
            "agent_name": "update-agent",
            "agent_version": "0.50",
            "machine_id": "machine-update",
            "install_id": "install-update",
        })

        allow = client.post("/api/agents/update-agent/update/allow", json={})
        assert allow.status_code == 200
        assert allow.json()["version"] == "0.59.0"
        assert allow.json()["job"]["status"] == "pending"

        check = client.get("/api/agent/update/check?agent=update-agent&version=0.50")
        assert check.status_code == 200
        data = check.json()
        assert data["update_available"] is True
        assert data["allowed"] is True
        assert data["job"]["target_version"] == "0.59.0"

    def test_pause_agent_update(self, client):
        client.post("/api/heartbeat", json={"agent_name": "pause-agent", "agent_version": "0.50"})
        client.post("/api/agents/pause-agent/update/allow", json={})

        pause = client.post("/api/agents/pause-agent/update/pause")
        assert pause.status_code == 200

        check = client.get("/api/agent/update/check?agent=pause-agent&version=0.50")
        assert check.status_code == 200
        assert check.json()["allowed"] is False

    def test_failed_update_keeps_permission_for_retry(self, client):
        client.post("/api/heartbeat", json={"agent_name": "retry-agent", "agent_version": "0.50"})
        client.post("/api/agents/retry-agent/update/allow", json={})

        failed = client.post("/api/heartbeat", json={
            "agent_name": "retry-agent",
            "agent_version": "0.50",
            "update_status": "failed",
            "update_target_version": "0.59.0",
            "update_error": "network reset",
        })
        assert failed.status_code == 200

        check = client.get("/api/agent/update/check?agent=retry-agent&version=0.50")
        assert check.status_code == 200
        data = check.json()
        assert data["allowed"] is True
        assert data["allowed_version"] == "0.59.0"

    def test_updater_claims_job_and_reports_progress(self, client):
        client.post("/api/heartbeat", json={
            "agent_name": "job-agent",
            "agent_version": "0.50",
            "machine_id": "machine-job",
            "install_id": "install-job",
        })
        allow = client.post("/api/agents/job-agent/update/allow", json={})
        job_id = allow.json()["job"]["job_id"]

        claimed = client.get(
            "/api/updater/jobs/next?install_id=install-job&machine_id=machine-job&updater_version=0.59.0"
        )
        assert claimed.status_code == 200
        data = claimed.json()
        assert data["job"]["job_id"] == job_id
        assert data["job"]["status"] == "claimed"
        assert data["version"]["package_exe_url"].endswith("/api/agent/packages/0.59.0/exe")

        progress = client.post(f"/api/updater/jobs/{job_id}/heartbeat", json={
            "status": "downloading",
            "progress_bytes": 1024,
            "total_bytes": 2048,
            "message": "下载中",
        })
        assert progress.status_code == 200
        assert progress.json()["job"]["status"] == "downloading"
        assert progress.json()["job"]["progress_bytes"] == 1024
        client.post(f"/api/updater/jobs/{job_id}/finish", json={"status": "failed", "error": "test done"})

    def test_update_job_returns_target_version_package(self, client):
        import routes
        _prepare_agent_release("0.60.0", routes)
        client.post("/api/agent/versions/register", json={"version": "0.60.0", "activate": True})
        client.post("/api/heartbeat", json={
            "agent_name": "version-bound-agent",
            "agent_version": "0.50",
            "machine_id": "machine-bound",
            "install_id": "install-bound",
        })

        allow = client.post("/api/agents/version-bound-agent/update/allow", json={"version": "0.60.0"})
        assert allow.status_code == 200
        assert allow.json()["job"]["target_version"] == "0.60.0"

        # 激活版本切回旧版后，已创建 job 仍应下载 0.60.0，避免任务漂移。
        client.post("/api/agent/versions/0.59.0/activate")
        claimed = client.get(
            "/api/updater/jobs/next?install_id=install-bound&machine_id=machine-bound&updater_version=0.59.0"
        )
        assert claimed.status_code == 200
        data = claimed.json()
        assert data["job"]["target_version"] == "0.60.0"
        assert data["version"]["version"] == "0.60.0"
        assert data["version"]["package_exe_url"].endswith("/api/agent/packages/0.60.0/exe")

    def test_agent_heartbeat_verifies_update_job(self, client):
        client.post("/api/heartbeat", json={
            "agent_name": "verify-agent",
            "agent_version": "0.50",
            "machine_id": "machine-verify",
            "install_id": "install-verify",
        })
        job_id = client.post("/api/agents/verify-agent/update/allow", json={}).json()["job"]["job_id"]
        client.get("/api/updater/jobs/next?install_id=install-verify&machine_id=machine-verify&updater_version=0.59.0")
        client.post(f"/api/updater/jobs/{job_id}/heartbeat", json={"status": "verifying", "message": "等待心跳"})

        hb = client.post("/api/heartbeat", json={
            "agent_name": "verify-agent",
            "agent_version": "0.59.0",
            "machine_id": "machine-verify",
            "install_id": "install-verify",
            "update_job_id": job_id,
        })
        assert hb.status_code == 200

        latest = client.get("/api/agents/verify-agent/update/jobs/latest")
        assert latest.status_code == 200
        assert latest.json()["job"]["status"] == "verified"

    def test_offline_pending_does_not_block_online_active_job(self, client):
        client.post("/api/heartbeat", json={"agent_name": "offline-target", "agent_version": "0.50", "machine_id": "machine-offline"})
        # 让在线状态自然变成旧记录语义：直接把状态置为 offline，模拟离线机器。
        client.post("/api/status", json={"agent_name": "offline-target", "status": "offline", "message": "offline"})
        offline_job = client.post("/api/agents/offline-target/update/allow", json={})
        assert offline_job.status_code == 200
        assert offline_job.json()["job"]["status"] == "pending"

        client.post("/api/heartbeat", json={"agent_name": "online-target", "agent_version": "0.50", "machine_id": "machine-online"})
        online_job = client.post("/api/agents/online-target/update/allow", json={})
        assert online_job.status_code == 200
        assert online_job.json()["job"]["status"] == "pending"


# ============================================================
# 12. 安全响应头
# ============================================================

class TestSecurityHeaders:
    def test_security_headers_present(self, client):
        resp = client.get("/api/health")
        assert resp.headers.get("x-content-type-options") == "nosniff"
        assert resp.headers.get("x-frame-options") == "DENY"
        assert resp.headers.get("x-xss-protection") == "1; mode=block"
        assert resp.headers.get("referrer-policy") == "strict-origin-when-cross-origin"


# ============================================================
# 13. 截图-事件关联
# ============================================================

class TestScreenshotEventCorrelation:
    def test_app_events_with_screenshots(self, client):
        """事件应能关联到截图"""
        _register_agent(client, "corr-agent")
        # 先上传截图，再发事件，确保截图时间早于事件时间
        ts_base = datetime.now() - timedelta(seconds=2)
        ts_ss = ts_base.strftime("%Y-%m-%dT%H:%M:%S")
        _upload_screenshot(client, "corr-agent", ts_ss)
        ts_event = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        client.post("/api/app_event", json={
            "agent_name": "corr-agent",
            "type": "window_switch",
            "window_title": "Test",
            "process_name": "test.exe",
            "timestamp": ts_event,
            "screenshot_timestamp": ts_ss,
        })
        resp = client.get("/api/app_events?agent=corr-agent&with_screenshots=true")
        events = resp.json()
        if events:
            assert "screenshot_id" in events[0]

    def test_browser_history_with_screenshots(self, client):
        """浏览器历史应能关联到截图"""
        _register_agent(client, "bh-corr-agent")
        ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        _upload_screenshot(client, "bh-corr-agent", ts)
        client.post("/api/browser_history", json={
            "agent_name": "bh-corr-agent",
            "records": [{
                "url": "https://corr-test.com",
                "title": "Corr Test",
                "last_visit": ts,
                "browser": "chrome",
            }]
        })
        resp = client.get("/api/browser_history?agent=bh-corr-agent&with_screenshots=true")
        records = resp.json()
        if records:
            assert "screenshot_id" in records[0]
