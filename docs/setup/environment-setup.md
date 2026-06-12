# Environment Setup

Track: B - Engineering Execution

This document defines environment variable policy for local development, CI, and deployment.

## Scope

- Source of truth for environment precedence
- Required variables for local startup
- Separation rules for local values vs secrets

For package/tool prerequisites, use [docs/setup/system-requirements.md](system-requirements.md).
For bootstrap flow, use [docs/02-first-time-setup.md](../02-first-time-setup.md).
For command execution, use [docs/dev/commands.md](../dev/commands.md).

## Environment Precedence

Highest to lowest:

1. Explicit shell exports for current command/session
2. CI or deployment-injected environment variables
3. Local `.env` values
4. Application defaults

Policy: local `.env` must never override CI or deployment values.

## Local URL Mode

Local API clients and browser docs should use the shared URL helper instead of hardcoded `127.0.0.1:8000` values:

```bash
source scripts/daily/local-url.sh
curl_local -sf "$(local_api_url /health)"
local_open_url /api/docs
```

| Variable | Default | Purpose |
|---|---|---|
| `LOCAL_API_SCHEME` | `http` | Choose direct HTTP or edge HTTPS for local API clients. |
| `LOCAL_API_BASE_URL` | computed | Override ingestor API base URL. |
| `LOCAL_DASHBOARD_URL` | computed | Override dashboard URL for smoke tests and docs. |
| `LOCAL_TLS_VERIFY` | `true` | Set to `false` to pass `-k` for local HTTPS curl calls. |

See [docs/setup/local-url-matrix.md](local-url-matrix.md) for the full local URL matrix.

## Required Local Variables

- `DATABASE_URL`
- `ENVIRONMENT` (default: `development`)
- `LOG_LEVEL` (default: `DEBUG`)

Optional feature flags and integrations can remain disabled locally unless needed.

## Local Development Rules

- `.env` is local-only and must remain uncommitted.
- Start from `.env.example` and customize only needed values.
- Keep secrets out of markdown, source files, and committed scripts.

## CI and Deployment Rules

- Do not rely on `.env` in CI or runtime containers.
- Inject secrets from the platform secret store.
- Keep secret scope environment-specific where possible.

## Validation Checks

```bash
# ensure file exists locally
ls -la .env

# verify a required key exists
grep DATABASE_URL .env

# run standard health checks
just doctor
```

## Troubleshooting

### Missing environment variable at runtime

1. Confirm variable name and scope.
2. Confirm injector source (shell export, CI secret, or platform secret manager).
3. Re-run `just doctor` and the relevant startup command.

### Local tests cannot connect to database

1. Verify local service stack is running.
2. Verify `DATABASE_URL` in `.env`.
3. Re-run focused test command from [docs/dev/commands.md](../dev/commands.md).

## Related Documents

- [docs/setup/system-requirements.md](system-requirements.md)
- [docs/02-first-time-setup.md](../02-first-time-setup.md)
- [docs/dev/commands.md](../dev/commands.md)
- [docs/03-daily-development.md](../03-daily-development.md)
