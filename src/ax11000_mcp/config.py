"""Config loading for AX11000 MCP.

Precedence (low -> high):
  1. ~/.config/ax11000-mcp/.env
  2. ./.env (project local, cwd)
  3. file pointed by $TPLINK_ENV
  4. real environment variables
  5. explicit args (host/username/password passed to load_config)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values


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


def load_config(
    host: str | None = None,
    username: str | None = None,
    password: str | None = None,
    timeout: int | None = None,
) -> RouterConfig:
    merged: dict[str, str] = {}

    # 1. user config
    merged.update(_read_dotenv_file(Path.home() / ".config" / "ax11000-mcp" / ".env"))
    # 2. project local
    merged.update(_read_dotenv_file(Path.cwd() / ".env"))
    # 3. $TPLINK_ENV (kept for tplinkcli compatibility)
    tplink_env = os.environ.get("TPLINK_ENV") or os.environ.get("AX11000_ENV")
    if tplink_env:
        merged.update(_read_dotenv_file(Path(tplink_env).expanduser()))
    # 4. env vars (both AX11000_* and ROUTER_* / TPLINK_* aliases)
    for key in (
        "ROUTER_IP",
        "ROUTER_HOST",
        "TPLINK_HOST",
        "AX11000_HOST",
        "ROUTER_USERNAME",
        "TPLINK_USERNAME",
        "AX11000_USERNAME",
        "ROUTER_PASSWORD",
        "TPLINK_PASSWORD",
        "AX11000_PASSWORD",
        "ROUTER_TIMEOUT",
        "AX11000_TIMEOUT",
    ):
        if os.environ.get(key):
            merged[key] = os.environ[key]

    def pick(*keys: str, default: str = "") -> str:
        for k in keys:
            if k in merged and merged[k] != "":
                return merged[k]
        return default

    final_host = host or pick(
        "ROUTER_IP", "ROUTER_HOST", "TPLINK_HOST", "AX11000_HOST", default="192.168.0.1"
    )
    final_user = username or pick(
        "ROUTER_USERNAME", "TPLINK_USERNAME", "AX11000_USERNAME", default="admin"
    )
    final_pass = password or pick(
        "ROUTER_PASSWORD", "TPLINK_PASSWORD", "AX11000_PASSWORD", default=""
    )
    timeout_raw = pick("ROUTER_TIMEOUT", "AX11000_TIMEOUT", default=str(timeout or 10))
    try:
        final_timeout = int(timeout_raw)
    except ValueError:
        final_timeout = 10

    if not final_pass:
        raise ValueError(
            "Router password is not set. Set ROUTER_PASSWORD env or "
            "~/.config/ax11000-mcp/.env (see .env.example)."
        )

    return RouterConfig(
        host=final_host, username=final_user, password=final_pass, timeout=final_timeout
    )
