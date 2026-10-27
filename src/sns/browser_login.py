"""Xiaohongshu / Douyin QR login via Chrome CDP screenshots."""
from __future__ import annotations

import base64
import json
import time
from typing import Any

from .cdp import CdpClient
from .paths import CDP_URL, QR_OUT, QR_PATH, ensure_dirs
from .qrutil import write_bytes_png
from .state import mark_logged_in

XHS_LOGIN_URLS = [
    "https://www.xiaohongshu.com/login",
    "https://www.xiaohongshu.com/",
]
DY_LOGIN_URLS = [
    "https://www.douyin.com/",
]

XHS_HOSTS = ["xiaohongshu.com", "xhscdn.com"]
DY_HOSTS = ["douyin.com", "douyinpic.com", "byteoversea.com"]

XHS_ORIGINS = ["https://www.xiaohongshu.com", "https://xiaohongshu.com"]
DY_ORIGINS = ["https://www.douyin.com", "https://douyin.com"]

# Strong auth cookies only (web_session exists for anonymous XHS visitors too)
XHS_COOKIE_HINTS = ("customer-sso", "id_token", "access-token", "access_token")
DY_COOKIE_HINTS = ("sessionid", "sessionid_ss", "uid_tt", "sid_guard")


def _emit(obj: dict[str, Any]) -> None:
    print(json.dumps(obj, ensure_ascii=False), flush=True)


def _cookie_names(cookies: list[dict[str, Any]]) -> set[str]:
    return {c.get("name") or "" for c in cookies}


def _has_login_cookies(cookies: list[dict[str, Any]], hints: tuple[str, ...]) -> bool:
    names = _cookie_names(cookies)
    if any(h in names for h in hints):
        return True
    for c in cookies:
        if c.get("name") == "LOGIN_STATUS" and str(c.get("value")) in ("1", "true", "True"):
            if "sessionid" in names or "sessionid_ss" in names or "uid_tt" in names:
                return True
    return False


def _check_xhs_js(cdp: CdpClient) -> bool:
    expr = """(() => {
      try {
        const cookies = document.cookie || '';
        const strong = /(?:customer-sso|id_token)=/.test(cookies);
        let userId = '';
        try {
          const st = window.__INITIAL_STATE__ || {};
          const u = st.user || {};
          userId = u.userId || (u.userInfo && u.userInfo.userId) || '';
        } catch (e) {}
        return JSON.stringify({strong, userId: String(userId || ''), href: location.href});
      } catch (e) {
        return JSON.stringify({error: String(e)});
      }
    })()"""
    try:
        raw = cdp.evaluate(expr) or "{}"
        st = json.loads(raw)
        return bool(st.get("strong") or st.get("userId"))
    except Exception:
        return False


def _check_dy_js(cdp: CdpClient) -> bool:
    expr = """(() => {
      try {
        const cookies = document.cookie || '';
        const ck = /(?:sessionid|uid_tt|sid_guard)=/.test(cookies);
        return JSON.stringify({ck, href: location.href});
      } catch (e) {
        return JSON.stringify({error: String(e)});
      }
    })()"""
    try:
        raw = cdp.evaluate(expr) or "{}"
        st = json.loads(raw)
        return bool(st.get("ck"))
    except Exception:
        return False


def _try_click_login(cdp: CdpClient, source: str) -> None:
    if source == "xhs":
        js = """(() => {
          const texts = ['登录', '登陆'];
          const nodes = Array.from(document.querySelectorAll('a,button,span,div'));
          for (const n of nodes) {
            const t = (n.innerText || n.textContent || '').trim();
            if (texts.includes(t) && n.offsetParent !== null) { n.click(); return 'clicked:'+t; }
          }
          return 'none';
        })()"""
    else:
        # Prefer header 登录 (top-right), then 扫码登录 tab
        js = """(() => {
          const steps = [];
          const loginBtns = Array.from(document.querySelectorAll('button,div,span,a'))
            .filter(n => (n.innerText || '').trim() === '登录' && n.offsetParent !== null);
          for (const n of loginBtns) {
            const r = n.getBoundingClientRect();
            if (r.top < 100 && r.right > window.innerWidth - 260) {
              n.click(); steps.push('header-login'); break;
            }
          }
          if (!steps.length) {
            for (const n of loginBtns) { n.click(); steps.push('login-any'); break; }
          }
          const scan = Array.from(document.querySelectorAll('div,span,button,a'))
            .find(n => (n.innerText || '').trim() === '扫码登录' && n.offsetParent !== null);
          if (scan) { scan.click(); steps.push('scan-tab'); }
          return steps.join(',') || 'none';
        })()"""
    try:
        r = cdp.evaluate(js)
        _emit({"event": "login_click", "source": source, "result": r})
    except Exception as e:
        _emit({"event": "login_click_error", "source": source, "error": str(e)})



def _mouse_click_xy(cdp: CdpClient, x: float, y: float) -> None:
    cdp.call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
    for typ in ("mousePressed", "mouseReleased"):
        cdp.call(
            "Input.dispatchMouseEvent",
            {"type": typ, "x": x, "y": y, "button": "left", "clickCount": 1},
        )


def _open_dy_login_modal(cdp: CdpClient) -> str:
    """Open Douyin login modal with a real mouse click; do not toggle if already open."""
    state = cdp.evaluate(
        """(() => {
      const t = document.body ? document.body.innerText : '';
      const open = t.includes('扫码登录') && (t.includes('打开「抖音APP」') || t.includes('扫一扫'));
      const candidates = [...document.querySelectorAll('button,div,span,a')].filter(n => {
        const x = (n.innerText || '').trim();
        return x === '登录' && n.offsetParent !== null;
      });
      candidates.sort((a,b) => b.getBoundingClientRect().right - a.getBoundingClientRect().right);
      if (!candidates.length) return JSON.stringify({open, btn: null});
      const r = candidates[0].getBoundingClientRect();
      return JSON.stringify({open, btn: {x: r.x + r.width/2, y: r.y + r.height/2}});
    })()"""
    )
    import json as _json
    st = _json.loads(state or "{}")
    if st.get("open"):
        # ensure 扫码登录 tab
        cdp.evaluate(
            """(() => {
              const tab = [...document.querySelectorAll('div,span,button')]
                .find(n => (n.innerText || '').trim() === '扫码登录' && n.offsetParent !== null);
              if (tab) tab.click();
              return 'ok';
            })()"""
        )
        return "already-open"
    btn = st.get("btn")
    if not btn:
        return "no-btn"
    _mouse_click_xy(cdp, float(btn["x"]), float(btn["y"]))
    time.sleep(2.5)
    cdp.evaluate(
        """(() => {
          const tab = [...document.querySelectorAll('div,span,button')]
            .find(n => (n.innerText || '').trim() === '扫码登录' && n.offsetParent !== null);
          if (tab) tab.click();
          return 'ok';
        })()"""
    )
    return "mouse-clicked"


def _find_qr_payload(cdp: CdpClient) -> dict[str, Any]:
    """Locate QR as data-URL image or CSS box for clip capture."""
    expr = """(() => {
      const out = {via: null, dataUrl: null, clip: null, note: ''};
      const imgs = Array.from(document.querySelectorAll('img'));
      // Prefer square data:image PNG near 扫码登录
      const dataImgs = imgs.filter(el => {
        const src = el.currentSrc || el.src || '';
        if (!src.startsWith('data:image')) return false;
        const r = el.getBoundingClientRect();
        return r.width >= 120 && r.height >= 120 && Math.abs(r.width - r.height) < 40
               && r.bottom > 0 && r.right > 0 && r.top < window.innerHeight;
      });
      if (dataImgs.length) {
        // Prefer one closest to vertical center (login modal)
        dataImgs.sort((a,b) => Math.abs((a.getBoundingClientRect().top+a.getBoundingClientRect().bottom)/2 - window.innerHeight/2)
                             - Math.abs((b.getBoundingClientRect().top+b.getBoundingClientRect().bottom)/2 - window.innerHeight/2));
        const el = dataImgs[0];
        const r = el.getBoundingClientRect();
        out.via = 'data-url';
        out.dataUrl = el.currentSrc || el.src;
        out.clip = {x: r.x - 12, y: r.y - 12, width: r.width + 24, height: r.height + 24};
        out.note = 'img data URL';
        return JSON.stringify(out);
      }
      // Canvas QR
      for (const el of document.querySelectorAll('canvas')) {
        const r = el.getBoundingClientRect();
        if (r.width >= 120 && r.height >= 120 && Math.abs(r.width - r.height) < 50
            && r.top > 80 && r.top < window.innerHeight - 80) {
          try {
            out.via = 'canvas';
            out.dataUrl = el.toDataURL('image/png');
            out.clip = {x: r.x - 12, y: r.y - 12, width: r.width + 24, height: r.height + 24};
            out.note = 'canvas';
            return JSON.stringify(out);
          } catch (e) {}
        }
      }
      // Panel containing 扫码登录 — clip left half (QR column)
      for (const n of document.querySelectorAll('div,section')) {
        const t = (n.innerText || '').trim();
        if (!(t.includes('扫码登录') && (t.includes('扫一扫') || t.includes('打开')))) continue;
        const r = n.getBoundingClientRect();
        if (r.width < 280 || r.width > 1000 || r.height < 200) continue;
        out.via = 'panel-clip';
        // left 48% is usually the QR column on Douyin
        out.clip = {x: r.x + 20, y: r.y + 50, width: Math.min(r.width * 0.48, 320), height: Math.min(r.height - 70, 360)};
        out.note = 'login panel left column';
        return JSON.stringify(out);
      }
      out.via = 'none';
      out.note = 'no QR found';
      return JSON.stringify(out);
    })()"""
    raw = cdp.evaluate(expr) or "{}"
    try:
        return json.loads(raw)
    except Exception:
        return {"via": "none", "note": "parse_error", "raw": raw[:200]}


def _save_qr_from_page(cdp: CdpClient, source: str) -> tuple[str, dict[str, Any]]:
    """Write a scannable QR PNG (cropped / data-URL), not a full-page screenshot."""
    info = _find_qr_payload(cdp)
    png: bytes | None = None
    if info.get("dataUrl") and str(info["dataUrl"]).startswith("data:image"):
        try:
            b64 = str(info["dataUrl"]).split(",", 1)[1]
            png = base64.b64decode(b64)
            info["saved_via"] = "data-url"
        except Exception as e:
            info["data_url_error"] = str(e)
    if png is None and info.get("clip"):
        c = info["clip"]
        try:
            png = cdp.screenshot_clip(c["x"], c["y"], c["width"], c["height"], scale=3.0)
            info["saved_via"] = info.get("via") or "clip"
        except Exception as e:
            info["clip_error"] = str(e)
    if png is None:
        # Last resort: full page (legacy) — still better than failing hard
        png = cdp.screenshot_png()
        info["saved_via"] = "fullpage-fallback"
    path = write_bytes_png(png, QR_PATH[source], also=QR_OUT[source])
    return str(path), info


def login_browser(
    source: str,
    timeout: float = 180.0,
    poll_interval: float = 3.0,
    cdp_url: str | None = None,
) -> dict[str, Any]:
    if source not in ("xhs", "dy"):
        raise ValueError(source)
    ensure_dirs()
    cdp_http = cdp_url or CDP_URL
    hosts = XHS_HOSTS if source == "xhs" else DY_HOSTS
    origins = XHS_ORIGINS if source == "xhs" else DY_ORIGINS
    urls = XHS_LOGIN_URLS if source == "xhs" else DY_LOGIN_URLS
    hints = XHS_COOKIE_HINTS if source == "xhs" else DY_COOKIE_HINTS
    js_check = _check_xhs_js if source == "xhs" else _check_dy_js

    cdp = CdpClient(cdp_http, prefer_url_substr=("douyin.com" if source == "dy" else "xiaohongshu.com"))
    try:
        cdp.call("Page.enable")
        cdp.call("Runtime.enable")
        cdp.call("Network.enable")

        deleted = cdp.delete_cookies_for_hosts(hosts)
        for origin in origins:
            cdp.clear_origin(origin)
        _emit(
            {
                "event": "session_cleared",
                "source": source,
                "deleted_cookies": deleted,
                "origins": origins,
            }
        )

        nav_url = urls[0]
        cdp.navigate(nav_url, settle=3.0)
        deleted2 = cdp.delete_cookies_for_hosts(hosts)
        for origin in origins:
            cdp.clear_origin(origin)
        cdp.navigate(nav_url, settle=2.5)
        if source == "dy":
            r = _open_dy_login_modal(cdp)
            _emit({"event": "login_click", "source": source, "result": r})
            time.sleep(2.0)
        else:
            _try_click_login(cdp, source)
            time.sleep(2.5)

        all_c = cdp.get_cookies()
        site_c0 = [c for c in all_c if any(h in (c.get("domain") or "") for h in hosts)]
        still = _has_login_cookies(site_c0, hints)
        _emit(
            {
                "event": "precheck",
                "source": source,
                "deleted_cookies_pass2": deleted2,
                "still_logged_in_cookies": still,
                "auth_cookie_names": sorted(
                    n for n in _cookie_names(site_c0) if n in hints or n == "LOGIN_STATUS"
                ),
            }
        )
        if still:
            cdp.delete_cookies_for_hosts(hosts)
            for origin in origins:
                cdp.clear_origin(origin)
            cdp.navigate(nav_url, settle=2.0)
            _try_click_login(cdp, source)
            time.sleep(2.0)

        # Wait for real QR (Douyin often shows logo placeholder first / risk-control)
        info = {"via": "none"}
        for _ in range(20):
            info = _find_qr_payload(cdp)
            if info.get("via") in ("data-url", "canvas"):
                break
            if source == "dy":
                _open_dy_login_modal(cdp)
            else:
                _try_click_login(cdp, source)
            time.sleep(1.0)

        qr_path, info = _save_qr_from_page(cdp, source)
        if source == "dy" and (info.get("saved_via") or "") == "fullpage-fallback":
            _emit({
                "event": "qr_blocked",
                "source": "dy",
                "hint": "Douyin did not render a scannable QR (often 4031 risk control). Enable 'Route traffic through this computer' or complete captcha on the box desktop, then retry sns login dy.",
                "path": qr_path,
            })
        _emit(
            {
                "event": "qr_ready",
                "source": source,
                "path": qr_path,
                "out": str(QR_OUT[source]),
                "via": info.get("saved_via") or info.get("via"),
                "note": info.get("note") or "",
                "login_url": nav_url,
            }
        )

        site_now = [
            c
            for c in cdp.get_cookies()
            if any(h in (c.get("domain") or "") for h in hosts)
        ]
        saw_logged_out = (not _has_login_cookies(site_now, hints)) and (not js_check(cdp))

        t0 = time.time()
        last_shot = time.time()
        while time.time() - t0 < timeout:
            all_c = cdp.get_cookies()
            site_c = [c for c in all_c if any(h in (c.get("domain") or "") for h in hosts)]
            ok_cookie = _has_login_cookies(site_c, hints)
            ok_js = js_check(cdp)
            if not (ok_cookie or ok_js):
                saw_logged_out = True
            if (ok_cookie or ok_js) and saw_logged_out:
                mark_logged_in(source)
                out = {
                    "event": "logged_in",
                    "source": source,
                    "via": "cookie" if ok_cookie else "js",
                    "cookie_names": sorted(_cookie_names(site_c))[:30],
                }
                _emit(out)
                return out

            if time.time() - last_shot > 15:
                try:
                    if source == "dy":
                        _try_click_login(cdp, source)
                        time.sleep(1)
                    qr_path, info = _save_qr_from_page(cdp, source)
                    last_shot = time.time()
                    _emit(
                        {
                            "event": "qr_refreshed",
                            "source": source,
                            "path": qr_path,
                            "via": info.get("saved_via") or info.get("via"),
                            "elapsed_s": int(time.time() - t0),
                        }
                    )
                except Exception as e:
                    _emit({"event": "qr_refresh_error", "source": source, "error": str(e)})

            _emit(
                {
                    "event": "poll",
                    "source": source,
                    "status": "waiting_scan",
                    "elapsed_s": int(time.time() - t0),
                    "cookie_count": len(site_c),
                    "saw_logged_out": saw_logged_out,
                }
            )
            time.sleep(poll_interval)

        raise TimeoutError(
            f"{source} login timed out after {timeout}s. "
            f"Screenshot QR at {QR_PATH[source]} (also {QR_OUT[source]}). "
            f"Open Chrome on CDP {cdp_http}, scan with the mobile app."
        )
    finally:
        cdp.close()
