# Disposable AWS-emulator lab. Run through `just --justfile just/labs.just`.
# These commands manage only the emulator; they never start the application,
# run migrations, seed data, launch host processes, or access real cloud accounts.

# Start the AWS emulator and wait for its Compose healthcheck.
lab-aws-up:
    #!/usr/bin/env bash
    set -euo pipefail
    docker compose --profile aws up --detach --no-deps --wait \
        --wait-timeout "${AWS_EMULATOR_WAIT_TIMEOUT_SECONDS:-60}" floci-aws
    printf '%s\n' 'AWS emulator ready.'

# Stop and remove the AWS emulator without affecting the application stack.
lab-aws-down:
    #!/usr/bin/env bash
    set -euo pipefail
    docker compose --profile aws rm --stop --force floci-aws
    printf '%s\n' 'AWS emulator stopped.'

# Check the AWS emulator's HTTP health endpoint.
lab-aws-verify:
    #!/usr/bin/env bash
    set -euo pipefail
    endpoint="http://127.0.0.1:4566"
    curl --fail --silent --show-error --connect-timeout 2 --max-time 5 \
        "${endpoint}/health" >/dev/null
    printf 'AWS emulator healthy: %s\n' "${endpoint}"
