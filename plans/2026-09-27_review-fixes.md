# レビュー指摘対応計画

- 作成者モデル: Claude Opus 5.5 (claude-opus-5-5)
- 日付: 2026-09-27
- 対象: `reviews/2026-09-27_ax11000-mcp-full.md` の指摘 1〜9

## 目的・背景

- コードレビューで出た confirm ゲートの回避、秘密値のマスク漏れ、設定の読み込み元などの指摘をまとめて解消する
- ローカル stdio の MCP なので外部からの直接攻撃は想定しないが、LLM 経由の誤操作やプロンプトインジェクションへの多層防御として対応する

## 実装方針

| # | 対応 |
|---|------|
| 1 | `raw_request`: `operation` 引数、`data` 内、path クエリ内の operation を解析して 1 つに決める。値が矛盾したら拒否し、実際に送る値でゲートを判定する。`data` は `urlencode` で組み直す |
| 2 | `config`: `./.env` は `AX11000_ALLOW_CWD_ENV=1` のときだけ読む |
| 3 | `_run`: エラーメッセージの `stok=` と `sysauth` をマスクする |
| 4 | `raw_request`: JSON でない応答にも `key=value` / `key: value` 形式の正規表現マスクをかける |
| 5 | README: 書き込み系ツールと `get_wifi` を自動許可にしない運用を明記する |
| 6 | `config`: 明示的に渡した `timeout` を最優先にし、下限を 1 にする |
| 7 | `_run` の戻り値に一律でマスクをかける（`get_wifi(reveal_secrets=True)` のときだけ除外）。`wep_key` / `wpa_key` をマスク対象に追加する |
| 8 | MAC アドレスは区切り文字が揃っているものだけ受け付ける（正規化はライブラリ側が行う）。comment は 32 文字までにする |
| 9 | モッククライアントの fixture を作り、上記のテストを追加する。config のテストは HOME を分離する |
| 10 | 現状維持 |

## 影響ファイル

- `src/ax11000_mcp/server.py`, `src/ax11000_mcp/config.py`
- `tests/conftest.py`（新規）, `tests/test_security.py`, `tests/test_config.py`, `tests/test_mcp_server.py`
- `README.md`, `.env.example`

## リスクと対策

- `./.env` を既定で読まなくなるため、既存利用者の挙動が変わる → README に移行方法（`~/.config` へ移すか、オプトイン用の環境変数を設定する）を書く
- `raw_request` の body を組み直すことでエンコードが変わる → `parse_qsl` / `urlencode` で往復させ、値は保持する

## 完了条件

- 指摘 1〜9 に対応したテストがあり、`pytest` / `ruff check` / `ruff format --check` がすべて通る
- レビュー記録の対応状況を更新する

## 完了記録（2026-09-27）

- 指摘 1〜9 に対応した。`pytest` は 38 passed、`ruff check` / `ruff format --check` もすべて通った
- 変更履歴: 実装中、エラーメッセージのマスク用正規表現が `'sysauth': '...'` のようなクォート付きのキーに対応していないことをテストで検出し、修正した
- 残課題: 実機での動作確認（raw_request の body を組み直したことによる影響）は未実施

## 変更履歴

- 2026-09-27: 指摘 2 の対応方針を変更した
  * 変更前: `./.env`（cwd）を `AX11000_ALLOW_CWD_ENV=1` のときだけ読む
  * 変更後: cwd ではなく、`__file__` から求めたリポジトリ直下の `.env` を常に読む（wheel インストール時は読まない）
  * 理由: README の起動方法（`uv --directory <repo>`）では cwd がリポジトリなので、オプトインにすると「リポジトリに `.env` を置く」という自然な使い方ができなくなる。リポジトリの場所を基準にすれば、使い勝手を保ったまま他のプロジェクトの `.env` を読む問題も防げる
  * 確認: 別ディレクトリ（攻撃者の `.env` を置いたもの）から `uv --directory <repo> run ax11000-mcp` で起動し、`session_info` がリポジトリの `.env` の値を返すことを確認した

## 実機での動作確認（2026-09-27）

- 対象: Archer AX11000 v1.0 / FW 2.2.1 Build 20250725
- 起動方法: README の登録例と同じ `uv --directory <repo> run ax11000-mcp` を MCP クライアントから stdio で呼び出し
- 参照系: `router_overview` / `list_devices` / `get_firmware` / `get_ipv4_status` / `get_ipv6_status` / `get_dhcp_leases` / `list_reservations` / `get_mesh_nodes` / `get_wifi`（2g, 5g, guest_2g）/ `raw_request` がすべて成功
  * `get_wifi` と `raw_request` の `psk_key` はマスクされていた
  * `get_wifi(band="6g")` は AX11000 に 6GHz が無いため `supported: false`（想定どおり）
- 安全ゲート: confirm 無しの `reboot_router` / `set_wifi` / `add_reservation`、data に operation=write を入れた `raw_request` は、実機に送る前に拒否された
- 書き込み系: ダミー MAC（AA:BB:CC:DD:EE:FF）で DHCP 予約を追加 → 一覧に表示 → 削除 → 0 件に戻ることを確認
  * `set_wifi` と `reboot_router` は Wi-Fi やネットワークが途切れるため未実施（ユーザー判断）
- 確認中に見つけて修正したもの:
  * `raw_request` の operation 引数の既定値が "read" だったため、data 側で operation を指定すると confirm=true でも「矛盾」として拒否された → 既定値を "" に変更
  * dataclass の内部名（`_wan_ipv4_ipaddr` 等）がそのまま出力された → 先頭の "_" を除去
  * 2 つ目の 5GHz バンド（`wireless_5g_2`）はライブラリ未対応 → README に `raw_request` での読み取り方法を記載
- 残課題: `add_reservation` の comment が `list_reservations` の結果に出ない（ライブラリの IPv4Reservation に comment 項目が無い）。実害はないため対応しない

## リポジトリ名の変更（2026-09-28）

- AX11000 専用ではなくなったため、`ax11000-mcp` から `tplink-router-mcp` に変更した
  * パッケージ `ax11000_mcp` → `tplink_router_mcp`、コマンド `ax11000-mcp` → `tplink-router-mcp`、FastMCP のサーバ名、README の登録例（`tplink-router`）
  * 設定ディレクトリは `~/.config/tplink-router-mcp/`。旧名の `~/.config/ax11000-mcp/.env` も互換のため読む（新しい方が優先）
- 確認: テスト 46 passed。新しいコマンド名で起動し、旧設定ディレクトリの認証情報で実機の `get_firmware` が成功した
