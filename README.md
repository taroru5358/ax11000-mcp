# ax11000-mcp

TP-Link Archer AX11000 (192.168.0.1) 用 MCP サーバ。Claude Code 等から stdio で起動する想定。
軽量 API 直結型 (`tplinkrouterc6u` 利用、Playwright 不要)。

実機確認: `GET http://192.168.0.1/` → `/webpages/index.html` (gaming テーマ、`tpEncrypt.js` 系)。
AX11000 V1 は `tplinkrouterc6u` のサポート対象。

## セットアップ

```bash
cd ~/git_work/ax11000-mcp
uv sync --group dev
```

認証情報はファイルに保存 (優先度 低→高: `~/.config/ax11000-mcp/.env` → `./.env` → `$TPLINK_ENV` → 環境変数):

```bash
mkdir -p ~/.config/ax11000-mcp
cp .env.example ~/.config/ax11000-mcp/.env
# 編集: ROUTER_PASSWORD に管理画面の Local Password を設定 (TP-Link ID では不可)
```

変数: `ROUTER_IP` (既定192.168.0.1), `ROUTER_USERNAME` (既定admin), `ROUTER_PASSWORD` (必須), `ROUTER_TIMEOUT`

## 起動確認

```bash
uv run pytest -q
uv run ruff check . && uv run ruff format --check .
ROUTER_PASSWORD=dummy uv run ax11000-mcp --help || echo "stdio server (helpなしは正常)"
```

## Claude Code 登録例

```json
{
  "mcpServers": {
    "ax11000": {
      "command": "uv",
      "args": ["--directory", "~/git_work/ax11000-mcp", "run", "ax11000-mcp"],
      "env": {}
    }
  }
}
```

認証情報は `~/.config/ax11000-mcp/.env` から読むため `env` は空でよい。
パスワードを直書きする場合のみ `"env": {"ROUTER_PASSWORD": "..."}` を追加。

## ツール

参照: `router_overview`, `list_devices`, `get_firmware`, `get_ipv4_status`, `get_ipv6_status`,
`get_dhcp_leases`, `list_reservations`, `get_mesh_nodes`, `get_wifi`, `session_info`, `list_endpoints`

変更 (confirm必須): `add_reservation`, `delete_reservation`, `set_wifi`, `reboot_router`

汎用: `raw_request(path, data, operation)` — syslog/無線詳細/guest 等の機種差分はこちら。
例: `raw_request(path="status?form=client_status", operation="read")`

注意:
- ルータは同時1セッション制限。各ツールは authorize→実行→logout する
- Wi-Fi 秘密値は既定マスク (`reveal_secrets=true` で開示)
- Local Password を使うこと (TP-Link ID不可)。https を使う場合はルータ側で Local Management via HTTPS を有効化
