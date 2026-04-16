import os
import subprocess
import shutil
from pathlib import Path

# Path to your local TeX tree (macOS BasicTeX)
LOCAL_TEXMF = Path.home() / "Library/texmf/tex/latex/local"

def install_packages_from_dir(pkg_dir):
    pkg_dir = Path(pkg_dir).resolve()
    if not pkg_dir.exists():
        print(f"❌ Directory {pkg_dir} does not exist.")
        return

    # Ensure local texmf dir exists
    LOCAL_TEXMF.mkdir(parents=True, exist_ok=True)

    # Process .ins files
    for ins_file in pkg_dir.glob("*.ins"):
        print(f"📦 Processing {ins_file.name}...")
        try:
            subprocess.run(["latex", str(ins_file)], cwd=pkg_dir, check=True)
        except subprocess.CalledProcessError:
            print(f"⚠️ Failed to process {ins_file}")
            continue

    # Move .sty files into texmf
    for sty_file in pkg_dir.glob("*.sty"):
        target = LOCAL_TEXMF / sty_file.name
        print(f"➡️ Installing {sty_file.name} → {target}")
        shutil.copy(sty_file, target)

    # Update LaTeX file database
    try:
        subprocess.run(["mktexlsr", str(LOCAL_TEXMF)], check=True)
        print("✅ TeX database updated.")
    except subprocess.CalledProcessError:
        print("⚠️ Failed to run mktexlsr. You may need to run it manually.")

if __name__ == "__main__":
    # Example: put all your CTAN downloads in ~/Downloads/fullpage
    pkg_dir = input("Enter the path to your CTAN package folder: ").strip()
    install_packages_from_dir(pkg_dir)
