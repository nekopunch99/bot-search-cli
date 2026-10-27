"""Bilibili QR login + read-only search."""
from __future__ import annotations

import http.cookiejar
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from .paths import BILI_COOKIES, QR_OUT, QR_PATH, UA, ensure_dirs
from .qrutil import write_qr_png
from .state import mark_logged_in

EM_RE = re.compile(r"<[^>]+>")
REFERER = "https://www.bilibili.com"


def _emit(obj: dict[str, Any]) -> None:
    print(json.dumps(obj, ensure_ascii=False), flush=True)


def generate_qr() -> dict[str, str]:
    url = "https://passport.bilibili.com/x/passport-login/web/qrcode/generate"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": UA, "Referer": "https://www.bilibili.com/"},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode())
    if data.get("code") != 0:
        raise RuntimeError(f"bili qr generate failed: {data}")
    d = data["data"]
    return {"url": d["url"], "qrcode_key": d["qrcode_key"]}


def poll_once(qrcode_key: str) -> tuple[dict[str, Any], list[str]]:
    """Return (body_json, set_cookie_header_values)."""
    url = (
        "https://passport.bilibili.com/x/passport-login/web/qrcode/poll?"
        + urllib.parse.urlencode({"qrcode_key": qrcode_key})
    )
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Referer": "https://passport.bilibili.com/login",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        set_cookies = resp.headers.get_all("Set-Cookie") or []
        # also gather via items for robustness
        if not set_cookies:
            set_cookies = [v for k, v in resp.headers.items() if k.lower() == "set-cookie"]
        body = json.loads(resp.read().decode())
    return body, set_cookies


def _cookies_from_set_cookie(set_cookies: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in set_cookies:
        part = raw.split(";", 1)[0]
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def _fetch_cross_domain(url: str, jar: http.cookiejar.CookieJar) -> None:
    if not url:
        return
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    req = urllib.request.Request(
        url,
        headers={"User-Agent": UA, "Referer": "https://passport.bilibili.com/"},
    )
    try:
        with opener.open(req, timeout=20) as resp:
            resp.read(64)
    except Exception:
        pass


def save_cookie_header(cookie_header: str, path: Path = BILI_COOKIES) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Store as simple Cookie header string (one line), plus a Netscape dump comment
    path.write_text(cookie_header.strip() + "\n", encoding="utf-8")


def load_cookie_header(path: Path = BILI_COOKIES) -> str | None:
    if not path.exists():
        return None
    line = path.read_text(encoding="utf-8").strip().splitlines()
    if not line:
        return None
    # skip comments
    for L in line:
        L = L.strip()
        if L and not L.startswith("#"):
            return L
    return None


def jar_to_header(jar: http.cookiejar.CookieJar) -> str:
    pairs = []
    for c in jar:
        pairs.append(f"{c.name}={c.value}")
    return "; ".join(pairs)


def login(timeout: float = 180.0, poll_interval: float = 2.0) -> dict[str, Any]:
    ensure_dirs()
    gen = generate_qr()
    qr_path = write_qr_png(gen["url"], QR_PATH["bili"], also=QR_OUT["bili"])
    _emit(
        {
            "event": "qr_ready",
            "source": "bili",
            "path": str(qr_path),
            "out": str(QR_OUT["bili"]),
            "qrcode_key": gen["qrcode_key"],
        }
    )
    t0 = time.time()
    jar = http.cookiejar.CookieJar()
    last_code = None
    while time.time() - t0 < timeout:
        body, set_cookies = poll_once(gen["qrcode_key"])
        if body.get("code") != 0:
            raise RuntimeError(f"bili poll error: {body}")
        data = body.get("data") or {}
        code = data.get("code")
        last_code = code
        if code == 0:
            # success
            cookies = _cookies_from_set_cookie(set_cookies)
            for k, v in cookies.items():
                # seed jar via SimpleCookie-like manual
                c = http.cookiejar.Cookie(
                    version=0,
                    name=k,
                    value=v,
                    port=None,
                    port_specified=False,
                    domain=".bilibili.com",
                    domain_specified=True,
                    domain_initial_dot=True,
                    path="/",
                    path_specified=True,
                    secure=False,
                    expires=None,
                    discard=True,
                    comment=None,
                    comment_url=None,
                    rest={},
                    rfc2109=False,
                )
                jar.set_cookie(c)
            _fetch_cross_domain(data.get("url") or "", jar)
            header = jar_to_header(jar)
            if not header and cookies:
                header = "; ".join(f"{k}={v}" for k, v in cookies.items())
            if not header:
                # still mark login but warn
                save_cookie_header("")
                mark_logged_in("bili")
                out = {
                    "event": "logged_in",
                    "source": "bili",
                    "warning": "no cookies captured; search may fail",
                    "poll": data,
                }
                _emit(out)
                return out
            save_cookie_header(header)
            mark_logged_in("bili")
            out = {"event": "logged_in", "source": "bili", "cookies_saved": str(BILI_COOKIES)}
            _emit(out)
            return out
        if code == 86101:
            status = "waiting_scan"
        elif code == 86090:
            status = "scanned_confirm"
        elif code == 86038:
            raise RuntimeError("bili QR expired; run login again")
        else:
            status = f"code_{code}"
        _emit(
            {
                "event": "poll",
                "source": "bili",
                "status": status,
                "code": code,
                "message": data.get("message"),
                "elapsed_s": int(time.time() - t0),
            }
        )
        time.sleep(poll_interval)
    raise TimeoutError(
        f"bili login timed out after {timeout}s (last_code={last_code}). "
        f"QR at {qr_path}"
    )


def http_get_json(url: str, cookie: str | None = None) -> dict[str, Any]:
    headers = {
        "User-Agent": UA,
        "Referer": REFERER,
        "Origin": "https://www.bilibili.com",
        "Accept": "application/json",
    }
    if cookie:
        headers["Cookie"] = cookie
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    if not raw.lstrip().startswith("{"):
        raise RuntimeError(f"Non-JSON response (likely WAF): {raw[:120]!r}")
    data = json.loads(raw)
    if data.get("code") not in (0, None):
        raise RuntimeError(
            f"Bilibili API error code={data.get('code')} message={data.get('message')}"
        )
    return data


def clean_title(s: str) -> str:
    return EM_RE.sub("", s or "").replace("&amp;", "&").strip()


def abs_pic(pic: str) -> str:
    if not pic:
        return ""
    if pic.startswith("//"):
        return "https:" + pic
    if pic.startswith("http://"):
        return "https://" + pic[len("http://") :]
    return pic


def search(query: str, num: int = 10, page: int = 1) -> dict[str, Any]:
    cookie = load_cookie_header()
    if cookie is None:
        return {
            "ok": False,
            "source": "bili",
            "error": "cookies_missing: run `sns login bili` again",
        }
    params = {
        "search_type": "video",
        "keyword": query,
        "page": str(page),
        "page_size": str(min(max(num, 1), 50)),
    }
    url = (
        "https://api.bilibili.com/x/web-interface/wbi/search/type?"
        + urllib.parse.urlencode(params)
    )
    try:
        data = http_get_json(url, cookie=cookie)
    except Exception:
        url = (
            "https://api.bilibili.com/x/web-interface/search/type?"
            + urllib.parse.urlencode(params)
        )
        data = http_get_json(url, cookie=cookie)

    payload = data.get("data") or {}
    results = payload.get("result") or payload.get("items") or []
    cards = []
    for i, item in enumerate(results[:num]):
        bvid = item.get("bvid") or ""
        arcurl = item.get("arcurl") or ""
        if not bvid and "cheese" in arcurl:
            url_out = arcurl.replace("http://", "https://")
        elif bvid:
            url_out = f"https://www.bilibili.com/video/{bvid}"
        else:
            url_out = arcurl.replace("http://", "https://")
        cards.append(
            {
                "source": "bili",
                "position": i,
                "title": clean_title(item.get("title") or ""),
                "author": item.get("author") or item.get("uname") or "",
                "author_id": str(item.get("mid") or item.get("uid") or ""),
                "id": bvid or str(item.get("aid") or item.get("id") or ""),
                "bvid": bvid,
                "aid": item.get("aid") or item.get("id") or "",
                "url": url_out,
                "plays": item.get("play")
                if item.get("play") is not None
                else item.get("view"),
                "likes": item.get("like"),
                "danmaku": item.get("video_review")
                if item.get("video_review") is not None
                else item.get("danmaku"),
                "duration": item.get("duration") or "",
                "cover_url": abs_pic(item.get("pic") or ""),
            }
        )
    return {
        "ok": True,
        "source": "bili",
        "query": query,
        "count": len(cards),
        "cards": cards,
        "url": f"https://search.bilibili.com/video?keyword={urllib.parse.quote(query)}",
        "via": "http+cookies",
    }
