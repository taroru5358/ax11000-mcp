"""セキュリティゲートの単体テスト (実機アクセスなし)."""

from urllib.parse import parse_qsl

import pytest

from tplink_router_mcp.server import (
    REDACTED,
    _redact_recursive,
    _valid_mac,
    add_reservation,
    delete_reservation,
    get_firmware,
    get_wifi,
    raw_request,
    reboot_router,
    set_wifi,
)


def _sent_params(client) -> dict:
    ((_name, (_path, body)),) = [c for c in client.calls if c[0] == "request"]
    return dict(parse_qsl(body))


# --- raw_request の confirm ゲート -------------------------------------------


def test_raw_request_write_requires_confirm(fake_client):
    res = raw_request("admin/nat?form=dmz", "", "write")
    assert res["ok"] is False
    assert "confirm" in res["error"]
    assert not fake_client.calls


def test_raw_request_read_passes_gate(fake_client):
    res = raw_request("admin/nat?form=setting", "", "read")
    assert "confirm" not in str(res)
    assert _sent_params(fake_client) == {"operation": "read"}


@pytest.mark.parametrize(
    ("path", "data", "operation"),
    [
        ("admin/nat?form=dmz", "operation=write&enable=on", ""),
        ("admin/nat?form=dmz", "enable=on&operation=WRITE", ""),
        ("admin/nat?form=dmz&operation=write", "enable=on", ""),
    ],
)
def test_raw_request_write_hidden_in_data_or_path_requires_confirm(
    fake_client, path, data, operation
):
    res = raw_request(path, data, operation)
    assert res["ok"] is False
    assert not fake_client.calls


def test_raw_request_operation_in_data_with_default_args(fake_client):
    # operation 引数を省略し data 側で指定した場合、矛盾扱いにせず confirm ゲートで判定する
    res = raw_request("admin/nat?form=dmz", "operation=write")
    assert res["ok"] is False
    assert "confirm" in res["error"]
    assert not fake_client.calls

    res = raw_request("admin/nat?form=dmz", "operation=write", confirm=True)
    assert "error" not in res
    assert _sent_params(fake_client)["operation"] == "write"


def test_raw_request_defaults_to_read(fake_client):
    raw_request("admin/status?form=all")
    assert _sent_params(fake_client) == {"operation": "read"}


def test_raw_request_conflicting_operations_rejected(fake_client):
    res = raw_request("admin/nat?form=dmz", "operation=load", "write", confirm=True)
    assert res["ok"] is False
    assert "矛盾" in res["error"]
    assert not fake_client.calls


def test_raw_request_keeps_extra_params(fake_client):
    raw_request("admin/x", "form=a&name=b%20c", "load")
    assert _sent_params(fake_client) == {"form": "a", "name": "b c", "operation": "load"}


def test_raw_request_masks_json_and_text(fake_client):
    fake_client.response = {"data": {"psk_key": "wifi-pass", "ssid": "home"}}
    res = raw_request("admin/wireless?form=wireless_5g")
    assert res["data"]["psk_key"] == REDACTED
    assert res["data"]["ssid"] == "home"

    fake_client.calls.clear()
    fake_client.response = "ssid=home&psk_key=wifi-pass&password: hunter2"
    res = raw_request("admin/x")
    assert "wifi-pass" not in res["raw"]
    assert "hunter2" not in res["raw"]
    assert "ssid=home" in res["raw"]


# --- エラーメッセージのマスク -------------------------------------------------


def test_error_masks_password_and_session(fake_client):
    fake_client.error = RuntimeError(
        "HTTPConnectionPool: /cgi-bin/luci/;stok=abcdef123/admin/x "
        "cookies={'sysauth': 'deadbeef'} pw-secret"
    )
    res = raw_request("admin/x")
    for leaked in ("abcdef123", "deadbeef", "pw-secret"):
        assert leaked not in res["error"]


# --- マスクの一律適用 ---------------------------------------------------------


def test_redact_recursive_masks_nested_secrets():
    data = {
        "wireless": {"psk_key": "secret123", "ssid": "mywifi", "wep_key1": "abc"},
        "auth": {"token": "abc", "stok": "xyz"},
        "reservations": [{"key": "1", "mac": "AA:BB:CC:DD:EE:FF"}],
    }
    out = _redact_recursive(data)
    assert out["wireless"]["psk_key"] == REDACTED
    assert out["wireless"]["wep_key1"] == REDACTED
    assert out["wireless"]["ssid"] == "mywifi"
    assert out["auth"]["token"] == REDACTED
    assert out["auth"]["stok"] == REDACTED
    assert out["reservations"][0]["key"] == "1"


def test_all_read_tools_redacted(fake_client):
    fake_client.response = {"pppoe_password": "isp-pass", "version": "1.0"}
    res = get_firmware()
    assert res["pppoe_password"] == REDACTED
    assert res["version"] == "1.0"


def test_get_wifi_masks_by_default_and_reveals_on_request(fake_client):
    fake_client.response = {"psk_key": "wifi-pass", "ssid": "home"}
    assert get_wifi("5g")["psk_key"] == REDACTED
    assert get_wifi("5g", reveal_secrets=True)["psk_key"] == "wifi-pass"


def test_get_wifi_unknown_band(fake_client):
    res = get_wifi("7g")
    assert res["supported"] is False
    assert not fake_client.calls


# --- 書き込み系の confirm ゲートと入力検証 -------------------------------------


@pytest.mark.parametrize(
    "call",
    [
        lambda: set_wifi("5g", False),
        lambda: reboot_router(),
        lambda: add_reservation("AA:BB:CC:DD:EE:FF", "192.168.0.50"),
        lambda: delete_reservation("AA:BB:CC:DD:EE:FF"),
    ],
)
def test_write_tools_require_confirm(fake_client, call):
    res = call()
    assert res["ok"] is False
    assert "confirm" in res["error"]
    assert not fake_client.calls


def test_set_wifi_and_reboot_with_confirm(fake_client):
    assert set_wifi("guest_2g", True, confirm=True)["ok"] is True
    assert reboot_router(confirm=True)["ok"] is True
    names = [c[0] for c in fake_client.calls]
    assert "set_wifi" in names and "reboot" in names
    assert names.count("logout") == 2


def test_set_wifi_unknown_band():
    res = set_wifi("7g", True, confirm=True)
    assert res["ok"] is False


def test_add_reservation_validates_input():
    bad_mac = add_reservation("not-a-mac", "192.168.0.50", confirm=True)
    assert bad_mac["ok"] is False
    assert "macaddr" in bad_mac["error"]
    bad_ip = add_reservation("AA:BB:CC:DD:EE:FF", "999.1.1.1", confirm=True)
    assert bad_ip["ok"] is False
    assert "ipaddr" in bad_ip["error"]
    long_comment = add_reservation("AA:BB:CC:DD:EE:FF", "192.168.0.50", "x" * 33, confirm=True)
    assert long_comment["ok"] is False
    assert "comment" in long_comment["error"]


@pytest.mark.parametrize(
    ("mac", "ok"),
    [
        ("AA:BB:CC:DD:EE:FF", True),
        ("aa-bb-cc-dd-ee-ff", True),
        ("AA:BB-CC:DD-EE:FF", False),
        ("AABBCCDDEEFF", False),
    ],
)
def test_valid_mac(mac, ok):
    assert _valid_mac(mac) is ok


def test_delete_reservation_validates_mac():
    res = delete_reservation("xx", confirm=True)
    assert res["ok"] is False
    assert "macaddr" in res["error"]


def test_jsonable_strips_private_field_prefix():
    from dataclasses import dataclass

    from tplink_router_mcp.server import _jsonable

    @dataclass
    class S:
        _wan_ipv4_ipaddr: str = "1.2.3.4"
        remote: bool = False

    assert _jsonable(S()) == {"wan_ipv4_ipaddr": "1.2.3.4", "remote": False}
