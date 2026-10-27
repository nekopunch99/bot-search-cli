# bot-search-cli

统一**只读**社交搜索 CLI，覆盖 **小红书 (xhs)**、**抖音 (dy)**、**B 站 (bili)**。

JSON 卡片输出风格接近 [Socai](https://github.com/socai-io/socai)。**每个源都必须先登录**；未在 `~/.sns/state.json` 标记登录时，`search` 会直接拒绝。

- **仓库：** https://github.com/nekopunch99/bot-search-cli
- **协议：** Apache-2.0（见 [LICENSE](LICENSE)、[NOTICE](NOTICE)）
- **English:** [README.md](README.md)

## 相对 Socai 的主要改动 / 新增

本项目**基于 / 扩展** Socai 的使用体验与部分能力，**不是**整仓 fork Socai 源码。xhs/dy 搜索仍依赖外部 `socai` CLI。

- 统一 `sns` CLI 与**登录门禁**（未 `login` 拒绝 `search`）
- `~/.sns/state.json` 持久化各源登录状态
- **B 站**原生护照 QR 登录 + cookies + 公开搜索接口（**不经** socai）
- **抖音** Cookie 导入（`--cookies` / `--cookie-file`）并 CDP 注入到 Socai 使用的 Chrome 配置
- 三源统一 search **JSON 卡片**输出
- xhs / dy 搜索仍经 **socai** 子进程 + Chrome CDP

## 依赖

- Python **≥ 3.10**
- 系统已安装 [`socai`](https://github.com/socai-io/socai)（在 `PATH` 上，或设 `SOCAI_BIN`）— **xhs / dy** 搜索需要
- 开启远程调试的 Chrome / Chromium，默认 CDP `http://127.0.0.1:9224`
- Python 依赖：`qrcode[pil]`、`Pillow`（安装时自动拉）

## 安装

```bash
# 克隆本仓库后
pip install -e .

# 或用 uv
uv pip install -e .
```

然后：

```bash
sns --help
sns status
```

可选环境变量：

```bash
export SOCAI_CDP_URL=http://127.0.0.1:9224   # 或 SNS_CDP_URL
# export SOCAI_BIN=/path/to/socai
# export SNS_HOME=~/.sns
# export SNS_OUT_DIR=~/.sns/out
```

## 命令

```bash
sns status
sns login <xhs|dy|bili> [--timeout 180] [--cdp URL]
sns login dy --cookies 'sessionid=...; ...'
sns login dy --cookie-file ~/path/to/cookies.txt
sns logout <xhs|dy|bili|all>
sns search <xhs|dy|bili> <关键词> [--num 5] [--pretty]
```

## 登录与二维码

| 源 | 方式 | 产物路径 |
|----|------|----------|
| **bili** | 护照 QR API → 生成 PNG | `~/.sns/bili/qr.png`（副本在 `SNS_OUT_DIR`，默认 `~/.sns/out/`） |
| **xhs** | Chrome CDP 打开登录页截取 QR | `~/.sns/xhs/qr.png` |
| **dy** | **推荐 Cookie 导入**；截图扫码为备选 | `~/.sns/dy/cookies.txt`；备选 QR 同上 |

登录过程会向 stdout 打事件 JSON，例如：

```json
{"event":"qr_ready","source":"bili","path":".../qr.png"}
{"event":"logged_in","source":"bili"}
```

冒烟可加 `--timeout 5`，超时退出并留下 QR 图。

## 搜索

- **xhs / dy**：门禁通过后调用 `socai xhs search --preview` / `socai dy search`（CDP）。
- **bili**：使用 `~/.sns/bili/cookies.txt` 调公开搜索接口。

未登录示例：

```bash
sns search bili 示例关键词 --num 3 --pretty
# → {"ok": false, "error": "not_logged_in: run `sns login bili` ..."}
```

## 抖音登录（稳定方案）

抖音 SSO 有强风控，脚本直连扫码常遇挑战页。推荐从已登录的 `douyin.com` 浏览器复制 Cookie（至少含 `sessionid`）导入：

```bash
sns login dy --cookies 'sessionid=你的SESSION; sessionid_ss=...; uid_tt=...; sid_guard=...'
# 或
sns login dy --cookie-file ~/dy-cookies.txt
```

会写入 `~/.sns/dy/cookies.txt`，并注入 Socai 用的 Chrome CDP，随后 `sns search dy ...` 可用。

备选：`sns login dy` 仍可走页面截图扫码（易过期，依赖风控放过）。

## 状态与路径

| 路径 | 用途 |
|------|------|
| `~/.sns/state.json` | 各源 `logged_in` / `at` |
| `~/.sns/bili/cookies.txt` | B 站 Cookie 头字符串 |
| `~/.sns/dy/cookies.txt` | 抖音 Cookie 头字符串 |
| `~/.sns/<source>/qr.png` | 主 QR 图 |
| `SNS_OUT_DIR`（默认 `~/.sns/out`） | QR / 调试副本 |

可用 `SNS_HOME` 覆盖根目录。**切勿提交** cookies、QR 图或 `state.json`。

只读：不点赞、不评论、不发布。

## 环境变量

| 变量 | 默认 | 含义 |
|------|------|------|
| `SNS_HOME` | `~/.sns` | 状态、cookies、QR |
| `SNS_OUT_DIR` | `$SNS_HOME/out` | 额外输出副本 |
| `SNS_CDP_URL` / `SOCAI_CDP_URL` | `http://127.0.0.1:9224` | Chrome CDP HTTP |
| `SOCAI_BIN` | PATH 上的 `socai` | socai 可执行文件路径 |

## 已知限制（xhs 扫码 / dy 备选扫码）

- 小红书登录页 QR 通过 Chrome CDP 截取；抖音截图扫码同样依赖页面风控。
- 登录成功判定：小红书看 `customer-sso` / `id_token`；抖音看 `sessionid` / `uid_tt` / `sid_guard`。
- 搜索门禁只认 `~/.sns/state.json` 的 `logged_in`。

## 署名

基于 / 扩展 **[Socai](https://github.com/socai-io/socai)**（[socai.io](https://socai.io/)），Apache-2.0。详见 [NOTICE](NOTICE)。

## 参与贡献

见 [CONTRIBUTING.md](CONTRIBUTING.md)。
