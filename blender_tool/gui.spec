# -*- mode: python ; coding: utf-8 -*-
#
# Configurazione PyInstaller per creare l'eseguibile Windows dell'app.
#
# Build:
#     pyinstaller gui.spec
#
# L'eseguibile risultante si trova in dist/OBJRenderer/OBJRenderer.exe
#
# Nota importante: NON impacchettiamo Blender. blender_render.py viene
# incluso come "dato" perche' deve rimanere un file .py leggibile che
# Blender esegue tramite --python. Viene estratto a runtime in sys._MEIPASS
# e la GUI lo ritrova con resource_path().

block_cipher = None


a = Analysis(
    ['gui.py'],
    pathex=[],
    binaries=[],
    # (sorgente, cartella_destinazione_dentro_il_bundle)
    datas=[('blender_render.py', '.')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name='OBJRenderer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # applicazione GUI: nessuna finestra console
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon='app.ico',       # opzionale: aggiungi un'icona .ico
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='OBJRenderer',
)
