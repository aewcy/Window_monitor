"""
Windows Service 入口已禁用。

Agent 需要采集登录用户的桌面、活动窗口和键盘事件。普通 Windows 服务运行在
Session 0，不能稳定访问交互式桌面。请使用 install-agent.ps1，它会安装登录
计划任务和 watchdog，并在用户会话中运行 Agent。
"""
import sys


MESSAGE = (
    "Monitor Agent 不支持普通 Windows Service 模式。"
    "请使用 install-agent.ps1 安装登录计划任务。"
)


def run_service():
    raise RuntimeError(MESSAGE)


if __name__ == "__main__":
    print(MESSAGE, file=sys.stderr)
    sys.exit(1)
