# sns-cli

Unified **read-only** social search CLI for **Xiaohongshu (xhs)**, **Douyin (dy)**, and **Bilibili (bili)**.

JSON card output is intentionally close to [Socai](https://github.com/socai-io/socai). Each source must be logged in first; `search` is refused until `~/.sns/state.json` marks that source as logged in.

- **Repository:** https://github.com/nekopunch99/sns-cli-search
- **License:** Apache-2.0 (see [LICENSE](LICENSE), [NOTICE](NOTICE))
- **Chinese docs:** [README.zh-CN.md](README.zh-CN.md)

## What's different from Socai

This project **builds on / extends** the Socai experience. It is **not** a verbatim fork of the Socai source tree. xhs/dy search still call the external `socai` CLI.

- Unified `sns` CLI with a **login gate** (`search` rejected until `sns login <source>`)
- Persistent login state in `~/.sns/state.json`
- **Bilibili** native passport QR login + cookies + public search HTTP APIs (does **not** go through socai)
- **Douyin** cookie import (`--cookies` / `--cookie-file`) with CDP inject into the Chrome profile Socai uses
- Unified search JSON **cards** across xhs / dy / bili
- xhs / dy search still run via **socai** subprocess + Chrome CDP

## Requirements

- Python **≥ 3.10**
- System-installed [`socai`](https://github.com/socai-io/socai) on `PATH` (or set `SOCAI_BIN`) — needed for **xhs** and **dy** search
- Chrome (or Chromium) with remote debugging, default CDP `http://127.0.0.1:9224`
- Python deps: `qrcode[pil]`, `Pillow` (installed automatically)

## Install

```bash
# From a clone of this repo
pip install -e .

# Or with uv
uv pip install -e .
```

Then:

```bash
sns --help
sns status
```

Optional env:

```bash
export SOCAI_CDP_URL=http://127.0.0.1:9224   # or SNS_CDP_URL
# export SOCAI_BIN=/path/to/socai
# export SNS_HOME=~/.sns
# export SNS_OUT_DIR=~/.sns/out
```

## Commands

```bash
sns status
sns login <xhs|dy|bili> [--timeout 180] [--cdp URL]
sns login dy --cookies 'sessionid=...; ...'
sns login dy --cookie-file ~/path/to/cookies.txt
sns logout <xhs|dy|bili|all>
sns search <xhs|dy|bili> <query> [--num 5] [--pretty]
```

## Login & QR codes

| Source | Method | Artifacts |
|--------|--------|-----------|
| **bili** | Passport QR API → PNG | `~/.sns/bili/qr.png` (copy under `SNS_OUT_DIR`, default `~/.sns/out/`) |
| **xhs** | Chrome CDP open login page → crop QR | `~/.sns/xhs/qr.png` |
| **dy** | **Preferred:** cookie import; screenshot QR is fallback | `~/.sns/dy/cookies.txt`; QR same pattern |

Login streams event JSON on stdout, e.g.:

```json
{"event":"qr_ready","source":"bili","path":".../qr.png"}
{"event":"logged_in","source":"bili"}
```

Use `--timeout 5` for a quick smoke test (leaves the QR image on timeout).

## Search

- **xhs / dy:** after the login gate, runs `socai xhs search --preview` / `socai dy search` (CDP).
- **bili:** uses `~/.sns/bili/cookies.txt` against Bilibili public search APIs.

Not logged in:

```bash
sns search bili example-query --num 3 --pretty
# → {"ok": false, "error": "not_logged_in: run `sns login bili` ..."}
```

## Douyin login (stable path)

Douyin SSO often challenges scripted QR flows. Prefer importing cookies from a browser already logged into `douyin.com` (at least `sessionid`):

```bash
sns login dy --cookies 'sessionid=YOUR_SESSION; sessionid_ss=...; uid_tt=...; sid_guard=...'
# or
sns login dy --cookie-file ~/dy-cookies.txt
```

This writes `~/.sns/dy/cookies.txt` and injects cookies into the Socai Chrome CDP profile so `sns search dy ...` works.

Fallback: `sns login dy` still attempts page-screenshot QR (fragile under risk control).

## State & paths

| Path | Purpose |
|------|---------|
| `~/.sns/state.json` | Per-source `logged_in` / `at` |
| `~/.sns/bili/cookies.txt` | Bilibili Cookie header string |
| `~/.sns/dy/cookies.txt` | Douyin Cookie header string |
| `~/.sns/<source>/qr.png` | Primary QR image |
| `SNS_OUT_DIR` (default `~/.sns/out`) | Extra QR / debug copies |

Override home with `SNS_HOME`. **Never commit** cookies, QR images, or `state.json`.

Read-only: no likes, comments, or posts.

## Environment variables

| Variable | Default | Meaning |
|----------|---------|---------|
| `SNS_HOME` | `~/.sns` | State, cookies, QR |
| `SNS_OUT_DIR` | `$SNS_HOME/out` | Extra output copies |
| `SNS_CDP_URL` / `SOCAI_CDP_URL` | `http://127.0.0.1:9224` | Chrome CDP HTTP endpoint |
| `SOCAI_BIN` | `socai` on `PATH` | Path to socai binary |

## Attribution

Inspired by / builds on **[Socai](https://github.com/socai-io/socai)** ([socai.io](https://socai.io/)), Apache-2.0. See [NOTICE](NOTICE).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).
