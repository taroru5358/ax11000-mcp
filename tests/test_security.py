"""セキュリティゲートの単体テスト (実機アクセスなし)."""

from ax11000_mcp.server import (
    _redact_recursive,
    add_reservation,
    delete_reservation,
    raw_request,
)


def test_raw_request_write_requires_confirm():
    res = raw_request("admin/nat?form=dmz", "", "write")
    assert res["ok"] is False
    assert "confirm" in res["error"]


def test_raw_request_read_needs_no_confirm_gate(monkeypatch):
    # ゲートは通ること (実機に触れないよう _get_client を差し替え)
    import ax11000_mcp.server as srv

    def _fail():
        raise RuntimeError("no-router")

    monkeypatch.setattr(srv, "_get_client", _fail)
    res = raw_request("admin/nat?form=setting", "", "read")
    assert "confirm" not in str(res)


def test_redact_recursive_masks_nested_secrets():
    data = {
        "wireless": {"psk_key": "secret123", "ssid": "mywifi"},
        "auth": {"token": "abc", "stok": "xyz"},
        "reservations": [{"key": "1", "mac": "AA:BB:CC:DD:EE:FF"}],
    }
    out = _redact_recursive(data)
    assert out["wireless"]["psk_key"] == "*** (masked)"
    assert out["wireless"]["ssid"] == "mywifi"
    assert out["auth"]["token"] == "*** (masked)"
    assert out["auth"]["stok"] == "*** (masked)"
    assert out["reservations"][0]["key"] == "1"


def test_add_reservation_validates_input():
    bad_mac = add_reservation("not-a-mac", "192.168.0.50", confirm=True)
    assert bad_mac["ok"] is False
    assert "macaddr" in bad_mac["error"]
    bad_ip = add_reservation("AA:BB:CC:DD:EE:FF", "999.1.1.1", confirm=True)
    assert bad_ip["ok"] is False
    assert "ipaddr" in bad_ip["error"]


def test_delete_reservation_validates_mac():
    res = delete_reservation("xx", confirm=True)
    assert res["ok"] is False
    assert "macaddr" in res["error"]
