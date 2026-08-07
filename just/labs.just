# Disposable exercises kept outside the root developer command surface.
# Run one explicitly, for example:
#   just --justfile just/labs.just lab-cloud-up azure
#   just --justfile just/labs.just lab-k8s-up

import 'cloud.just'
import 'kubernetes.just'

# Probe the optional local HTTPS ingress after it has been started separately.
lab-ingress-smoke gateway-url="https://127.0.0.1":
    bash "{{ justfile_directory() }}/../scripts/smoke-test-ingress.sh" "{{ gateway-url }}"

# Run the bounded authenticated observations workload against an already-ready stack.
lab-load base-url="http://127.0.0.1:8000" vus="5" duration="90s":
    #!/usr/bin/env bash
    set -euo pipefail
    : "${BEARER_TOKEN:?Set BEARER_TOKEN to a writer/admin JWT (for example, from just smoke-token).}"
    export BASE_URL="{{ base-url }}"
    export VUS="{{ vus }}"
    export DURATION="{{ duration }}"
    k6 run --vus "${VUS}" --duration "${DURATION}" \
        "{{ justfile_directory() }}/../scripts/load/k6-observations-load.js"

# Stop/restart the local PostgreSQL container and prove the ingestor recovers.
lab-chaos:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "Chaos mutates the running local database; use a disposable core stack."
    cd "{{ justfile_directory() }}/.." && \
        uv run pytest tests/e2e/test_chaos.py -v --no-cov --run-chaos
