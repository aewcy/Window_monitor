# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for Monitor Agent — 单文件 .exe 打包
被控机无需安装 Python 或任何依赖，直接运行 monitor-agent.exe

用法:
    pyinstaller --clean --noconfirm agent/agent.spec
    # 或双击 build.bat
"""

import sys
import os
from pathlib import Path

# SPECPATH 是 PyInstaller 提供的 spec 文件所在目录
_SPEC_DIR = Path(SPECPATH)
_AGENT_DIR = _SPEC_DIR.resolve()

# ---- 隐藏导入 — 所有 C 扩展/动态加载的模块 ----
_HIDDEN_IMPORTS = [
    # pynput 键盘钩子
    'pynput', 'pynput.keyboard', 'pynput.keyboard._win32',
    # pywin32 Windows API
    'win32gui', 'win32process', 'win32api', 'win32con', 'win32ui',
    'win32event', 'win32service', 'win32serviceutil', 'servicemanager',
    'pythoncom', 'pywintypes',
    # Windows 服务入口
    'service',
    # mss 屏幕截图
    'mss', 'mss.windows',
    # Pillow JPEG codec + 屏幕截图
    'PIL', 'PIL.Image', 'PIL.ImageGrab', 'PIL._imaging',
    # psutil
    'psutil', 'psutil._pswindows',
    # requests 依赖
    'urllib3', 'charset_normalizer', 'certifi',
]

# ---- 排除不需要的模块以减小体积 ----
_EXCLUDES = [
    'tkinter', 'matplotlib', 'numpy', 'scipy', 'pandas',
    'jedi', 'IPython', 'PyQt5', 'PySide2', 'wx',
    'notebook', 'tornado', 'sqlalchemy', 'alembic',
    'pytest', 'setuptools', 'pip', 'wheel',
    'lib2to3', 'multiprocessing',
]

# ======== Phase 1: 分析 ========
a = Analysis(
    [str(_AGENT_DIR / 'main.py')],
    pathex=[str(_AGENT_DIR)],
    binaries=[],
    datas=[],
    hiddenimports=_HIDDEN_IMPORTS,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=_EXCLUDES,
    noarchive=False,
    optimize=0,
)

# ======== Phase 2: 打包 Python 字节码 ========
pyz = PYZ(a.pure)

# ======== Phase 3: 生成单文件 .exe ========
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='monitor-agent',               # 输出文件名
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,                            # UPX 压缩减小体积
    upx_exclude=[],
    runtime_tmpdir=None,                 # 临时解压目录 (None=系统默认)
    console=True,                        # 控制台窗口 — 保留 print/input
    hide_console=False,
    disable_windowed_traceback=True,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
