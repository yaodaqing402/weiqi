# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包脚本：生成 Windows(.exe 文件夹) 与 macOS(.app) 单文件应用。

    pyinstaller packaging/weiqi.spec --clean -y
"""
import re
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path.cwd()
SRC = ROOT / "src"

# 读取版本号
ver_text = (SRC / "weiqi" / "__init__.py").read_text(encoding="utf-8")
VERSION = re.search(r'__version__\s*=\s*"([^"]+)"', ver_text).group(1)
APP_NAME = f"WeiQi_v{VERSION}"

block_cipher = None

# 随包附带的 KataGo（先运行 python packaging/fetch_katago.py 准备 vendor/katago）
VENDOR = ROOT / "vendor" / "katago"
datas = []
if (VENDOR / "models").is_dir():
    datas.append((str(VENDOR / "models"), "katago/models"))
if sys.platform == "darwin" and (VENDOR / "macos").is_dir():
    datas.append((str(VENDOR / "macos"), "katago/macos"))
if sys.platform == "win32" and (VENDOR / "windows").is_dir():
    for backend in sorted(p.name for p in (VENDOR / "windows").iterdir() if p.is_dir()):
        datas.append((str(VENDOR / "windows" / backend), f"katago/windows/{backend}"))
if not datas:
    print("警告：没有找到 vendor/katago，安装包将不含 KataGo（正式对局会退回内置 AI）")

a = Analysis(
    [str(ROOT / "packaging" / "run_game.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=datas,
    hiddenimports=["numpy", "pygame"] + collect_submodules("weiqi"),
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "PIL", "scipy", "pandas"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,             # 窗口型应用，不弹控制台
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=APP_NAME,
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name=f"{APP_NAME}.app",
        icon=None,
        bundle_identifier="com.yaodaqing.weiqi",
        info_plist={
            "CFBundleName": "围棋",
            "CFBundleDisplayName": "围棋 · 少儿版",
            "CFBundleShortVersionString": VERSION,
            "NSHighResolutionCapable": True,
        },
    )
