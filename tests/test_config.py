import pytest

from ax11000_mcp.config import RouterConfig, load_config


def test_base_url():
    assert (
        RouterConfig(host="192.168.0.1", username="admin", password="x").base_url()
        == "http://192.168.0.1"
    )
    assert (
        RouterConfig(host="http://192.168.0.1/", username="a", password="x").base_url()
        == "http://192.168.0.1"
    )


def test_safe_summary_hides_password():
    s = RouterConfig(host="192.168.0.1", username="admin", password="secret").safe_summary()
    assert s["password_set"] is True
    assert "secret" not in str(s)


def test_load_config_env_vars(monkeypatch, tmp_path):
    monkeypatch.delenv("ROUTER_PASSWORD", raising=False)
    monkeypatch.delenv("TPLINK_PASSWORD", raising=False)
    monkeypatch.delenv("AX11000_PASSWORD", raising=False)
    monkeypatch.delenv("TPLINK_ENV", raising=False)
    monkeypatch.delenv("AX11000_ENV", raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ROUTER_IP", "192.168.0.1")
    monkeypatch.setenv("ROUTER_PASSWORD", "pw123")
    cfg = load_config()
    assert cfg.base_url() == "http://192.168.0.1"
    assert cfg.password == "pw123"


def test_load_config_missing_password(monkeypatch, tmp_path):
    for k in (
        "ROUTER_PASSWORD",
        "TPLINK_PASSWORD",
        "AX11000_PASSWORD",
        "TPLINK_ENV",
        "AX11000_ENV",
    ):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.chdir(tmp_path)
    # ensure no user config interferes: point HOME to empty tmp
    monkeypatch.setenv("HOME", str(tmp_path))
    with pytest.raises(ValueError, match="password"):
        load_config()
