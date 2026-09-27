"""Config loading for TP-Link router MCP.

Precedence (low -> high):
  1. ~/.config/tplink-router-mcp/.env (legacy ~/.config/ax11000-mcp/.env is read first)
  2. <repo root>/.env (source checkout only; independent of cwd)
  3. file pointed by $TPLINK_ENV
  4. real environment variables
  5. explicit args (host/username/password passed to load_config)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values

# 旧名 (ax11000-mcp) の設定ディレクトリも互換のため読む。後ろほど優先
USER_CONFIG_DIRS = ("ax11000-mcp", "tplink-router-mcp")

ENV_KEYS = (
    "ROUTER_IP",
    "ROUTER_HOST",
    "ROUTER_USERNAME",
    "ROUTER_PASSWORD",
    "ROUTER_TIMEOUT",
)


@dataclass(frozen=True)
class RouterConfig:
    host: str
    username: str
    password: str
    timeout: int = 10

    def base_url(self) -> str:
        h = self.host.strip()
        if h.startswith(("http://", "https://")):
            return h.rstrip("/")
        return f"http://{h.rstrip('/')}"

    def safe_summary(self) -> dict:
        return {
            "host": self.base_url(),
            "username": self.username,
            "timeout": self.timeout,
            "password_set": bool(self.password),
        }


def _read_dotenv_file(path: Path) -> dict[str, str]:
    try:
        if path.is_file():
            return {k: v for k, v in dotenv_values(path).items() if v is not None}
    except OSError:
        pass
    return {}


def _repo_env_path() -> Path | None:
    """Return <repo root>/.env when running from a source checkout (uv sync / editable).

    Resolved from this file rather than cwd, so launching the server from another
    project never picks up that project's .env. Returns None for wheel installs.
    """
    root = Path(__file__).resolve().parents[2]
    if (root / "pyproject.toml").is_file():
        return root / ".env"
    return None


def load_config(
    host: str | None = None,
    username: str | None = None,
    password: str | None = None,
    timeout: int | None = None,
) -> RouterConfig:
    merged: dict[str, str] = {}

    # 1. user config (legacy dir from the ax11000-mcp era first, new dir wins)
    for name in USER_CONFIG_DIRS:
        merged.update(_read_dotenv_file(Path.home() / ".config" / name / ".env"))
    # 2. repo local (next to pyproject.toml, not cwd)
    repo_env = _repo_env_path()
    if repo_env is not None:
        merged.update(_read_dotenv_file(repo_env))
    # 3. $TPLINK_ENV (switch between .env files, e.g. for multiple routers)
    tplink_env = os.environ.get("TPLINK_ENV")
    if tplink_env:
        merged.update(_read_dotenv_file(Path(tplink_env).expanduser()))
    # 4. env vars
    for key in ENV_KEYS:
        if os.environ.get(key):
            merged[key] = os.environ[key]

    def pick(*keys: str, default: str = "") -> str:
        for k in keys:
            if k in merged and merged[k] != "":
                return merged[k]
        return default

    final_host = host or pick("ROUTER_IP", "ROUTER_HOST", default="192.168.0.1")
    final_user = username or pick("ROUTER_USERNAME", default="admin")
    final_pass = password or pick("ROUTER_PASSWORD", default="")
    if timeout is not None:
        final_timeout = timeout
    else:
        try:
            final_timeout = int(pick("ROUTER_TIMEOUT", default="10"))
        except ValueError:
            final_timeout = 10
    final_timeout = max(1, final_timeout)

    if not final_pass:
        raise ValueError(
            "Router password is not set. Set ROUTER_PASSWORD env or "
            "~/.config/tplink-router-mcp/.env (see .env.example)."
        )

    return RouterConfig(
        host=final_host, username=final_user, password=final_pass, timeout=final_timeout
    )
