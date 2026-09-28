# tplink-router-mcp

English | [日本語](README.ja.md)

An MCP server for TP-Link routers, meant to be launched over stdio from Claude Code or other MCP clients.
It talks to the router's web API directly via `tplinkrouterc6u` (no Playwright needed).
Development and hardware testing are done on an Archer AX11000 V1, but other TP-Link routers work too (see "Supported routers" below).

Checked on hardware: `GET http://192.168.0.1/` → `/webpages/index.html` (gaming theme, `tpEncrypt.js` family).

## Supported routers

Router communication is handled by [tplinkrouterc6u](https://github.com/AlexandrErohin/TP-Link-Archer-C6U).
`TplinkRouterProvider.get_client` detects the model when connecting, so no per-model configuration is needed.
Any model supported by that library (Archer AX / BE / C / MR / VR series, Deco, MERCUSYS, and 100+ others) should basically work with this MCP server.
For the full list, see ["Supported routers" in the tplinkrouterc6u README](https://github.com/AlexandrErohin/TP-Link-Archer-C6U#supports).

The available tools do depend on the model (i.e. which client implementation the library uses internally). The table below reflects what was confirmed from the tplinkrouterc6u 5.35.0 source.

| Tool | Coverage |
|---|---|
| `router_overview`, `list_devices`, `get_firmware`, `get_ipv4_status`, `set_wifi`, `reboot_router` | Almost all models |
| `get_dhcp_leases`, `list_reservations` | Some models, such as the Archer AX/C series |
| `raw_request` | Some models, such as the Archer AX/C series and Deco |
| `get_mesh_nodes` | Archer AX/C series (EasyMesh capable), Deco |
| `get_wifi`, `add_reservation`, `delete_reservation` | Archer AX/C series (C6U-family client) only |

- Calling a tool on an unsupported model does not crash the server; it returns `supported: false` or an error message
- Some Wi-Fi bands do not exist on every model (e.g. 6 GHz is only on Wi-Fi 6E / 7 models)
- The second 5 GHz band (`wireless_5g_2`) on tri-band models (such as the AX11000) is not supported by tplinkrouterc6u, so `get_wifi` / `set_wifi` cannot handle it. You can read it with `raw_request(path="admin/wireless?form=wireless_5g_2")`
- Only the Archer AX11000 V1 has been tested on real hardware. Reports from other models are welcome via Issues
- The default router address is `192.168.0.1`. If your router uses a different IP (e.g. `192.168.1.1`), set `ROUTER_IP`

## Setup

```bash
cd /path/to/tplink-router-mcp  # the cloned directory
uv sync --group dev
```

Credentials are stored in a file. The simplest way is to put a `.env` in the root of the cloned repository (`.env` is already in `.gitignore`).

```bash
cp .env.example .env
# Edit: set ROUTER_PASSWORD to the web admin Local Password (a TP-Link ID does not work)
```

Variables: `ROUTER_IP` (default 192.168.0.1), `ROUTER_USERNAME` (default admin), `ROUTER_PASSWORD` (required), `ROUTER_TIMEOUT` (seconds, minimum 1)

Sources and precedence (low → high):

1. `~/.config/tplink-router-mcp/.env` (if you want to keep it outside the repository)
2. `.env` in the repository root
3. The file pointed to by `$TPLINK_ENV` (e.g. to switch between multiple routers)
4. Environment variables

The repository `.env` is located relative to this repository, not the current directory at startup.
Whatever project Claude Code is opened in, that project's `.env` will never be read by mistake.
If you install it as a package (e.g. with `uvx`), there is no repository, so only 1, 3 and 4 are used.

## Checking that it starts

```bash
uv run pytest -q
uv run ruff check . && uv run ruff format --check .
ROUTER_PASSWORD=dummy uv run tplink-router-mcp --help || echo "stdio server (no --help is expected)"
```

## Registering with Claude Code

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

Credentials are read from `.env`, so `env` can stay empty.
Only if you want to hard-code the password, add `"env": {"ROUTER_PASSWORD": "..."}`.

## Tools

Read: `router_overview`, `list_devices`, `get_firmware`, `get_ipv4_status`, `get_ipv6_status`,
`get_dhcp_leases`, `list_reservations`, `get_mesh_nodes`, `get_wifi`, `session_info`, `list_endpoints`

Write (confirm required): `add_reservation`, `delete_reservation`, `set_wifi`, `reboot_router`

Generic: `raw_request(path, data, operation)` — for syslog, detailed wireless settings, guest network and other model-specific endpoints.
Example: `raw_request(path="status?form=client_status", operation="read")`
Secrets in the response are always masked. Any operation other than `read`/`load` is treated as a write and requires `confirm=true`.
The operation is checked wherever it is specified: the `operation` argument, `data`, or the query string of `path`. Conflicting values are rejected.

Notes:
- The router allows only one session at a time. Each tool does authorize → run → logout
- All tool results and error messages mask secrets (password / PSK / stok / sysauth, etc.). Only Wi-Fi secrets can be revealed, with `get_wifi(reveal_secrets=true)`
- The `add_reservation` comment is limited to 32 characters. MAC addresses must use a single separator consistently, either `:` or `-`
- Use the Local Password (a TP-Link ID does not work). For HTTPS, enable Local Management via HTTPS on the router
- The default connection is plain HTTP (intended for use within the LAN). Set `ROUTER_IP` to `https://...` to connect over HTTPS

## Operational notes (Claude Code permissions)

`confirm=true` is an argument the LLM sets itself, so it helps prevent mistakes but is not a substitute for human approval.
If instructions are smuggled into web pages or repository text the LLM reads, or into host names announced by devices on the LAN (shown in `list_devices` results), i.e. prompt injection, the LLM may follow them and call write tools.

Do not put the following tools in `permissions.allow`; approve each call instead.

- Write tools: `add_reservation`, `delete_reservation`, `set_wifi`, `reboot_router`
- Tools that can reveal secrets / hit arbitrary endpoints: `get_wifi`, `raw_request`

Example that auto-allows only read tools:

```json
{
  "permissions": {
    "allow": [
      "mcp__tplink-router__router_overview",
      "mcp__tplink-router__list_devices",
      "mcp__tplink-router__get_firmware",
      "mcp__tplink-router__session_info",
      "mcp__tplink-router__list_endpoints"
    ]
  }
}
```
