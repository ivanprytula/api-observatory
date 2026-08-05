# Database operations. Use these explicitly; destructive/reset operations are
# intentionally not part of the default local startup flow.

# Open an explicit local service database; cloud access uses native psql with a
# separately supplied DATABASE_URL so this helper cannot target cloud hosts.
db-psql service query="":
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -z "{{query}}" ]]; then
        echo "Usage: just db-psql <service> <query>" >&2
        exit 1
    fi
    case "{{service}}" in
        ingestor) docker compose exec ingestor-db psql -U postgres -d api_obs_ingestor -c "{{query}}" ;;
        inference) docker compose exec inference-db psql -U postgres -d api_obs_inference -c "{{query}}" ;;
        *)
            echo "Choose a local database: just db-psql ingestor|inference <query>" >&2
            exit 2
            ;;
    esac
