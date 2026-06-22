"""
Monitor Agent — Windows 服务版
注册: python service.py install
启动: python service.py start
停止: python service.py stop
卸载: python service.py remove
"""
import sys
import os
import servicemanager
import win32event
import win32service
import win32serviceutil

# 将 agent 目录加入路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class MonitorAgentService(win32serviceutil.ServiceFramework):
    _svc_name_ = "MonitorAgent"
    _svc_display_name_ = "Monitor Agent"
    _svc_description_ = "员工监控 Agent — 截图采集、活动记录、浏览器历史"
    _svc_start_type_ = win32service.SERVICE_AUTO_START  # 开机自启

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)
        self.is_alive = True

    def SvcStop(self):
        """停止服务"""
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.stop_event)
        self.is_alive = False

    def SvcDoRun(self):
        """启动服务"""
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, ""),
        )
        self.main()

    def main(self):
        """Agent 主逻辑 — 传入 stop_event 用于接收停止信号"""
        from main import main as agent_main
        try:
            agent_main(stop_event=self.stop_event)
        except Exception as e:
            servicemanager.LogErrorMsg(f"Monitor Agent 异常: {e}")


def run_service():
    """从 PyInstaller 打包后的主程序进入 Windows 服务控制器。"""
    servicemanager.Initialize()
    servicemanager.PrepareToHostSingle(MonitorAgentService)
    servicemanager.StartServiceCtrlDispatcher()


if __name__ == "__main__":
    if len(sys.argv) == 1:
        # 从服务控制管理器启动
        run_service()
    else:
        # 命令行操作: install / start / stop / remove
        win32serviceutil.HandleCommandLine(MonitorAgentService)
