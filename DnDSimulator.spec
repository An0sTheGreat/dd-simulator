# PyInstaller build definition for the Windows application.

from pathlib import Path


project_root = Path(SPECPATH)
theme_root = project_root / "src" / "dd_simulator" / "ui" / "themes"
font_root = project_root / "src" / "dd_simulator" / "ui" / "assets" / "fonts"
icon_root = project_root / "src" / "dd_simulator" / "ui" / "assets" / "icons"
inventory_art_root = project_root / "src" / "dd_simulator" / "ui" / "assets" / "inventory"
location_art_root = project_root / "src" / "dd_simulator" / "ui" / "assets" / "location"
preset_root = project_root / "src" / "dd_simulator" / "state" / "presets"
llama_root = project_root / "vendor" / "llama_cpp"
license_root = project_root / "licenses"

a = Analysis(
    [str(project_root / "launcher.py")],
    pathex=[str(project_root / "src")],
    binaries=[],
    datas=[
        (str(theme_root / "high_fantasy"), "dd_simulator/ui/themes/high_fantasy"),
        (str(theme_root / "modern_proof"), "dd_simulator/ui/themes/modern_proof"),
        (str(font_root), "dd_simulator/ui/assets/fonts"),
        (str(icon_root), "dd_simulator/ui/assets/icons"),
        (str(inventory_art_root), "dd_simulator/ui/assets/inventory"),
        (str(location_art_root), "dd_simulator/ui/assets/location"),
        (str(preset_root), "dd_simulator/state/presets"),
        (str(llama_root), "llama_cpp"),
        (str(license_root), "licenses"),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="DnDSimulator",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="DnDSimulator",
)
