from __future__ import annotations

import shutil
from pathlib import Path


def write_qr_png(data: str, dest: Path, also: Path | None = None) -> Path:
    import qrcode

    dest.parent.mkdir(parents=True, exist_ok=True)
    img = qrcode.make(data)
    img.save(str(dest))
    if also is not None:
        also.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(dest, also)
    return dest


def write_bytes_png(png: bytes, dest: Path, also: Path | None = None) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(png)
    if also is not None:
        also.parent.mkdir(parents=True, exist_ok=True)
        also.write_bytes(png)
    return dest
