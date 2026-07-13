#!/usr/bin/env bash
# Azure environment helper.
# Behavior:
# - If mode is `emulator`, export Azurite-compatible credentials for floci-az.
# - If mode is `login`, verify az CLI login and export subscription.
# - Otherwise, auto-detect based on AZURE_ENDPOINT_URL.

set -euo pipefail

_is_sourced() {
	(return 0 2>/dev/null)
}

_done() {
	if _is_sourced; then
		return "$1" 2>/dev/null || true
	else
		exit "$1"
	fi
}

usage() {
	cat <<'USAGE' >&2
Usage: source scripts/azure-env.sh [mode]

Modes:
    emulator|floci-az   Export emulator credentials (AZURE_ENDPOINT_URL defaults to http://127.0.0.1:4577)
    login               Verify az CLI login and export AZURE_SUBSCRIPTION_ID
    (no args)           Auto-detect: prefer emulator endpoint, then az CLI
USAGE
	_done 1
}

AZURITE_ACCOUNT="devstoreaccount1"
AZURITE_KEY="Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw=="

MODE=${1:-}
if [[ -n "$MODE" && ("$MODE" == "-h" || "$MODE" == "--help") ]]; then
	usage
fi

case "$MODE" in
	emulator|floci-az)
		export AZURE_ENDPOINT_URL=${AZURE_ENDPOINT_URL:-http://127.0.0.1:4577}
		export AZURE_STORAGE_ACCOUNT="$AZURITE_ACCOUNT"
		export AZURE_STORAGE_KEY="$AZURITE_KEY"
		export AZURE_STORAGE_CONNECTION_STRING="DefaultEndpointsProtocol=http;AccountName=${AZURITE_ACCOUNT};AccountKey=${AZURITE_KEY};BlobEndpoint=${AZURE_ENDPOINT_URL}/${AZURITE_ACCOUNT};QueueEndpoint=${AZURE_ENDPOINT_URL}/${AZURITE_ACCOUNT}"
		echo "Set emulator creds for floci-az (${AZURE_ENDPOINT_URL})" >&2
		_done 0
		;;

	login)
		if ! command -v az &>/dev/null; then
			echo "ERROR: Azure CLI not found. Install: https://aka.ms/installazurecli" >&2
			_done 1
		fi
		if ! az account show > /dev/null 2>&1; then
			echo "ERROR: Not logged in. Run: az login" >&2
			_done 1
		fi
		export AZURE_SUBSCRIPTION_ID=$(az account show --query id -o tsv)
		echo "Azure subscription: $(az account show --query name -o tsv) (${AZURE_SUBSCRIPTION_ID})" >&2
		_done 0
		;;

	"")
		if [[ -n "${AZURE_ENDPOINT_URL:-}" && "${AZURE_ENDPOINT_URL}" =~ ^http://127\.0\.0\.1 ]]; then
			export AZURE_STORAGE_ACCOUNT="$AZURITE_ACCOUNT"
			export AZURE_STORAGE_KEY="$AZURITE_KEY"
			export AZURE_STORAGE_CONNECTION_STRING="DefaultEndpointsProtocol=http;AccountName=${AZURITE_ACCOUNT};AccountKey=${AZURITE_KEY};BlobEndpoint=${AZURE_ENDPOINT_URL}/${AZURITE_ACCOUNT};QueueEndpoint=${AZURE_ENDPOINT_URL}/${AZURITE_ACCOUNT}"
			echo "Auto-detected emulator endpoint; exported Azurite creds" >&2
			_done 0
		fi

		if command -v az &>/dev/null && az account show > /dev/null 2>&1; then
			export AZURE_SUBSCRIPTION_ID=$(az account show --query id -o tsv)
			echo "Using Azure CLI login: $(az account show --query name -o tsv)" >&2
			_done 0
		fi

		echo "No AZURE_ENDPOINT_URL or az CLI login detected; set up credentials first." >&2
		_done 0
		;;

	*)
		echo "Unknown mode: $MODE" >&2
		usage
		;;
esac
