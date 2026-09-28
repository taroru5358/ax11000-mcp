import pytest

from tplink_router_mcp.config import RouterConfig, load_config


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


def test_load_config_env_vars(monkeypatch, isolated_env):
    monkeypatch.setenv("ROUTER_IP", "192.168.0.1")
    monkeypatch.setenv("ROUTER_PASSWORD", "pw123")
    cfg = load_config()
    assert cfg.base_url() == "http://192.168.0.1"
    assert cfg.password == "pw123"


def test_load_config_missing_password(isolated_env):
    with pytest.raises(ValueError, match="password"):
        load_config()


def _write_user_env(home, text, name="tplink-router-mcp"):
    d = home / ".config" / name
    d.mkdir(parents=True)
    (d / ".env").write_text(text)


def test_repo_env_is_read(isolated_env):
    home, _work, repo = isolated_env
    _write_user_env(home, "ROUTER_PASSWORD=user-pw\n")
    (repo / ".env").write_text("ROUTER_IP=10.0.0.1\nROUTER_PASSWORD=repo-pw\n")
    cfg = load_config()
    assert cfg.base_url() == "http://10.0.0.1"
    assert cfg.password == "repo-pw"


def test_cwd_env_is_not_read(isolated_env):
    home, work, _repo = isolated_env
    _write_user_env(home, "ROUTER_PASSWORD=pw\n")
    (work / ".env").write_text("ROUTER_HOST=http://attacker.example\n")
    assert load_config().base_url() == "http://192.168.0.1"


def test_repo_env_path_points_to_checkout_root():
    from tplink_router_mcp.config import _repo_env_path

    path = _repo_env_path()
    assert path is not None
    assert (path.parent / "pyproject.toml").is_file()
    assert (path.parent / "src" / "tplink_router_mcp").is_dir()


def test_explicit_timeout_wins_over_env(monkeypatch, isolated_env):
    monkeypatch.setenv("ROUTER_PASSWORD", "pw")
    monkeypatch.setenv("ROUTER_TIMEOUT", "30")
    assert load_config(timeout=5).timeout == 5
    assert load_config().timeout == 30


@pytest.mark.parametrize("raw", ["0", "-3"])
def test_timeout_has_lower_bound(monkeypatch, isolated_env, raw):
    monkeypatch.setenv("ROUTER_PASSWORD", "pw")
    monkeypatch.setenv("ROUTER_TIMEOUT", raw)
    assert load_config().timeout == 1


def test_tplink_env_file_overrides_repo_env(monkeypatch, isolated_env, tmp_path):
    _home, _work, repo = isolated_env
    (repo / ".env").write_text("ROUTER_IP=10.0.0.1\nROUTER_PASSWORD=repo-pw\n")
    other = tmp_path / "router2.env"
    other.write_text("ROUTER_IP=10.0.0.2\nROUTER_PASSWORD=router2-pw\n")
    monkeypatch.setenv("TPLINK_ENV", str(other))
    cfg = load_config()
    assert cfg.base_url() == "http://10.0.0.2"
    assert cfg.password == "router2-pw"


@pytest.mark.parametrize("key", ["AX11000_PASSWORD", "TPLINK_PASSWORD"])
def test_legacy_aliases_are_ignored(monkeypatch, isolated_env, key):
    monkeypatch.setenv(key, "legacy-pw")
    with pytest.raises(ValueError, match="password"):
        load_config()


def test_legacy_user_config_dir_is_ignored(isolated_env):
    home, _work, _repo = isolated_env
    _write_user_env(home, "ROUTER_PASSWORD=legacy-pw\n", name="ax11000-mcp")
    with pytest.raises(ValueError, match="password"):
        load_config()
