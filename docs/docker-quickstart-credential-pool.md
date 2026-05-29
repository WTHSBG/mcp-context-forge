# Docker Quickstart for Credential Pool Gateways

This fork can run as a single Docker Compose service for local evaluation and
small private deployments. The image is built from the current source tree, so
it includes the credential pool routing changes.

## Start

```bash
docker compose -f docker-compose.quickstart.yml up -d --build
```

Open the Admin UI:

```text
http://localhost:4444/admin
```

Default local credentials:

```text
admin@example.com / ChangeMe123!
```

Check health:

```bash
curl http://localhost:4444/health
```

Data is stored in the Docker volume `contextforge_data`.

## Register Multi-Key MCP Gateways

Given multiple MCP config files with the same `mcpServers` shape:

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

Build ContextForge gateway payloads:

```bash
python3 scripts/build_mcp_credential_pool.py key-file-1.json key-file-2.json \
  --output /tmp/credential-pool-gateways.json
```

Create an admin token from the running container:

```bash
TOKEN=$(docker compose -f docker-compose.quickstart.yml exec -T gateway sh -lc \
  'python3 -m mcpgateway.utils.create_jwt_token --username "$PLATFORM_ADMIN_EMAIL" --exp 10080 --secret "$JWT_SECRET_KEY"')
```

Register the generated gateways:

```bash
jq -c '.gateways[]' /tmp/credential-pool-gateways.json | while read payload; do
  curl -sS -X POST http://localhost:4444/gateways \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "$payload"
  echo
done
```

Gateway registration may call the upstream MCP server to discover tools. If the
upstream provider charges quota for discovery, run this only when you are ready.

## Production Notes

For production, override at least these values:

```bash
export PLATFORM_ADMIN_PASSWORD='...'
export JWT_SECRET_KEY='...32+ bytes...'
export AUTH_ENCRYPTION_SECRET='...32+ bytes...'
docker compose -f docker-compose.quickstart.yml up -d --build
```

For higher traffic or multi-user deployments, prefer the full stack:

```bash
docker compose -f docker-compose.yml -f docker-compose.override.lite.yml up -d --build
```

The full stack adds Postgres, Redis, and Nginx. The credential pool feature works
in both deployment modes.
