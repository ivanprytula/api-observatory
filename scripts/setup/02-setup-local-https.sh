#!/usr/bin/env bash
set -euo pipefail

# ─── Configuration ─────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
CERT_DIR="${PROJECT_ROOT}/infra/certs"

# ─── Colors ───────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# ─── Helpers ───────────────────────────────────────────────────────────────────
log() { echo -e "${GREEN}✓${NC} $*"; }
warn() { echo -e "${YELLOW}⚠${NC} $*"; }
error() { echo -e "${RED}✗${NC} $*" >&2; }

# ─── Main ──────────────────────────────────────────────────────────────────────
main() {
    echo ""
    echo "════════════════════════════════════════════════════════════════════════════"
    echo "Local HTTPS Certificate Setup"
    echo "════════════════════════════════════════════════════════════════════════════"
    echo ""

    # Check if mkcert is installed
    if ! command -v mkcert &>/dev/null; then
        error "mkcert not found. Install it first:"
        echo ""
        echo "  macOS:              brew install mkcert"
        echo "  Ubuntu/Debian:      sudo apt-get install mkcert"
        echo "  Fedora/RHEL:        sudo dnf install mkcert"
        echo "  Windows (Choco):    choco install mkcert"
        echo ""
        exit 1
    fi

    log "mkcert found"

    # Check if certificates already exist
    if [[ -f "${CERT_DIR}/localhost+2.pem" && -f "${CERT_DIR}/localhost+2-key.pem" ]]; then
        warn "Certificates already exist:"
        echo "  ${CERT_DIR}/localhost+2.pem"
        echo "  ${CERT_DIR}/localhost+2-key.pem"
        echo ""
        read -r -p "Regenerate? (y/n) " -n 1 response
        echo ""
        if [[ "$response" != "y" && "$response" != "Y" ]]; then
            echo "Using existing certificates."
            exit 0
        fi
        rm -f "${CERT_DIR}/localhost+2.pem" "${CERT_DIR}/localhost+2-key.pem"
        log "Removed old certificates"
    fi

    # Create cert directory
    mkdir -p "${CERT_DIR}"
    log "Created certificate directory: ${CERT_DIR}"

    # Install local CA (may prompt for sudo password)
    echo ""
    echo "Installing local certificate authority (may require password)..."
    if mkcert -install; then
        log "Local CA installed in system trust store"
    else
        error "Failed to install local CA"
        exit 1
    fi

    # Generate certificates
    echo ""
    echo "Generating certificates for: localhost, 127.0.0.1, *.local"
    if (cd "${CERT_DIR}" && mkcert localhost 127.0.0.1 "*.local"); then
        log "Certificates generated:"
        echo "  - ${CERT_DIR}/localhost+2.pem (public certificate)"
        echo "  - ${CERT_DIR}/localhost+2-key.pem (private key)"
    else
        error "Failed to generate certificates"
        exit 1
    fi

    # Display certificate info
    echo ""
    echo "════════════════════════════════════════════════════════════════════════════"
    echo "Certificate Details"
    echo "════════════════════════════════════════════════════════════════════════════"
    openssl x509 -in "${CERT_DIR}/localhost+2.pem" -noout -text | grep -A 2 "Subject:" | head -3
    openssl x509 -in "${CERT_DIR}/localhost+2.pem" -noout -dates
    echo ""

    # Next steps
    echo "════════════════════════════════════════════════════════════════════════════"
    echo "Next Steps"
    echo "════════════════════════════════════════════════════════════════════════════"
    echo ""
    echo "1. Start services (with HTTPS on :443):"
    echo "     just up-https"
    echo ""
    echo "2. Access via HTTPS:"
    echo "     LOCAL_API_SCHEME=https bash scripts/daily/local-url.sh open /"
    echo "     LOCAL_API_SCHEME=https bash scripts/daily/local-url.sh open /api/docs"
    echo ""
    echo "3. Verify certificate:"
    echo "     curl -v $(LOCAL_API_SCHEME=https bash scripts/daily/local-url.sh api-url /health)"
    echo ""
    echo "Full documentation:"
    echo "     docs/04-setup/local-https-setup.md"
    echo ""
    log "Setup complete!"
}

main "$@"
