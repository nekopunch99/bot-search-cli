"""Minimal Chrome DevTools Protocol client (HTTP + raw WebSocket)."""
from __future__ import annotations

import base64
import json
import os
import socket
import struct
import time
import urllib.request
from typing import Any
from urllib.parse import urlparse


class CdpClient:
    def __init__(self, cdp_http: str, prefer_url_substr: str | None = None):
        pages = json.load(
            urllib.request.urlopen(cdp_http.rstrip("/") + "/json", timeout=5)
        )
        page = None
        if prefer_url_substr:
            page = next(
                (
                    p
                    for p in pages
                    if p.get("type") == "page"
                    and prefer_url_substr in (p.get("url") or "")
                    and p.get("webSocketDebuggerUrl")
                ),
                None,
            )
        if not page:
            page = next(
                (
                    p
                    for p in pages
                    if p.get("type") == "page" and p.get("webSocketDebuggerUrl")
                ),
                None,
            )
        if not page:
            ver = json.load(
                urllib.request.urlopen(cdp_http.rstrip("/") + "/json/version", timeout=5)
            )
            ws_url = ver["webSocketDebuggerUrl"]
        else:
            ws_url = page["webSocketDebuggerUrl"]
        u = urlparse(ws_url)
        key = base64.b64encode(os.urandom(16)).decode()
        req = (
            f"GET {u.path} HTTP/1.1\r\nHost: {u.hostname}:{u.port}\r\n"
            f"Upgrade: websocket\r\nConnection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
        ).encode()
        self.s = socket.create_connection((u.hostname, u.port), timeout=15)
        self.s.sendall(req)
        buf = b""
        while b"\r\n\r\n" not in buf:
            buf += self.s.recv(4096)
        if b"101" not in buf.split(b"\r\n", 1)[0]:
            raise RuntimeError("CDP websocket upgrade failed")
        self._id = 0
        self.cdp_http = cdp_http.rstrip("/")

    def _send(self, obj: dict[str, Any]) -> None:
        data = json.dumps(obj).encode()
        mask = os.urandom(4)
        plen = len(data)
        if plen < 126:
            hdr = bytes([0x81, 0x80 | plen]) + mask
        else:
            hdr = bytes([0x81, 0x80 | 126]) + struct.pack(">H", plen) + mask
        self.s.sendall(hdr + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

    def _recv(self) -> dict[str, Any]:
        while True:
            hdr = b""
            while len(hdr) < 2:
                hdr += self.s.recv(2 - len(hdr))
            opcode = hdr[0] & 0x0F
            masked = hdr[1] & 0x80
            plen = hdr[1] & 0x7F
            if plen == 126:
                plen = struct.unpack(">H", self.s.recv(2))[0]
            elif plen == 127:
                plen = struct.unpack(">Q", self.s.recv(8))[0]
            mk = self.s.recv(4) if masked else b""
            data = b""
            while len(data) < plen:
                data += self.s.recv(plen - len(data))
            if masked:
                data = bytes(b ^ mk[i % 4] for i, b in enumerate(data))
            if opcode == 1:
                return json.loads(data)
            if opcode == 8:
                raise RuntimeError("CDP websocket closed")

    def call(
        self, method: str, params: dict[str, Any] | None = None, timeout: float = 40
    ) -> Any:
        self._id += 1
        mid = self._id
        self._send({"id": mid, "method": method, "params": params or {}})
        t0 = time.time()
        while time.time() - t0 < timeout:
            msg = self._recv()
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(msg["error"])
                return msg.get("result")
        raise TimeoutError(method)

    def evaluate(self, expression: str, await_promise: bool = False, timeout: float = 40) -> Any:
        r = self.call(
            "Runtime.evaluate",
            {
                "expression": expression,
                "awaitPromise": await_promise,
                "returnByValue": True,
            },
            timeout=timeout,
        )
        return (r or {}).get("result", {}).get("value")

    def navigate(self, url: str, settle: float = 2.0) -> None:
        self.call("Page.enable")
        self.call("Page.navigate", {"url": url})
        time.sleep(settle)

    def screenshot_png(self) -> bytes:
        self.call("Page.enable")
        r = self.call("Page.captureScreenshot", {"format": "png"}, timeout=20)
        return base64.b64decode(r["data"])

    def screenshot_clip(self, x: float, y: float, width: float, height: float, scale: float = 2.0) -> bytes:
        """Capture a CSS-pixel clip (origin top-left of viewport)."""
        self.call("Page.enable")
        clip = {
            "x": max(0.0, float(x)),
            "y": max(0.0, float(y)),
            "width": float(width),
            "height": float(height),
            "scale": float(scale),
        }
        r = self.call(
            "Page.captureScreenshot",
            {"format": "png", "clip": clip, "captureBeyondViewport": True},
            timeout=20,
        )
        return base64.b64decode(r["data"])

    def get_cookies(self, urls: list[str] | None = None) -> list[dict[str, Any]]:
        self.call("Network.enable")
        if urls:
            r = self.call("Network.getCookies", {"urls": urls})
            return (r or {}).get("cookies") or []
        # All browser cookies (needed to clear site sessions reliably)
        r = self.call("Network.getAllCookies")
        return (r or {}).get("cookies") or []

    def delete_cookies_for_hosts(self, host_substrings: list[str]) -> int:
        """Delete cookies whose domain contains any of the substrings. Returns count."""
        self.call("Network.enable")
        cookies = self.get_cookies()  # getAllCookies
        n = 0
        for c in cookies:
            dom = c.get("domain") or ""
            if any(h in dom for h in host_substrings):
                params: dict[str, Any] = {"name": c["name"]}
                if c.get("domain"):
                    params["domain"] = c["domain"]
                if c.get("path"):
                    params["path"] = c["path"]
                # url helps some Chrome versions delete host-only cookies
                if c.get("domain") and c.get("path") is not None:
                    scheme = "https"
                    host = (c["domain"] or "").lstrip(".")
                    params["url"] = f"{scheme}://{host}{c.get('path') or '/'}"
                try:
                    self.call("Network.deleteCookies", params)
                    n += 1
                except Exception:
                    pass
        return n

    def clear_origin(self, origin: str) -> None:
        """Best-effort clear cookies+storage for one origin."""
        try:
            self.call(
                "Storage.clearDataForOrigin",
                {
                    "origin": origin,
                    "storageTypes": "cookies,local_storage,indexeddb,session_storage",
                },
            )
        except Exception:
            pass

    def close(self) -> None:
        try:
            self.s.close()
        except Exception:
            pass


def new_page_target(cdp_http: str, url: str = "about:blank") -> str:
    """Create a new tab; return its websocket debugger URL id/info."""
    req = urllib.request.Request(
        cdp_http.rstrip("/") + "/json/new?" + url,
        method="PUT",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except Exception:
        # older Chrome: GET
        with urllib.request.urlopen(
            cdp_http.rstrip("/") + "/json/new?" + url, timeout=10
        ) as resp:
            return json.loads(resp.read().decode())
