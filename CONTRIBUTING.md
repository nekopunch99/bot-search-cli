# Contributing to sns-cli

Thanks for helping improve https://github.com/nekopunch99/bot-search-cli.

## Dev setup

```bash
git clone https://github.com/nekopunch99/bot-search-cli.git
cd bot-search-cli
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
sns --help
sns status
```

Without editable install you can still run the root shim:

```bash
./sns status
# or: PYTHONPATH=src python -m sns.cli status
```

## Layout

- Package lives under `src/sns/`
- Console entry: `sns = sns.cli:main` (see `pyproject.toml`)
- User data stays under `~/.sns/` (or `SNS_HOME`) — never inside the repo

## Code style

- Python 3.10+, `from __future__ import annotations`
- Keep modules focused; prefer stdlib + declared deps
- Read-only tooling only (no write/like/comment/post helpers)

## Testing login / search

1. Ensure Chrome CDP is up (`SNS_CDP_URL` / `SOCAI_CDP_URL`, default `9224`).
2. `sns login bili --timeout 5` — should emit `qr_ready` and leave a PNG under `~/.sns/bili/`.
3. For Douyin, prefer cookie import in a private shell; do not paste real cookies into issues or commits.
4. `sns search <source> <query> --pretty` only after that source shows `logged_in` in `sns status`.

## Do not commit

- `.venv/`, `out/`, `**/qr.png`, `**/cookies.txt`, `state.json`, `.sns/`
- Real session cookies, tokens, screenshots of logged-in sessions
- Local absolute paths (use `~/.sns/`, env vars, placeholders)

See `.gitignore`. If you accidentally commit secrets, rotate them and purge history before publishing.

## Attribution

Document Socai dependency honestly (xhs/dy via `socai` CLI; bili is local). Keep [NOTICE](NOTICE) accurate.
