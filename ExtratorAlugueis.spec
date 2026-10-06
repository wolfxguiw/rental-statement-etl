# PyInstaller one-folder release for Windows.
from pathlib import Path

project_root = Path(SPECPATH)
ocr_runtime = project_root / "vendor" / "tesseract"
if not (ocr_runtime / "tesseract.exe").is_file():
    raise FileNotFoundError(f"OCR local não encontrado: {ocr_runtime}")

a = Analysis(
    ["run_desktop.py"],
    pathex=[SPECPATH],
    binaries=[],
    datas=[(str(ocr_runtime), "ocr")],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tests", "reportlab", "pytest"],
    noarchive=False,
    optimize=1,
)
# Package metadata SBOMs and Tcl's test extension are not used by the app.
a.datas = [
    entry
    for entry in a.datas
    if not (
        entry[0].casefold().startswith("cryptography-")
        and "\\sboms\\" in entry[0].casefold()
    )
    and not entry[0].casefold().endswith("tcltest-2.5.8.tm")
]
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ExtratorAlugueis",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=True,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="ExtratorAlugueis",
)
