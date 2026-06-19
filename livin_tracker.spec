# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec untuk Livin Tracker
# Build: python build.py
#
# Output: dist/LivinTracker.exe (Windows) atau dist/LivinTracker (Mac/Linux)

import sys
from pathlib import Path

BASE = Path(SPECPATH)

block_cipher = None

a = Analysis(
    [str(BASE / 'main.py')],
    pathex=[str(BASE)],
    binaries=[],
    datas=[
        # Bundle templates HTML
        (str(BASE / 'templates'), 'templates'),
        # Bundle static files jika ada
        # (str(BASE / 'static'), 'static'),
    ],
    hiddenimports=[
        # Flask & ecosystem
        'flask',
        'flask.json',
        'werkzeug',
        'werkzeug.serving',
        'jinja2',
        'jinja2.ext',
        'click',
        # Google Auth
        'google.auth',
        'google.auth.transport.requests',
        'google.oauth2.credentials',
        'google_auth_oauthlib',
        'google_auth_oauthlib.flow',
        'googleapiclient',
        'googleapiclient.discovery',
        'googleapiclient.errors',
        # OpenAI
        'openai',
        'httpx',
        # PDF
        'pdfplumber',
        'pikepdf',
        # Standard
        'sqlite3',
        'pickle',
        'json',
        'threading',
        'webbrowser',
        # App modules
        'src.banks',
        'src.config',
        'src.database',
        'src.gmail_fetcher',
        'src.llm_extractor',
        'src.dashboard',
        'src.pdf_extractor',
        'src.parser',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'numpy',
        'pandas',
        'scipy',
        'PIL',
        'cv2',
        'torch',
        'tensorflow',
        'pytest',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='LivinTracker',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,        # True = tampilkan terminal (berguna untuk melihat log sync)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon='assets/icon.ico',  # uncomment jika ada file icon
)
