# Local Kubernetes lab recipes. Compose remains the canonical onboarding runtime.

k8s-cluster-create:
    k3d cluster create --config infra/kubernetes/k3d.yaml --kubeconfig-update-default --kubeconfig-switch-context
    echo "cluster data-zoo created — context: k3d-data-zoo"

k8s-cluster-delete:
    k3d cluster delete data-zoo

k8s-build:
    docker build -t data-zoo/ingestor:latest .
    docker build -t data-zoo/dashboard:latest -f services/dashboard/Dockerfile .

k8s-load-images:
    k3d image import -c data-zoo data-zoo/ingestor:latest data-zoo/dashboard:latest

k8s-deploy-infra:
    #!/usr/bin/env bash
    set -euo pipefail
    helm repo add --force-update bitnami https://charts.bitnami.com/bitnami
    helm repo add --force-update redpanda https://charts.redpanda.com
    helm repo update
    kubectl create namespace data-zoo --dry-run=client -o yaml | kubectl apply -f -
    for chart in postgresql redis; do
      helm upgrade --install "$chart" "bitnami/$chart" --namespace data-zoo --values "infra/kubernetes/helm-values/${chart}.yaml" --wait
    done
    helm upgrade --install redpanda redpanda/redpanda --namespace data-zoo --values infra/kubernetes/helm-values/redpanda.yaml --wait

k8s-secret:
    kubectl apply -n data-zoo -f infra/kubernetes/overlays/local/secret.example.yaml

k8s-migrate:
    kubectl delete job/ingestor-migrate -n data-zoo --ignore-not-found
    kubectl apply -f infra/kubernetes/overlays/local/migrate-job.yaml
    kubectl -n data-zoo wait --for=condition=complete job/ingestor-migrate --timeout=60s

k8s-deploy:
    kubectl apply -k infra/kubernetes/overlays/local
    kubectl -n data-zoo rollout status deployment/ingestor --timeout=120s
    kubectl -n data-zoo rollout status deployment/dashboard --timeout=120s

k8s-status:
    @kubectl -n data-zoo get pods,deployments,services,ingress -o wide

k8s-logs service="":
    @kubectl -n data-zoo logs "deployment/{{service}}" --tail=50 -f

k8s-port-forward service="" local-port="" remote-port="":
    kubectl -n data-zoo port-forward "deployment/{{service}}" {{local-port}}:{{remote-port}}

k8s-up:
    @just k8s-cluster-create
    @just k8s-build
    @just k8s-load-images
    @just k8s-deploy-infra
    @just k8s-secret
    @just k8s-migrate
    @just k8s-deploy
    @just k8s-status

k8s-down:
    k3d cluster delete data-zoo
