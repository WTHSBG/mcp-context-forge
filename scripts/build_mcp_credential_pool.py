#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build ContextForge gateway payloads from multiple MCP server key files.

The script reads one or more JSON files shaped like:

    {"mcpServers": {"name": {"url": "...", "headers": {...}}}}

and emits one gateway payload per MCP server. For each server, headers from all
input files are combined into ``auth_value.credential_pool`` so ContextForge can
round-robin credentials at runtime.
"""

# Standard
import argparse
import json
from pathlib import Path
from typing import Any


def _load(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    servers = data.get("mcpServers")
    if not isinstance(servers, dict):
        raise ValueError(f"{path} does not contain an object field named mcpServers")
    return servers


def build_payloads(paths: list[Path], transport: str, gateway_mode: str) -> list[dict[str, Any]]:
    """Build ContextForge gateway create payloads from MCP key files."""

    grouped: dict[str, dict[str, Any]] = {}
    for path in paths:
        servers = _load(path)
        for server_name, server_config in servers.items():
            if not isinstance(server_config, dict):
                continue
            url = server_config.get("url")
            headers = server_config.get("headers")
            if not isinstance(url, str) or not isinstance(headers, dict):
                continue
            entry = grouped.setdefault(server_name, {"url": url, "credentials": []})
            if entry["url"] != url:
                raise ValueError(f"server {server_name!r} has different URLs across input files")
            entry["credentials"].append(
                {
                    "id": f"{path.stem}-{len(entry['credentials']) + 1}",
                    "headers": {str(k): str(v) for k, v in headers.items() if k and v is not None},
                }
            )

    payloads: list[dict[str, Any]] = []
    for server_name, entry in sorted(grouped.items()):
        credentials = entry["credentials"]
        if not credentials:
            continue
        payloads.append(
            {
                "name": server_name,
                "url": entry["url"],
                "transport": transport,
                "auth_type": "authheaders",
                "auth_value": {"credential_pool": credentials},
                "gateway_mode": gateway_mode,
            }
        )
    return payloads


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", type=Path, help="MCP key JSON files")
    parser.add_argument("--transport", default="STREAMABLEHTTP", choices=["SSE", "STREAMABLEHTTP"], help="Gateway transport to use")
    parser.add_argument("--gateway-mode", default="cache", choices=["cache", "direct_proxy"], help="ContextForge gateway mode")
    parser.add_argument("--output", type=Path, help="Optional output JSON file")
    args = parser.parse_args()

    payloads = build_payloads(args.files, args.transport, args.gateway_mode)
    rendered = json.dumps({"gateways": payloads}, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
