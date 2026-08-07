# Test recipes. Unit tests need no runtime stack. PostgreSQL integration tests use
# testcontainers when Docker is available; smoke, API, and E2E tests use the local stack.

# Probe the already-ready local core API.
test-smoke base-url="http://127.0.0.1:8000":
    bash "{{justfile_directory()}}/scripts/smoke-test.sh" {{base-url}}

# Create/reuse a local writer/admin account and print its access token for `test-smoke-auth`.
smoke-token base-url="http://127.0.0.1:8000":
    #!/usr/bin/env bash
    set -euo pipefail

    BASE_URL="{{base-url}}"
    USERNAME="${SMOKE_USERNAME:-smoke-writer}"
    ROLE="${SMOKE_ROLE:-writer}"
    PASSWORD="${SMOKE_PASSWORD:-}"

    error() {
        printf '[ERROR] %s\n' "$*" >&2
        exit 1
    }

    case "${ROLE}" in
        writer|admin) ;;
        *) error "SMOKE_ROLE must be writer or admin (got: ${ROLE})" ;;
    esac

    if [[ -z "${PASSWORD}" ]]; then
        read -r -p "Enter password for ${USERNAME}: " PASSWORD
    fi
    [[ "${#PASSWORD}" -ge 8 ]] || error "SMOKE_PASSWORD must be at least 8 characters"

    ROOT_URL="${BASE_URL%/}"
    USER_EMAIL="${USERNAME}@example.com"
    USER_PAYLOAD="$(jq -n --arg username "${USERNAME}" --arg email "${USER_EMAIL}" --arg password "${PASSWORD}" \
        '{username: $username, email: $email, password: $password}')"
    REGISTER_RESPONSE="$(curl -sS -w '\n%{http_code}' -X POST "${ROOT_URL}/api/v1/auth/register" \
        -H 'Content-Type: application/json' --data "${USER_PAYLOAD}" || true)"
    REGISTER_STATUS="${REGISTER_RESPONSE##*$'\n'}"
    REGISTER_BODY="${REGISTER_RESPONSE%$'\n'*}"
    case "${REGISTER_STATUS}" in
        201|409) ;;
        422)
            DETAILS="$(jq -r 'if (.detail | type) == "array" then [.detail[]?.msg] | join("; ") else (.detail // "validation error") end' <<<"${REGISTER_BODY}")"
            error "Registration failed with HTTP 422: ${DETAILS}"
            ;;
        *) error "Registration failed with HTTP ${REGISTER_STATUS}" ;;
    esac

    INTERNAL_TOKEN="$(just --justfile "{{justfile_directory()}}/Justfile" _dev-internal-token local-smoke)"
    ROLE_PAYLOAD="$(jq -n --arg role "${ROLE}" '{role: $role}')"
    ROLE_STATUS="$(curl -sS -o /dev/null -w '%{http_code}' -X POST "${ROOT_URL}/api/v1/auth/users/${USERNAME}/role" \
        -H 'Content-Type: application/json' -H "Authorization: Bearer ${INTERNAL_TOKEN}" \
        --data "${ROLE_PAYLOAD}" || true)"
    [[ "${ROLE_STATUS}" == "200" ]] || error "Role assignment failed with HTTP ${ROLE_STATUS}"

    LOGIN_RESPONSE="$(curl -sS -X POST "${ROOT_URL}/api/v1/auth/token" \
        -H 'Content-Type: application/x-www-form-urlencoded' \
        --data-urlencode "username=${USERNAME}" --data-urlencode "password=${PASSWORD}")" || \
        error "Login failed"
    ACCESS_TOKEN="$(jq -er '.access_token | select(type == "string" and length > 0)' <<<"${LOGIN_RESPONSE}")" || \
        error "Login response did not contain an access token"
    printf '%s\n' "${ACCESS_TOKEN}"

# Set SMOKE_JWT to a writer/admin JWT to include the authenticated write/read path.
test-smoke-auth base-url="http://127.0.0.1:8000":
    #!/usr/bin/env bash
    set -euo pipefail
    : "${SMOKE_JWT:?Set SMOKE_JWT to a writer/admin JWT.}"
    bash "{{justfile_directory()}}/scripts/smoke-test.sh" {{base-url}}

# No containers: isolated tests with optional runtime dependencies installed by uv.
test-unit:
    bash "{{justfile_directory()}}/scripts/test/run-lane.sh" unit

# Requires Docker only; fixtures provision and remove their own temporary dependencies.
test-integration:
    bash "{{justfile_directory()}}/scripts/test/run-lane.sh" integration

# Baseline application and PostgreSQL behavior. Optional runtime capabilities remain off.
test-core:
    bash "{{justfile_directory()}}/scripts/test/run-profile.sh" core

# Requires Docker only; verifies PostgreSQL tenant-isolation behavior in an isolated database.
test-capability-rls:
    bash "{{justfile_directory()}}/scripts/test/run-profile.sh" rls

# Requires Docker only; broker boundaries use deterministic fixtures and test doubles.
test-capability-broker:
    bash "{{justfile_directory()}}/scripts/test/run-profile.sh" broker

# Requires Docker only when selected integration fixtures need PostgreSQL; no AI provider is called.
test-capability-ai:
    bash "{{justfile_directory()}}/scripts/test/run-profile.sh" ai

# Requires Docker only; starts and removes its own deterministic harness, never the local stack.
test-full-optional:
    bash "{{justfile_directory()}}/scripts/test/run-full-optional.sh"

# Requires Docker only when selected fixtures need it; excludes public live probes and labs.
test-e2e:
    bash "{{justfile_directory()}}/scripts/test/run-lane.sh" e2e

# Requires public network access; never a CI gate and no local stack is needed.
test-live-external:
    bash "{{justfile_directory()}}/scripts/test/run-lane.sh" live

# Run manual API collections without resetting or seeding the local database.
test-api:
    cd "{{justfile_directory()}}/bruno" && bru run auth ops sources contracts scorecards websocket -r --env local-dev --env-var "baseUrl=${BRUNO_BASE_URL:-http://127.0.0.1:8000}"
