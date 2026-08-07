# Disposable local Kubernetes lab. Import this file from just/labs.just.

_lab-k8s-cluster-create:
    #!/usr/bin/env bash
    set -euo pipefail
    project_root="{{justfile_directory()}}/.."
    if ! k3d cluster list | awk 'NR > 1 {print $1}' | grep -qx "api-obs"; then
        k3d cluster create --config "${project_root}/infra/kubernetes/k3d.yaml" --kubeconfig-update-default --kubeconfig-switch-context=false
    fi

_lab-k8s-build:
    #!/usr/bin/env bash
    set -euo pipefail
    cd "{{justfile_directory()}}/.."
    registry="localhost:5000/api-obs"
    docker build -t "${registry}/ingestor:local" .
    docker build -t "${registry}/dashboard:local" -f services/dashboard/Dockerfile .
    docker build -t "${registry}/ingestor-db:local" infra/database

_lab-k8s-push-images:
    #!/usr/bin/env bash
    set -euo pipefail
    registry="localhost:5000/api-obs"
    docker push "${registry}/ingestor:local"
    docker push "${registry}/dashboard:local"
    docker push "${registry}/ingestor-db:local"

_lab-k8s-bootstrap:
    #!/usr/bin/env bash
    set -euo pipefail
    overlay="{{justfile_directory()}}/../infra/kubernetes/overlays/local"
    context="k3d-api-obs"
    kubectl --context "${context}" apply -f "${overlay}/namespace.yaml"
    kubectl --context "${context}" -n api-obs apply -f "${overlay}/service-account.yaml"
    kubectl --context "${context}" -n api-obs apply -f "${overlay}/config.yaml"
    kubectl --context "${context}" -n api-obs apply -f "${overlay}/secret.yaml"
    kubectl --context "${context}" -n api-obs apply -f "${overlay}/postgres-init-configmap.yaml"
    kubectl --context "${context}" -n api-obs apply -f "${overlay}/ingestor-db-deployment.yaml"
    kubectl --context "${context}" -n api-obs apply -f "${overlay}/ingestor-db-service.yaml"
    kubectl --context "${context}" -n api-obs rollout status deployment/ingestor-db --timeout=120s

_lab-k8s-migrate:
    #!/usr/bin/env bash
    set -euo pipefail
    overlay="{{justfile_directory()}}/../infra/kubernetes/overlays/local"
    context="k3d-api-obs"
    kubectl --context "${context}" -n api-obs delete job/ingestor-migrate --ignore-not-found
    kubectl --context "${context}" apply -f "${overlay}/migrate-job.yaml"
    kubectl --context "${context}" -n api-obs wait --for=condition=complete job/ingestor-migrate --timeout=120s

_lab-k8s-deploy:
    #!/usr/bin/env bash
    set -euo pipefail
    context="k3d-api-obs"
    restart_apps=false
    if kubectl --context "${context}" -n api-obs get deployment/ingestor >/dev/null 2>&1; then
        restart_apps=true
    fi
    kubectl --context "${context}" apply -k "{{justfile_directory()}}/../infra/kubernetes/overlays/local"
    if [[ "${restart_apps}" == true ]]; then
        kubectl --context "${context}" -n api-obs rollout restart deployment/ingestor deployment/dashboard
    fi
    kubectl --context "${context}" -n api-obs rollout status deployment/ingestor --timeout=120s
    kubectl --context "${context}" -n api-obs rollout status deployment/dashboard --timeout=120s

# Build, publish, migrate, and deploy the disposable local stack.
lab-k8s-up: _lab-k8s-cluster-create _lab-k8s-build _lab-k8s-push-images _lab-k8s-bootstrap _lab-k8s-migrate _lab-k8s-deploy
    @kubectl --context k3d-api-obs -n api-obs get pods,deployments,services,ingress -o wide

lab-k8s-down:
    k3d cluster delete api-obs

lab-k8s-status:
    @kubectl --context k3d-api-obs -n api-obs get pods,deployments,services,ingress -o wide

lab-k8s-logs service="ingestor":
    kubectl --context k3d-api-obs -n api-obs logs "deployment/{{service}}" --tail=50 -f

lab-k8s-port-forward service="ingestor" local_port="8000" remote_port="8000":
    kubectl --context k3d-api-obs -n api-obs port-forward "deployment/{{service}}" {{local_port}}:{{remote_port}}
