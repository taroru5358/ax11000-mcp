# tplink-router-mcp

[English](README.md) | 日本語

TP-Link ルータ用の MCP サーバ。Claude Code 等から stdio で起動する想定。
軽量 API 直結型 (`tplinkrouterc6u` 利用、Playwright 不要)。
開発と実機確認は Archer AX11000 V1 で行っていますが、他の TP-Link ルータでも使えます (下記「対応機種」)。

実機確認: `GET http://192.168.0.1/` → `/webpages/index.html` (gaming テーマ、`tpEncrypt.js` 系)。

## 対応機種

ルータとの通信には [tplinkrouterc6u](https://github.com/AlexandrErohin/TP-Link-Archer-C6U) を使っています。
接続時に `TplinkRouterProvider.get_client` が機種を自動判定するため、機種ごとの設定は要りません。
このライブラリがサポートする機種 (Archer AX / BE / C / MR / VR シリーズ、Deco、MERCUSYS など 100 機種以上) なら、基本的にこの MCP サーバで操作できます。
サポート機種の一覧は [tplinkrouterc6u の README の「Supported routers」](https://github.com/AlexandrErohin/TP-Link-Archer-C6U#supports) を参照してください。

ただし、使えるツールは機種 (ライブラリ内部のクライアント実装) によって異なります。以下は tplinkrouterc6u 5.35.0 の実装から確認した範囲です。

| ツール | 対応範囲 |
|---|---|
| `router_overview`, `list_devices`, `get_firmware`, `get_ipv4_status`, `set_wifi`, `reboot_router` | ほぼ全機種 |
| `get_dhcp_leases`, `list_reservations` | Archer AX/C 系など一部の機種 |
| `raw_request` | Archer AX/C 系、Deco など一部の機種 |
| `get_mesh_nodes` | Archer AX/C 系 (EasyMesh 対応機)、Deco |
| `get_wifi`, `add_reservation`, `delete_reservation` | Archer AX/C 系 (C6U 系クライアント) のみ |

- 未対応の機種でツールを呼んでも止まりません。`supported: false` やエラーメッセージを返します
- Wi-Fi のバンドは機種によって存在しないものがあります (例: 6GHz は Wi-Fi 6E / 7 対応機のみ)
- トライバンド機 (AX11000 など) の 2 つ目の 5GHz バンド (`wireless_5g_2`) は tplinkrouterc6u が未対応のため `get_wifi` / `set_wifi` では扱えません。読み取りは `raw_request(path="admin/wireless?form=wireless_5g_2")` で可能です
- 動作を実機で確認したのは Archer AX11000 V1 だけです。他機種で試した結果は Issue で教えてもらえると助かります
- 既定の接続先は `192.168.0.1` です。ルータの IP が異なる場合 (例: `192.168.1.1`) は `ROUTER_IP` を設定してください

## セットアップ

```bash
cd /path/to/tplink-router-mcp  # cloneしたディレクトリ
uv sync --group dev
```

認証情報はファイルに保存します。いちばん簡単なのは、clone したリポジトリ直下に `.env` を置く方法です (`.env` は `.gitignore` 済み)。

```bash
cp .env.example .env
# 編集: ROUTER_PASSWORD に管理画面の Local Password を設定 (TP-Link ID では不可)
```

変数: `ROUTER_IP` (既定192.168.0.1), `ROUTER_USERNAME` (既定admin), `ROUTER_PASSWORD` (必須), `ROUTER_TIMEOUT` (秒、最小1)

読み込む場所と優先度 (低→高):

1. `~/.config/tplink-router-mcp/.env` (リポジトリの外に置きたい場合)
2. リポジトリ直下の `.env`
3. `$TPLINK_ENV` で指定したファイル (ルータが複数あるときの切り替えなど)
4. 環境変数

リポジトリ直下の `.env` は、起動時のカレントディレクトリではなく、このリポジトリの場所から探します。
Claude Code をどのプロジェクトで開いていても、そのプロジェクトの `.env` を誤って読むことはありません。
なお `uvx` などでパッケージとしてインストールした場合はリポジトリが無いため、1・3・4 だけを使います。

## 起動確認

```bash
uv run pytest -q
uv run ruff check . && uv run ruff format --check .
ROUTER_PASSWORD=dummy uv run tplink-router-mcp --help || echo "stdio server (helpなしは正常)"
```

## Claude Code 登録例

```json
{
  "mcpServers": {
    "tplink-router": {
      "command": "uv",
      "args": ["--directory", "/path/to/tplink-router-mcp", "run", "tplink-router-mcp"],
      "env": {}
    }
  }
}
```

認証情報は `.env` から読むため `env` は空でよい。
パスワードを直書きする場合のみ `"env": {"ROUTER_PASSWORD": "..."}` を追加。

## ツール

参照: `router_overview`, `list_devices`, `get_firmware`, `get_ipv4_status`, `get_ipv6_status`,
`get_dhcp_leases`, `list_reservations`, `get_mesh_nodes`, `get_wifi`, `session_info`, `list_endpoints`

変更 (confirm必須): `add_reservation`, `delete_reservation`, `set_wifi`, `reboot_router`

汎用: `raw_request(path, data, operation)` — syslog/無線詳細/guest 等の機種差分はこちら。
例: `raw_request(path="status?form=client_status", operation="read")`
戻り値の秘密値は常にマスク。`read`/`load` 以外のoperationは書き込みとみなし `confirm=true` が必須。
operation は `operation` 引数、`data`、path のクエリ文字列のどこで指定しても判定されます。値が矛盾する場合は拒否します。

注意:
- ルータは同時1セッション制限。各ツールは authorize→実行→logout する
- 全ツールの戻り値とエラーメッセージは秘密値 (パスワード / PSK / stok / sysauth 等) をマスクする。Wi-Fi 秘密値のみ `get_wifi(reveal_secrets=true)` で開示可能
- `add_reservation` の comment は 32 文字まで。MAC アドレスは区切り文字を `:` か `-` のどちらかに揃える
- Local Password を使うこと (TP-Link ID不可)。https を使う場合はルータ側で Local Management via HTTPS を有効化
- 既定の接続は平文HTTP (LAN内利用想定)。`ROUTER_IP` に `https://...` を指定すればHTTPSで接続する
