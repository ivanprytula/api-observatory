# Database operations. Use these explicitly; destructive/reset operations are
# intentionally not part of the default local startup flow.

# Open an explicit local service database; cloud access uses native psql with a
# separately supplied DATABASE_URL so this helper cannot target cloud hosts.
db-psql service:
    #!/usr/bin/env bash
    set -euo pipefail
    case "{{service}}" in
        ingestor) docker compose exec ingestor-db psql -U postgres -d api_obs_ingestor ;;
        inference) docker compose exec inference-db psql -U postgres -d api_obs_inference ;;
        *)
            echo "Choose a local database: just db-psql ingestor|inference" >&2
            exit 2
            ;;
    esac
