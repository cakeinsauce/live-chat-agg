# -*- mode: python ; coding: utf-8 -*-
import sys

from PyInstaller.utils.hooks import collect_all, collect_submodules

IS_DARWIN = sys.platform == "darwin"

datas = [("static", "static")]
binaries = []
hiddenimports = [
    "app",
    "app.config",
    "app.server",
    "app.launcher",
    "app.desktop",
    "app.tts_neural",
    "edge_tts",
    "edge_tts.communicate",
    "certifi",
    "charset_normalizer",
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
]

_COLLECT_ALL_PKGS = [
    "TikTokLive",
    "uvicorn",
    "websockets",
    "pydantic",
    "pydantic_core",
    "pydantic_settings",
    "fastapi",
    "starlette",
    "mashumaro",
    "betterproto",
    "aiohttp",
    "h11",
    "httptools",
    "wsproto",
    "anyio",
    "click",
    "PySide6",
    "edge_tts",
]

for pkg in _COLLECT_ALL_PKGS:
    try:
        pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
        datas += pkg_datas
        binaries += pkg_binaries
        hiddenimports += pkg_hidden
    except Exception as exc:
        print(f"WARN: collect_all({pkg!r}) failed: {exc}")

hiddenimports += collect_submodules("google.protobuf")

a = Analysis(
    ["run_packaged.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "numpy",
        "PIL",
        "pytest",
        "IPython",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data)

if IS_DARWIN:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="live-chat-agg",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=True,
        disable_windowed_traceback=False,
        argv_emulation=False,
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
        name="live-chat-agg",
    )
    app = BUNDLE(
        coll,
        name="live-chat-agg.app",
        icon=None,
        bundle_identifier="com.cakeinsauce.livechataggregator",
        info_plist={
            "CFBundleName": "Live Chat Aggregator",
            "CFBundleDisplayName": "Live Chat Aggregator",
            "CFBundleShortVersionString": "3.1.0",
            "CFBundleVersion": "3.1.0",
            "NSHighResolutionCapable": True,
            "LSBackgroundOnly": False,
        },
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.zipfiles,
        a.datas,
        [],
        name="live-chat-agg",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=True,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
    )
