#!/usr/bin/env bash
set -euo pipefail

CLUSTER_NAME="${1:-data-zoo}"
NAMESPACE="${2:-data-zoo}"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

require_cmd docker
require_cmd k3d
require_cmd kubectl

if ! docker info >/dev/null 2>&1; then
  echo "Docker daemon is not running" >&2
  exit 1
fi

if k3d cluster list | awk '{print $1}' | grep -qx "$CLUSTER_NAME"; then
  echo "k3d cluster '$CLUSTER_NAME' already exists"
else
  k3d cluster create "$CLUSTER_NAME" \
    --servers 1 \
    --agents 1 \
    --port "8080:80@loadbalancer" \
    --port "8443:443@loadbalancer" \
    --wait
fi

kubectl cluster-info >/dev/null
kubectl get namespace "$NAMESPACE" >/dev/null 2>&1 || kubectl create namespace "$NAMESPACE"

cat <<EOF
k3d bootstrap complete.
cluster:   $CLUSTER_NAME
namespace: $NAMESPACE

next:
  kubectl config use-context k3d-$CLUSTER_NAME
  kubectl get nodes
EOF
