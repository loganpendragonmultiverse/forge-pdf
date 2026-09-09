"""Hash exactly the versioned public release artifacts."""

import hashlib
from pathlib import Path

from forge_pdf import __version__

root = Path(__file__).resolve().parents[1] / "dist"
names = [
    f"Forge-PDF-{__version__}-Windows.zip",
    f"forge_pdf-{__version__}-py3-none-any.whl",
    f"forge_pdf-{__version__}.tar.gz",
]
lines = [f"{hashlib.sha256((root / name).read_bytes()).hexdigest()}  {name}" for name in names]
(root / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
