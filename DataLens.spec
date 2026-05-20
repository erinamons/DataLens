# -*- mode: python ; coding: utf-8 -*-
"""DataLens PyInstaller spec"""

import sys
from pathlib import Path

a = Analysis(
    [str(Path('main.py').resolve())],
    pathex=[str(Path('.').resolve())],
    binaries=[],
    datas=[
        (str(Path('web/index.html').resolve()), 'web'),
    ],
    hiddenimports=[
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        'fastapi',
        'pydantic',
        'anyio',
        'anyio._backends',
        'anyio._backends._asyncio',
        'starlette',
        'starlette.responses',
        'starlette.routing',
        'starlette.middleware',
        'starlette.middleware.cors',
        'multipart',
        'email_validator',
        'sniffio',
        'certifi',
        'h11',
        'httptools',
        'idna',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib', 'numpy', 'scipy', 'pandas',
        'PIL', 'pillow',
        'torch', 'tensorflow',
        'jupyter', 'IPython', 'pytest',
        'tkinter',
        'xml.etree',
        'pydoc',
        'lib2to3',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='DataLens',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,  # console + ctypes 隐藏（Python 3.14 不支持 windowed）
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
