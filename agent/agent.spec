# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for Monitor Agent.

Usage:
    pyinstaller --clean --noconfirm agent/agent.spec
    or run agent/build.bat
"""

from pathlib import Path

_SPEC_DIR = Path(SPECPATH)
_AGENT_DIR = _SPEC_DIR.resolve()

_HIDDEN_IMPORTS = [
    "pynput", "pynput.keyboard", "pynput.keyboard._win32",
    "win32gui", "win32process", "win32api", "win32con", "win32ui",
    "pythoncom", "pywintypes",
    "mss", "mss.windows",
    "PIL", "PIL.Image", "PIL.ImageGrab", "PIL._imaging",
    "psutil", "psutil._pswindows",
    "urllib3", "charset_normalizer", "certifi",
]

_EXCLUDES = [
    "tkinter", "matplotlib", "numpy", "scipy", "pandas",
    "jedi", "IPython", "PyQt5", "PySide2", "wx",
    "notebook", "tornado", "sqlalchemy", "alembic",
    "pytest", "setuptools", "pip", "wheel",
    "lib2to3", "multiprocessing",
]

a = Analysis(
    [str(_AGENT_DIR / "main.py")],
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

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="monitor-agent",
    icon=str(_AGENT_DIR / "assets" / "windows-monitor.ico"),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    hide_console=False,
    disable_windowed_traceback=True,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
