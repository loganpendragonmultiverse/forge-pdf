"""Build a portable directory and retain dependency notices alongside it."""

import importlib.metadata as metadata
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    if sys.platform != "win32":
        raise SystemExit("Build this Windows preview on Windows.")
    subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--windowed",
            "--name",
            "Forge PDF",
            "--collect-all",
            "pypdfium2",
            "--collect-all",
            "pypdfium2_raw",
            "--collect-all",
            "reportlab",
            str(ROOT / "tools" / "desktop_entry.py"),
        ],
        cwd=ROOT,
        check=True,
    )
    destination = ROOT / "dist" / "Forge PDF"
    support = destination / "Support"
    support.mkdir(exist_ok=True)
    for name in ["README.md", "LICENSE", "THIRD_PARTY_NOTICES.md", "SECURITY.md", "TESTING.md"]:
        shutil.copy2(ROOT / name, support / name)
    shutil.copytree(ROOT / "examples", support / "examples", dirs_exist_ok=True)
    licenses = support / "licenses"
    licenses.mkdir(exist_ok=True)
    for package in [
        "pypdf",
        "pypdfium2",
        "Pillow",
        "reportlab",
        "charset-normalizer",
        "pyinstaller",
        "cryptography",
        "cffi",
        "pycparser",
    ]:
        dist = metadata.distribution(package)
        for file in dist.files or []:
            if any(
                word in str(file).lower() for word in ["license", "copyright", "notice", "copying"]
            ):
                source = Path(dist.locate_file(file))
                if source.is_file():
                    target = licenses / package / str(file).replace("../", "").replace("..\\", "")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
    shutil.copy2(Path(sys.base_prefix) / "LICENSE.txt", licenses / "Python-LICENSE.txt")
    tclroot = Path(sys.base_prefix) / "tcl"
    for source in tclroot.rglob("*"):
        if source.is_file() and source.name.lower() in ("license.terms", "license", "license.txt"):
            target = licenses / "tcl-tk" / source.relative_to(tclroot)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    archive = shutil.make_archive(
        str(ROOT / "dist" / "Forge-PDF-1.0.0-Windows"), "zip", ROOT / "dist", "Forge PDF"
    )
    print(archive)


if __name__ == "__main__":
    main()
