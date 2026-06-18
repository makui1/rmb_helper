# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all

spire_datas, spire_binaries, spire_hiddenimports = collect_all('spire')

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=spire_binaries,
    datas=[
        ('app\\ui\\assets', 'app\\ui\\assets'),
        ('app\\resources', 'resources'),
    ] + spire_datas,
    hiddenimports=spire_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'PySide6.QtWebEngine',
        'PySide6.QtWebEngineWidgets',
        'PySide6.QtWebEngineCore',
        'PySide6.Qt3DCore',
        'PySide6.Qt3DRender',
        'PySide6.Qt3DInput',
        'PySide6.Qt3DAnimation',
        'PySide6.QtMultimedia',
        'PySide6.QtMultimediaWidgets',
        'PySide6.QtBluetooth',
        'PySide6.QtNfc',
        'PySide6.QtLocation',
        'PySide6.QtPositioning',
        'PySide6.QtRemoteObjects',
        'PySide6.QtScxml',
        'PySide6.QtSensors',
        'PySide6.QtSerialPort',
        'PySide6.QtCharts',
        'PySide6.QtDataVisualization',
    ],
    noarchive=False,
    optimize=0,
)
# ── 打包 Universal CRT，兼容未打补丁的 Windows 10 ───────────────────────────
# Win10 早期版本缺少 api-ms-win-crt-*.dll（需要 KB2999226），
# 离线机器无法联网安装，直接把 UCRT 随 exe 一起分发。
import glob as _glob, os as _os
def _collect_ucrt() -> list:
    # 优先从 Windows Kits 取可再发行版本（VS / WDK 安装后存在）
    kits_pattern = (
        r"C:\Program Files (x86)\Windows Kits\10\Redist\*\ucrt\DLLs\x64\*.dll"
    )
    dlls = _glob.glob(kits_pattern)
    if not dlls:
        # 回退：从 System32 收集（打包机必须是已更新的 Win10/Win11）
        dlls = _glob.glob(r"C:\Windows\System32\api-ms-win-crt-*.dll")
        ucrtbase = r"C:\Windows\System32\ucrtbase.dll"
        if _os.path.exists(ucrtbase):
            dlls.append(ucrtbase)
    return [(_os.path.basename(f), f, 'BINARY') for f in dlls]
_ucrt = _collect_ucrt()
if _ucrt:
    print(f"[UCRT] 打包 {len(_ucrt)} 个 Universal CRT DLL")
    a.binaries += _ucrt
else:
    print("[UCRT] 警告：未找到 UCRT DLL，请安装 Visual Studio 或 Windows Kits")
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='任免表工具箱',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[
        # Spire 原生库自带压缩/特殊加载逻辑，UPX 处理后可能无法加载
        'Spire.Doc.Base.dll',
        'libSkiaSharp.dll',
        # UCRT 系统 DLL 不应被 UPX 压缩
        'ucrtbase.dll',
        'api-ms-win-crt-*.dll',
    ],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['app\\ui\\assets\\icon.ico'],
)
