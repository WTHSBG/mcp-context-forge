# MCP Credential Pool Gateways

ContextForge supports storing multiple upstream authentication header sets on a
single MCP gateway. Runtime calls rotate through the available credentials and
temporarily cool down a credential when the upstream response looks like auth,
rate-limit, or quota exhaustion.

## Auth Value Shape

Use `auth_type: "authheaders"` and store a `credential_pool` inside
`auth_value`:

```json
{
  "auth_type": "authheaders",
  "auth_value": {
    "credential_pool": [
      {
        "id": "key-1",
        "headers": {
          "Authorization": "Bearer <token-1>"
        }
      },
      {
        "id": "key-2",
        "headers": {
          "Authorization": "Bearer <token-2>"
        }
      }
    ]
  }
}
```

The `id` is only used for logs and in-memory cooldown state. Do not put secrets
in `id`.

## Build From MCP Config Files

For MCP config files shaped like:

```json
{
  "mcpServers": {
    "server-name": {
      "url": "https://example.com/mcp",
      "headers": {
        "Authorization": "Bearer <token>"
      }
    }
  }
}
```

generate ContextForge gateway payloads with:

```bash
python3 scripts/build_mcp_credential_pool.py key-file-1.json key-file-2.json \
  --output /tmp/gateways.json
```

The output contains one gateway payload per MCP server name, with all input
credentials grouped under that gateway. Keep generated files with real keys out
of git.

## Run With Docker

For the shortest local path, build and start this fork with:

```bash
docker compose -f docker-compose.quickstart.yml up -d --build
```

Then open `http://localhost:4444/admin` and register the generated gateway
payloads. See `docs/docker-quickstart-credential-pool.md` for the full flow.

## Runtime Behavior

- Normal MCP tool calls round-robin credentials per gateway.
- If a credential produces a 401, 403, 429, or quota/rate-limit-like error text,
  ContextForge cools that credential down for the current worker and retries the
  next credential.
- Gateway registration and refresh try credential variants in order, so one
  exhausted key does not prevent discovery when another key still works.
- The state is in-memory and best-effort; restarting the process clears cooldowns.
