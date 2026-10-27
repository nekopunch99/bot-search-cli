"""sns CLI: unified read-only social search with QR login gate."""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from . import bili as bili_mod
from . import browser_login
from . import dy as dy_mod
from .paths import BILI_COOKIES, CDP_URL, QR_OUT, QR_PATH, SOURCES, STATE_PATH, ensure_dirs
from .dy import DY_COOKIES
from . import socai_wrap
from .state import load_state, mark_logged_out, require_login


def _print(obj: Any, pretty: bool) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2 if pretty else None))


def cmd_status(args: argparse.Namespace) -> int:
    ensure_dirs()
    st = load_state()
    out = {
        "ok": True,
        "state_path": str(STATE_PATH),
        "cdp": CDP_URL,
        "sources": st,
        "qr_paths": {s: str(QR_PATH[s]) for s in SOURCES},
        "qr_out": {s: str(QR_OUT[s]) for s in SOURCES},
        "bili_cookies": str(BILI_COOKIES),
        "dy_cookies": str(DY_COOKIES),
    }
    _print(out, True)
    return 0


def cmd_logout(args: argparse.Namespace) -> int:
    src = args.source
    st = mark_logged_out(src)
    if src in ("bili", "all"):
        try:
            if BILI_COOKIES.exists():
                BILI_COOKIES.write_text("", encoding="utf-8")
        except Exception:
            pass
    if src in ("dy", "all"):
        try:
            if DY_COOKIES.exists():
                DY_COOKIES.write_text("", encoding="utf-8")
        except Exception:
            pass
    _print({"ok": True, "logged_out": src, "sources": st}, True)
    return 0


def cmd_login(args: argparse.Namespace) -> int:
    src = args.source
    timeout = float(args.timeout)
    try:
        if src == "bili":
            bili_mod.login(timeout=timeout)
        elif src == "dy" and (getattr(args, "cookies", None) or getattr(args, "cookie_file", None)):
            if args.cookie_file:
                dy_mod.login_with_cookie_file(args.cookie_file, cdp_url=args.cdp)
            else:
                dy_mod.login_with_cookies(args.cookies, cdp_url=args.cdp)
        elif src in ("xhs", "dy"):
            browser_login.login_browser(src, timeout=timeout, cdp_url=args.cdp)
        else:
            _print({"ok": False, "error": f"unknown source {src}"}, True)
            return 2
    except TimeoutError as e:
        _print({"ok": False, "event": "timeout", "source": src, "error": str(e)}, True)
        return 1
    except Exception as e:
        _print({"ok": False, "event": "error", "source": src, "error": str(e)}, True)
        return 1
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    src = args.source
    gate = require_login(src)
    if gate is not None:
        _print(gate, args.pretty)
        return 2
    try:
        if src == "bili":
            out = bili_mod.search(args.query, num=args.num)
        elif src == "xhs":
            out = socai_wrap.search_xhs(args.query, num=args.num)
        elif src == "dy":
            out = socai_wrap.search_dy(args.query, num=args.num)
        else:
            out = {"ok": False, "error": f"unknown source {src}"}
    except Exception as e:
        out = {"ok": False, "source": src, "error": str(e)}
        _print(out, args.pretty)
        return 1
    _print(out, args.pretty)
    return 0 if out.get("ok") else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="sns",
        description="统一只读社交搜索 CLI（小红书 / 抖音 / B站），每个源必须先扫码登录",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("status", help="查看各源登录状态")
    sp.set_defaults(func=cmd_status)

    lp = sub.add_parser("login", help="扫码登录某一源")
    lp.add_argument("source", choices=list(SOURCES))
    lp.add_argument(
        "--timeout",
        type=float,
        default=180.0,
        help="等待扫码超时秒数（默认 180；冒烟可用 5）",
    )
    lp.add_argument(
        "--cdp",
        default=CDP_URL,
        help=f"Chrome CDP HTTP 地址（默认 {CDP_URL}）",
    )
    lp.add_argument(
        "--cookies",
        default=None,
        help="抖音：粘贴浏览器 Cookie 头（含 sessionid），比截图扫码稳",
    )
    lp.add_argument(
        "--cookie-file",
        default=None,
        help="抖音：从文件读 Cookie（一行 Cookie 头或 name=value 多行）",
    )
    lp.set_defaults(func=cmd_login)

    op = sub.add_parser("logout", help="清除登录标记")
    op.add_argument("source", choices=[*SOURCES, "all"])
    op.set_defaults(func=cmd_logout)

    sep = sub.add_parser("search", help="搜索（未登录会拒绝）")
    sep.add_argument("source", choices=list(SOURCES))
    sep.add_argument("query")
    sep.add_argument("--num", type=int, default=5)
    sep.add_argument("--pretty", action="store_true")
    sep.set_defaults(func=cmd_search)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
