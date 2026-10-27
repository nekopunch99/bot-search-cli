from __future__ import annotations

import os
from pathlib import Path

HOME = Path.home()
SNS_HOME = Path(os.environ.get("SNS_HOME") or (HOME / ".sns"))
STATE_PATH = SNS_HOME / "state.json"
# Runtime artifacts (QR copies, debug shots). Never write into the repo by default.
OUT_DIR = Path(os.environ.get("SNS_OUT_DIR") or (SNS_HOME / "out"))

CDP_URL = (
    os.environ.get("SNS_CDP_URL")
    or os.environ.get("SOCAI_CDP_URL")
    or "http://127.0.0.1:9224"
)

SOURCES = ("xhs", "dy", "bili")

SOURCE_DIR = {
    "xhs": SNS_HOME / "xhs",
    "dy": SNS_HOME / "dy",
    "bili": SNS_HOME / "bili",
}

QR_PATH = {
    "xhs": SNS_HOME / "xhs" / "qr.png",
    "dy": SNS_HOME / "dy" / "qr.png",
    "bili": SNS_HOME / "bili" / "qr.png",
}

QR_OUT = {
    "xhs": OUT_DIR / "xhs-qr.png",
    "dy": OUT_DIR / "dy-qr.png",
    "bili": OUT_DIR / "bili-qr.png",
}

BILI_COOKIES = SNS_HOME / "bili" / "cookies.txt"

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36"
)


def ensure_dirs() -> None:
    SNS_HOME.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for d in SOURCE_DIR.values():
        d.mkdir(parents=True, exist_ok=True)
