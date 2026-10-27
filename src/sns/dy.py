"""Douyin login helpers: cookie import (stable) + optional CDP inject for Socai."""
from __future__ import annotations

import http.cookiejar
import json
import time
import urllib.request
from pathlib import Path
from typing import Any

from .cdp import CdpClient
from .paths import CDP_URL, QR_OUT, QR_PATH, SOURCE_DIR, UA, ensure_dirs
from .state import mark_logged_in

DY_COOKIES = SOURCE_DIR["dy"] / "cookies.txt"
DY_HOSTS = ("douyin.com", "douyinpic.com")
DY_ORIGINS = ("https://www.douyin.com", "https://douyin.com")
# Auth cookies that indicate a real logged-in web session
AUTH_NAMES = ("sessionid", "sessionid_ss", "uid_tt", "sid_guard", "sid_tt")


def _emit(obj: dict[str, Any]) -> None:
    print(json.dumps(obj, ensure_ascii=False), flush=True)


def parse_cookie_header(raw: str) -> dict[str, str]:
    """Parse `a=1; b=2` or multiline `a=1` / Netscape-ish name=value lines."""
    out: dict[str, str] = {}
    text = (raw or "").strip()
    if not text:
        return out
    # If it looks like one Cookie header, split on ;
    if "\n" not in text and ";" in text:
        parts = text.split(";")
    else:
        parts = []
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # Netscape: domain flag path secure expiry name value
            cols = line.split("\t")
            if len(cols) >= 7:
                out[cols[5]] = cols[6]
                continue
            parts.append(line)
    for part in parts:
        part = part.strip()
        if not part or part.startswith("#"):
            continue
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        k, v = k.strip(), v.strip()
        if k.lower() in ("path", "domain", "expires", "max-age", "secure", "httponly", "samesite"):
            continue
        if k:
            out[k] = v
    return out


def save_cookie_header(cookie_header: str, path: Path = DY_COOKIES) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(cookie_header.strip() + "\n", encoding="utf-8")


def load_cookie_header(path: Path = DY_COOKIES) -> str | None:
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            return line
    return None


def cookies_to_header(cookies: dict[str, str]) -> str:
    return "; ".join(f"{k}={v}" for k, v in cookies.items())


def has_auth(cookies: dict[str, str]) -> bool:
    return any(n in cookies and cookies[n] for n in AUTH_NAMES)


def inject_cookies_cdp(
    cookies: dict[str, str],
    cdp_url: str | None = None,
) -> dict[str, Any]:
    """Write cookies into the Socai Chrome profile so `socai dy search` can reuse them."""
    cdp_http = cdp_url or CDP_URL
    cdp = CdpClient(cdp_http, prefer_url_substr="douyin.com")
    try:
        cdp.call("Network.enable")
        cdp.call("Page.enable")
        # Clear old dy session first
        deleted = cdp.delete_cookies_for_hosts(list(DY_HOSTS))
        for origin in DY_ORIGINS:
            cdp.clear_origin(origin)
        set_n = 0
        for name, value in cookies.items():
            if not name or value is None:
                continue
            try:
                cdp.call(
                    "Network.setCookie",
                    {
                        "name": name,
                        "value": value,
                        "url": "https://www.douyin.com/",
                        "domain": ".douyin.com",
                        "path": "/",
                        "secure": True,
                    },
                )
                set_n += 1
            except Exception:
                pass
        cdp.navigate("https://www.douyin.com/", settle=2.0)
        all_c = cdp.get_cookies(urls=["https://www.douyin.com/"])
        names = sorted({c.get("name") or "" for c in all_c})
        return {
            "deleted": deleted,
            "set": set_n,
            "cookie_names": names[:40],
            "has_auth": any(n in names for n in AUTH_NAMES),
        }
    finally:
        cdp.close()


def login_with_cookies(
    raw: str,
    cdp_url: str | None = None,
    inject: bool = True,
) -> dict[str, Any]:
    """Stable Douyin login: paste Cookie header / sessionid from a logged-in browser."""
    ensure_dirs()
    cookies = parse_cookie_header(raw)
    if not has_auth(cookies):
        raise RuntimeError(
            "missing auth cookie: need at least one of "
            + ", ".join(AUTH_NAMES)
            + " (copy from a logged-in douyin.com tab)"
        )
    header = cookies_to_header(cookies)
    save_cookie_header(header)
    out: dict[str, Any] = {
        "event": "cookies_saved",
        "source": "dy",
        "path": str(DY_COOKIES),
        "auth_names": sorted(n for n in cookies if n in AUTH_NAMES),
    }
    _emit(out)
    if inject:
        inj = inject_cookies_cdp(cookies, cdp_url=cdp_url)
        out["inject"] = inj
        _emit({"event": "cdp_inject", "source": "dy", **inj})
        if not inj.get("has_auth"):
            raise RuntimeError("cookies saved but CDP inject did not stick; is Chrome CDP up?")
    mark_logged_in("dy")
    done = {"event": "logged_in", "source": "dy", "via": "cookie_import", "cookies_saved": str(DY_COOKIES)}
    _emit(done)
    return done


def login_with_cookie_file(path: str | Path, cdp_url: str | None = None) -> dict[str, Any]:
    p = Path(path).expanduser()
    raw = p.read_text(encoding="utf-8")
    return login_with_cookies(raw, cdp_url=cdp_url)
