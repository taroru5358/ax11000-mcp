"""AX11000 MCP server (stdio, Claude Code向け)."""

from __future__ import annotations

import ipaddress
import json
import re
from collections.abc import Callable
from typing import Any

from mcp.server.fastmcp import FastMCP
from tplinkrouterc6u import Connection, TplinkRouterProvider

from .config import RouterConfig, load_config

mcp = FastMCP("ax11000-mcp")

ENDPOINT_CATALOG = [
    {
        "name": "router_overview",
        "kind": "read",
        "desc": "firmware+status+WAN+CPU/メモリ+台数のダッシュボード",
    },
    {"name": "list_devices", "kind": "read", "desc": "接続デバイス一覧 (hostname/IP/MAC/接続種別)"},
    {"name": "get_firmware", "kind": "read", "desc": "ファーム/ハードウェアバージョン"},
    {"name": "get_ipv4_status", "kind": "read", "desc": "WAN/LAN IPv4 状態"},
    {"name": "get_ipv6_status", "kind": "read", "desc": "IPv6 WAN 状態 (未対応機種あり)"},
    {"name": "get_dhcp_leases", "kind": "read", "desc": "DHCPリース一覧"},
    {"name": "list_reservations", "kind": "read", "desc": "DHCPアドレス予約一覧"},
    {"name": "get_mesh_nodes", "kind": "read", "desc": "EasyMeshノード一覧"},
    {"name": "get_wifi", "kind": "read", "desc": "指定バンドのWi-Fi設定 (秘密値は既定マスク)"},
    {"name": "session_info", "kind": "read", "desc": "接続設定の安全サマリ (パスワードは出さない)"},
    {"name": "list_endpoints", "kind": "read", "desc": "本MCPのツールカタログ"},
    {"name": "add_reservation", "kind": "write", "desc": "DHCP予約追加 (confirm必須)"},
    {"name": "delete_reservation", "kind": "write", "desc": "DHCP予約削除 (confirm必須)"},
    {"name": "set_wifi", "kind": "write", "desc": "Wi-Fi ON/OFF (confirm必須)"},
    {"name": "reboot_router", "kind": "write", "desc": "再起動 (confirm必須)"},
    {
        "name": "raw_request",
        "kind": "raw",
        "desc": "任意エンドポイント読取 (秘密値は常にマスク。read/load以外はconfirm必須)",
    },
]

BAND_MAP: dict[str, Connection] = {
    "2g": Connection.HOST_2G,
    "host_2g": Connection.HOST_2G,
    "5g": Connection.HOST_5G,
    "host_5g": Connection.HOST_5G,
    "6g": Connection.HOST_6G,
    "host_6g": Connection.HOST_6G,
    "guest_2g": Connection.GUEST_2G,
    "guest_5g": Connection.GUEST_5G,
    "guest_6g": Connection.GUEST_6G,
    "iot_2g": Connection.IOT_2G,
    "iot_5g": Connection.IOT_5G,
    "iot_6g": Connection.IOT_6G,
}


def _jsonable(obj: Any) -> Any:
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_jsonable(v) for v in obj]
    if hasattr(obj, "__dataclass_fields__"):
        out: dict[str, Any] = {}
        for f in obj.__dataclass_fields__:  # type: ignore[attr-defined]
            out[f] = _jsonable(getattr(obj, f))
        return out
    if hasattr(obj, "__dict__"):
        return {k: _jsonable(v) for k, v in vars(obj).items() if not k.startswith("_")}
    return str(obj)


REDACTED = "*** (masked)"

# 部分一致で秘密値とみなすキー (小文字比較)。"key" は予約ID等でも使うため対象外
_SENSITIVE_SUBSTRINGS = (
    "password",
    "passwd",
    "psk",
    "passphrase",
    "secret",
    "token",
    "stok",
    "sysauth",
)

_MAC_RE = re.compile(r"^([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}$")


def _redact_recursive(obj: Any) -> Any:
    """入れ子構造を再帰走査し、秘密値らしいキーの値をマスクする。"""
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            kl = str(k).lower()
            if any(s in kl for s in _SENSITIVE_SUBSTRINGS) and v:
                out[k] = REDACTED
            else:
                out[k] = _redact_recursive(v)
        return out
    if isinstance(obj, (list, tuple)):
        return [_redact_recursive(v) for v in obj]
    return obj


def _redact_wifi(d: dict, reveal: bool) -> dict:
    if reveal:
        return d
    return _redact_recursive(d)


def _valid_mac(mac: str) -> bool:
    return bool(_MAC_RE.fullmatch(mac.strip()))


def _valid_ipv4(addr: str) -> bool:
    try:
        ipaddress.IPv4Address(addr.strip())
        return True
    except ipaddress.AddressValueError:
        return False


def _get_client(cfg: RouterConfig | None = None):
    cfg = cfg or load_config()
    client = TplinkRouterProvider.get_client(
        cfg.base_url(), cfg.password, cfg.username, timeout=cfg.timeout
    )
    return client, cfg


def _run(fn: Callable[[Any], Any]) -> Any:
    client, cfg = _get_client()
    try:
        client.authorize()
        try:
            return fn(client)
        finally:
            try:
                client.logout()
            except Exception:
                pass
    except Exception as e:
        msg = str(e)
        password = getattr(cfg, "password", "")
        if password:
            msg = msg.replace(password, REDACTED)
        raise RuntimeError(f"router request failed: {msg}") from e


def _unsupported(tool: str, e: Exception) -> dict:
    return {"supported": False, "tool": tool, "error": f"{type(e).__name__}: {e}"}


@mcp.tool()
def router_overview() -> dict:
    """ダッシュボード: firmware/CPU/メモリ/WAN/デバイス台数。"""

    def _fn(client):
        fw = _redact_recursive(_jsonable(client.get_firmware()))
        st = client.get_status()
        std = _jsonable(st)
        devices = std.pop("devices", []) if isinstance(std, dict) else []
        summary = {}
        if isinstance(std, dict):
            for k in (
                "wan_ipv4_addr",
                "lan_ipv4_addr",
                "conn_type",
                "cpu_usage",
                "mem_usage",
                "wan_ipv4_uptime",
                "wired_total",
                "wifi_clients_total",
                "guest_clients_total",
                "clients_total",
                "iot_clients_total",
                "wifi_2g_enable",
                "wifi_5g_enable",
                "wifi_6g_enable",
            ):
                if k in std:
                    summary[k] = std[k]
        return {
            "firmware": fw,
            "summary": summary,
            "status": _redact_recursive(std),
            "devices": devices,
        }

    return _run(_fn)


@mcp.tool()
def list_devices() -> dict:
    """接続デバイス一覧 (hostname/IP/MAC/接続種別)。"""

    def _fn(client):
        st = client.get_status()
        return {
            "devices": _jsonable(getattr(st, "devices", [])),
            "total": getattr(st, "clients_total", None),
        }

    return _run(_fn)


@mcp.tool()
def get_firmware() -> dict:
    """ファームウェア情報。"""
    return _run(lambda c: _jsonable(c.get_firmware()))


@mcp.tool()
def get_ipv4_status() -> dict:
    """WAN/LAN IPv4 状態。"""
    return _run(lambda c: _jsonable(c.get_ipv4_status()))


@mcp.tool()
def get_ipv6_status() -> dict:
    """IPv6 WAN 状態。未対応の場合は supported=false。"""
    try:
        return _run(lambda c: _jsonable(c.get_ipv6_status()))
    except Exception as e:
        return _unsupported("get_ipv6_status", e)


@mcp.tool()
def get_dhcp_leases() -> dict:
    """DHCPリース一覧。未対応の場合は supported=false。"""
    try:
        return _run(lambda c: {"leases": _jsonable(c.get_ipv4_dhcp_leases())})
    except Exception as e:
        return _unsupported("get_dhcp_leases", e)


@mcp.tool()
def list_reservations() -> dict:
    """DHCPアドレス予約一覧。"""
    try:
        return _run(lambda c: {"reservations": _jsonable(c.get_ipv4_reservations())})
    except Exception as e:
        return _unsupported("list_reservations", e)


@mcp.tool()
def get_mesh_nodes() -> dict:
    """EasyMeshノード一覧。"""
    try:
        return _run(lambda c: {"nodes": _jsonable(c.get_mesh_nodes())})
    except Exception as e:
        return _unsupported("get_mesh_nodes", e)


@mcp.tool()
def get_wifi(band: str = "5g", reveal_secrets: bool = False) -> dict:
    """指定バンドのWi-Fi設定。band: 2g/5g/6g/guest_2g/... 秘密値は既定マスク。

    例: get_wifi(band="5g"), get_wifi(band="guest_2g", reveal_secrets=True)
    """
    key = band.lower()
    if key not in BAND_MAP:
        return {"supported": False, "error": f"unknown band: {band}", "valid": sorted(BAND_MAP)}
    conn = BAND_MAP[key]
    try:

        def _fn(client):
            return _redact_wifi(_jsonable(client.get_wifi(conn)), reveal_secrets)

        return _run(_fn)
    except Exception as e:
        return _unsupported("get_wifi", e)


@mcp.tool()
def session_info() -> dict:
    """接続設定の安全サマリ (パスワードは出さない)。"""
    return load_config().safe_summary()


@mcp.tool()
def list_endpoints() -> dict:
    """本MCPのツールカタログ。"""
    return {"endpoints": ENDPOINT_CATALOG}


@mcp.tool()
def add_reservation(
    macaddr: str, ipaddr: str, comment: str = "", enable: bool = True, confirm: bool = False
) -> dict:
    """DHCP予約追加。書き換えのため confirm=true が必須。

    例: add_reservation(macaddr="AA:BB:CC:DD:EE:FF", ipaddr="192.168.0.50", confirm=True)
    """
    if not confirm:
        return {"ok": False, "error": "confirm=true が必要です (安全ゲート)"}
    if not _valid_mac(macaddr):
        return {"ok": False, "error": f"invalid macaddr: {macaddr}"}
    if not _valid_ipv4(ipaddr):
        return {"ok": False, "error": f"invalid ipaddr: {ipaddr}"}

    def _fn(client):
        client.add_ipv4_reservation(macaddr, ipaddr, comment, enable)
        return {"ok": True, "macaddr": macaddr, "ipaddr": ipaddr}

    try:
        return _run(_fn)
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


@mcp.tool()
def delete_reservation(macaddr: str, confirm: bool = False) -> dict:
    """DHCP予約削除。confirm=true が必須。"""
    if not confirm:
        return {"ok": False, "error": "confirm=true が必要です (安全ゲート)"}
    if not _valid_mac(macaddr):
        return {"ok": False, "error": f"invalid macaddr: {macaddr}"}

    def _fn(client):
        client.delete_ipv4_reservation(macaddr)
        return {"ok": True, "macaddr": macaddr}

    try:
        return _run(_fn)
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


@mcp.tool()
def set_wifi(band: str, enable: bool, confirm: bool = False) -> dict:
    """Wi-Fi ON/OFF。無線再起動を伴うため confirm=true が必須。

    例: set_wifi(band="guest_2g", enable=True, confirm=True)
    """
    if not confirm:
        return {"ok": False, "error": "confirm=true が必要です (安全ゲート)"}
    key = band.lower()
    if key not in BAND_MAP:
        return {"ok": False, "error": f"unknown band: {band}", "valid": sorted(BAND_MAP)}
    conn = BAND_MAP[key]

    def _fn(client):
        client.set_wifi(conn, enable)
        return {"ok": True, "band": band, "enable": enable}

    try:
        return _run(_fn)
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


@mcp.tool()
def reboot_router(confirm: bool = False) -> dict:
    """ルータ再起動。confirm=true が必須。"""
    if not confirm:
        return {"ok": False, "error": "confirm=true が必要です (安全ゲート)"}

    def _fn(client):
        client.reboot()
        return {"ok": True}

    try:
        return _run(_fn)
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


@mcp.tool()
def raw_request(path: str, data: str = "", operation: str = "read", confirm: bool = False) -> dict:
    """任意エンドポイント読取。

    - path例: "admin/nat?form=vs", "admin/upnp?form=service"
    - data例: "operation=load" 等。operation指定時は data に operation= が無ければ自動付与
    - 戻り値の秘密値は常にマスク (reveal不可)
    - operation が read/load 以外の場合は書き込みとみなし confirm=true が必須
    """

    op = (operation or "read").lower()
    if op not in ("read", "load") and not confirm:
        return {"ok": False, "error": "confirm=true が必要です (安全ゲート)"}

    def _fn(client):
        req = getattr(client, "request", None)
        if req is None:
            return {"supported": False, "error": "this client has no request()"}
        body = data
        if op and "operation=" not in body:
            body = f"operation={op}" + (f"&{body}" if body else "")
        try:
            res = req(path, body)
        except TypeError:
            res = req(path, data)
        j = _redact_recursive(_jsonable(res))
        if isinstance(j, str):
            try:
                return _redact_recursive(json.loads(j))
            except ValueError:
                return {"raw": j[:8000]}
        return j if isinstance(j, dict) else {"result": j}

    try:
        return _run(_fn)
    except Exception as e:
        return {"supported": False, "error": f"{type(e).__name__}: {e}"}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
