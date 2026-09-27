"""共通fixture: 実機に触れないモッククライアント."""

from __future__ import annotations

from typing import Any

import pytest

import tplink_router_mcp.server as srv
from tplink_router_mcp import config
from tplink_router_mcp.config import RouterConfig


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self.response: Any = {}
        self.error: Exception | None = None

    def _record(self, name: str, *args: Any) -> Any:
        self.calls.append((name, args))
        if self.error is not None:
            raise self.error
        return self.response

    def authorize(self) -> None:
        self.calls.append(("authorize", ()))

    def logout(self) -> None:
        self.calls.append(("logout", ()))

    def request(self, path: str, data: str) -> Any:
        return self._record("request", path, data)

    def get_wifi(self, conn: Any) -> Any:
        return self._record("get_wifi", conn)

    def get_firmware(self) -> Any:
        return self._record("get_firmware")

    def set_wifi(self, conn: Any, enable: bool) -> Any:
        return self._record("set_wifi", conn, enable)

    def reboot(self) -> Any:
        return self._record("reboot")


@pytest.fixture
def fake_client(monkeypatch) -> FakeClient:
    client = FakeClient()
    cfg = RouterConfig(host="192.168.0.1", username="admin", password="pw-secret")
    monkeypatch.setattr(srv, "_get_client", lambda cfg_=None: (client, cfg))
    return client


@pytest.fixture
def isolated_env(monkeypatch, tmp_path):
    """設定読み込みをホストの環境・HOMEから隔離する."""
    for k in (*config.ENV_KEYS, "TPLINK_ENV"):
        monkeypatch.delenv(k, raising=False)
    home = tmp_path / "home"
    home.mkdir()
    work = tmp_path / "work"
    work.mkdir()
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(work)
    monkeypatch.setattr(config, "_repo_env_path", lambda: repo / ".env")
    return home, work, repo
