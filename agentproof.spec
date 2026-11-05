# PyInstaller spec: builds a single-file AgentProof.exe (backend + built frontend + sample data).
# Build with build_exe.bat (Windows). Data (.env, data/agentproof.db) is stored next to the exe.
# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

def _no_tests(name: str) -> bool:
    return ".tests" not in name and not name.endswith(".conftest")


# scipy/scikit-learn import parts of their vendored array-API layer dynamically, so collect them fully.
hiddenimports = (
    collect_submodules("backend")
    + collect_submodules("uvicorn")
    + collect_submodules("sklearn", filter=_no_tests)
    + collect_submodules("scipy._external", filter=_no_tests)
    + collect_submodules("scipy._lib", filter=_no_tests)
    + collect_submodules("scipy.sparse", filter=_no_tests)
    + collect_submodules("scipy.special", filter=_no_tests)
    + collect_submodules("numpy.fft")
    + ["multipart", "python_multipart"]
)

datas = [
    ("frontend/dist", "frontend/dist"),
    ("sample_data/northwind_kb.md", "sample_data"),
    ("sample_data/northwind_transcripts.json", "sample_data"),
    ("sample_data/northwind_transcripts.csv", "sample_data"),
    ("backend/templates", "backend/templates"),
    (".env.example", "."),
] + collect_data_files("reportlab")

a = Analysis(
    ["run.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "pytest", "IPython", "pandas"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="AgentProof",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=True,  # keeps a window with the server log; close it (or Ctrl+C) to stop AgentProof
    disable_windowed_traceback=False,
)
