"""Windows 文件关联：将 .lrmx 关联到本工具（双击打开）。

写入 HKEY_CURRENT_USER\\Software\\Classes，无需管理员权限，仅影响当前用户。
.lrmx 是自定义扩展名，系统中没有既有关联，因此无需处理 UserChoice 哈希。
"""
from __future__ import annotations

import sys
from pathlib import Path

PROG_ID = 'rmb_helper.lrmx'
EXT = '.lrmx'
_DESC = '干部任免审批表'


def supported() -> bool:
    return sys.platform == 'win32'


def _launch_command() -> str:
    """返回 shell\\open\\command 的值，结尾追加 "%1" 传入被双击的文件路径。"""
    if getattr(sys, 'frozen', False):
        return f'"{Path(sys.executable)}" "%1"'
    # 开发模式：pythonw main.py "%1"
    py = Path(sys.executable)
    pyw = py.with_name('pythonw.exe')
    runner = pyw if pyw.exists() else py
    main_py = Path(__file__).resolve().parents[2] / 'main.py'
    return f'"{runner}" "{main_py}" "%1"'


def _icon_value() -> str:
    if getattr(sys, 'frozen', False):
        return f'"{Path(sys.executable)}",0'
    return str(Path(__file__).resolve().parents[1] / 'ui' / 'assets' / 'icon.ico')


def is_registered() -> bool:
    if not supported():
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, rf'Software\Classes\{EXT}') as k:
            val, _ = winreg.QueryValueEx(k, '')
            return val == PROG_ID
    except FileNotFoundError:
        return False


def register() -> None:
    import winreg
    cmd = _launch_command()
    icon = _icon_value()

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf'Software\Classes\{EXT}') as k:
        winreg.SetValueEx(k, '', 0, winreg.REG_SZ, PROG_ID)
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf'Software\Classes\{PROG_ID}') as k:
        winreg.SetValueEx(k, '', 0, winreg.REG_SZ, _DESC)
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                          rf'Software\Classes\{PROG_ID}\DefaultIcon') as k:
        winreg.SetValueEx(k, '', 0, winreg.REG_SZ, icon)
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                          rf'Software\Classes\{PROG_ID}\shell\open\command') as k:
        winreg.SetValueEx(k, '', 0, winreg.REG_SZ, cmd)
    _notify_shell()


def unregister() -> None:
    import winreg
    for sub in (
        rf'Software\Classes\{PROG_ID}\shell\open\command',
        rf'Software\Classes\{PROG_ID}\shell\open',
        rf'Software\Classes\{PROG_ID}\shell',
        rf'Software\Classes\{PROG_ID}\DefaultIcon',
        rf'Software\Classes\{PROG_ID}',
    ):
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, sub)
        except FileNotFoundError:
            pass
    # 仅当 .lrmx 默认值仍指向本工具时才清除
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, rf'Software\Classes\{EXT}',
                            0, winreg.KEY_ALL_ACCESS) as k:
            val, _ = winreg.QueryValueEx(k, '')
            if val == PROG_ID:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, rf'Software\Classes\{EXT}')
    except FileNotFoundError:
        pass
    _notify_shell()


def _notify_shell() -> None:
    """通知资源管理器关联已变更，立即刷新图标/默认程序。"""
    try:
        import ctypes
        SHCNE_ASSOCCHANGED = 0x08000000
        SHCNF_IDLIST = 0x0000
        ctypes.windll.shell32.SHChangeNotify(SHCNE_ASSOCCHANGED, SHCNF_IDLIST, None, None)
    except Exception:
        pass
