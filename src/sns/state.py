from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .paths import SOURCES, STATE_PATH, ensure_dirs


def _now_iso() -> str:
    # Asia/Shanghai wall clock as offset-aware ISO
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")
    except Exception:
        return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def default_state() -> dict[str, Any]:
    return {s: {"logged_in": False, "at": None} for s in SOURCES}


def load_state() -> dict[str, Any]:
    ensure_dirs()
    if not STATE_PATH.exists():
        st = default_state()
        save_state(st)
        return st
    try:
        raw = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        raw = {}
    st = default_state()
    for s in SOURCES:
        if isinstance(raw.get(s), dict):
            st[s]["logged_in"] = bool(raw[s].get("logged_in"))
            st[s]["at"] = raw[s].get("at")
    return st


def save_state(st: dict[str, Any]) -> None:
    ensure_dirs()
    STATE_PATH.write_text(
        json.dumps(st, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def mark_logged_in(source: str) -> dict[str, Any]:
    st = load_state()
    st[source] = {"logged_in": True, "at": _now_iso()}
    save_state(st)
    return st


def mark_logged_out(source: str) -> dict[str, Any]:
    st = load_state()
    if source == "all":
        for s in SOURCES:
            st[s] = {"logged_in": False, "at": None}
    else:
        st[source] = {"logged_in": False, "at": None}
    save_state(st)
    return st


def require_login(source: str) -> dict[str, Any] | None:
    """Return an error dict if source is not marked logged-in; else None."""
    st = load_state()
    info = st.get(source) or {}
    if not info.get("logged_in"):
        return {
            "ok": False,
            "source": source,
            "error": f"not_logged_in: run `sns login {source}` and scan the QR first",
            "state": info,
        }
    return None
