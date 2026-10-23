# PyInstaller build recipe. Build with:   pyinstaller closeout.spec
#
# config.yaml is bundled inside the program as the factory-default rules. At runtime the
# program prefers an editable config.yaml placed BESIDE the executable and re-reads it on
# every run, so IT can update the rules without rebuilding; the bundled copy is only the
# fallback when no external file sits next to the program. Ship Closeout.exe together with a
# config.yaml if you want hot rule updates. Build on the operating system the users run:
# PyInstaller cannot make a Windows .exe from a Mac, or the reverse.
import sys

a = Analysis(
    ["main.py"],
    datas=[("config.yaml", ".")],
    hiddenimports=["openpyxl"],  # pandas loads its Excel writer by name at runtime
)
pyz = PYZ(a.pure)

if sys.platform == "darwin":
    # A macOS app is a folder by design; PyInstaller rejects one-file .app bundles.
    exe = EXE(pyz, a.scripts, exclude_binaries=True, name="Closeout", console=False)
    app = BUNDLE(COLLECT(exe, a.binaries, a.datas, name="Closeout"), name="Closeout.app")
else:
    # Windows: one self-contained Closeout.exe, no console window.
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, name="Closeout", console=False)
