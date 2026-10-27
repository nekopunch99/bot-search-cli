"""Wrap Socai for Xiaohongshu / Douyin search (read-only preview cards)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Any

from .paths import CDP_URL


def _socai_bin() -> str:
    env = os.environ.get("SOCAI_BIN")
    if env:
        return env
    found = shutil.which("socai")
    if found:
        return found
    home = os.path.expanduser("~/.cargo/bin/socai")
    if os.path.isfile(home):
        return home
    raise RuntimeError("socai not found on PATH or ~/.cargo/bin")


def _env() -> dict[str, str]:
    env = os.environ.copy()
    env["SOCAI_CDP_URL"] = os.environ.get("SOCAI_CDP_URL") or CDP_URL
    cargo_env = os.path.expanduser("~/.cargo/env")
    # ensure cargo bin on PATH
    cargo_bin = os.path.expanduser("~/.cargo/bin")
    path = env.get("PATH", "")
    if cargo_bin not in path:
        env["PATH"] = cargo_bin + os.pathsep + path
    if os.path.isfile(cargo_env):
        # light touch: PATH already fixed
        pass
    return env


_task_begun = False


def ensure_task(label: str = "sns search") -> None:
    global _task_begun
    if _task_begun:
        return
    bin_ = _socai_bin()
    try:
        subprocess.run(
            [bin_, "task", "begin", label],
            env=_env(),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except Exception:
        pass
    _task_begun = True


def _run(args: list[str], timeout: float = 180) -> dict[str, Any]:
    ensure_task()
    bin_ = _socai_bin()
    proc = subprocess.run(
        [bin_, *args],
        env=_env(),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    out = (proc.stdout or "").strip()
    # socai often prints a run_dir line then JSON
    json_text = None
    if out.startswith("{"):
        json_text = out
    else:
        # find last JSON object
        idx = out.rfind("\n{")
        if idx >= 0:
            json_text = out[idx + 1 :]
        else:
            idx = out.find("{")
            if idx >= 0:
                json_text = out[idx:]
    if not json_text:
        raise RuntimeError(
            f"socai returned no JSON (exit={proc.returncode}): "
            f"stdout={out[:300]!r} stderr={(proc.stderr or '')[:300]!r}"
        )
    try:
        data = json.loads(json_text)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"socai JSON parse failed: {e}; text={json_text[:300]!r}") from e
    if proc.returncode != 0 and not isinstance(data, dict):
        raise RuntimeError(f"socai exit {proc.returncode}: {proc.stderr[:300]}")
    return data if isinstance(data, dict) else {"raw": data}


def normalize_xhs(data: dict[str, Any], query: str) -> dict[str, Any]:
    cards_in = data.get("cards") or data.get("notes") or []
    cards = []
    for i, c in enumerate(cards_in):
        cards.append(
            {
                "source": "xhs",
                "position": i,
                "title": c.get("title") or "",
                "author": c.get("author") or "",
                "author_id": c.get("author_id") or "",
                "id": c.get("note_id") or c.get("id") or "",
                "note_id": c.get("note_id") or "",
                "url": c.get("url") or "",
                "likes": c.get("likes"),
                "plays": c.get("plays") or c.get("liked_count"),
                "type": c.get("type") or "",
                "cover_url": c.get("cover_url") or c.get("cover") or "",
            }
        )
    return {
        "ok": True,
        "source": "xhs",
        "query": query,
        "count": len(cards),
        "cards": cards,
        "url": data.get("url") or "",
        "via": "socai",
    }


def normalize_dy(data: dict[str, Any], query: str) -> dict[str, Any]:
    cards_in = data.get("cards") or data.get("videos") or []
    cards = []
    for i, c in enumerate(cards_in):
        cards.append(
            {
                "source": "dy",
                "position": i,
                "title": c.get("title") or c.get("desc") or "",
                "author": c.get("author") or "",
                "author_id": c.get("author_id") or "",
                "id": c.get("aweme_id") or c.get("video_id") or c.get("id") or "",
                "url": c.get("url") or "",
                "likes": c.get("likes") or c.get("digg_count"),
                "plays": c.get("plays") or c.get("play_count"),
                "comments": c.get("comments"),
                "duration": c.get("duration") or c.get("duration_seconds"),
                "cover_url": c.get("cover_url") or "",
            }
        )
    return {
        "ok": True,
        "source": "dy",
        "query": query,
        "count": len(cards),
        "cards": cards,
        "url": data.get("url") or "",
        "via": "socai",
    }


def search_xhs(query: str, num: int = 5) -> dict[str, Any]:
    data = _run(
        [
            "xhs",
            "search",
            query,
            "--num-notes",
            str(num),
            "--preview",
            "--pretty",
        ],
        timeout=240,
    )
    return normalize_xhs(data, query)


def search_dy(query: str, num: int = 5) -> dict[str, Any]:
    data = _run(
        ["dy", "search", query, "--num", str(num), "--pretty"],
        timeout=240,
    )
    return normalize_dy(data, query)
