#!/bin/bash
# Azure Free Tier provisioning for API Observatory MVP.
# Uses free-tier services only: B1s VM, PostgreSQL Flexible Server B1ms, existing ACR.
# Expected cost: $0/month (within free tier limits).
set -euo pipefail

trap 'fail "Script failed at line $LINENO (exit code $?)"' ERR

RG="api-observatory-rg"
LOCATION="polandcentral"
FALLBACK_LOCATIONS="westeurope northeurope uksouth"
VM_NAME="api-observatory-vm"
ADMIN_USER="azureuser"
PG_SERVER="api-observatory-pg"
PG_DB="api_observatory"
PG_ADMIN="pgadmin"
# Reuse ACR from audience-insights (already provisioned, Standard tier free for 31 days)
ACR_NAME="audienceinsightsacr"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✓${NC} $1"; }
warn() { echo -e "${YELLOW}⚠${NC} $1"; }
fail() { echo -e "${RED}✗${NC} $1"; exit 1; }
sep()  { echo "────────────────────────────────────────"; }

command -v az &>/dev/null || fail "Azure CLI not found. Install: https://aka.ms/installazurecli"
az account show &>/dev/null || fail "Not logged in. Run: az login"

SUB_ID=$(az account show --query id -o tsv)
SUB_NAME=$(az account show --query name -o tsv)
ok "Azure CLI — $SUB_NAME (subscription: $SUB_ID)"

# ─── Resource Group ───
sep
echo "  Location: $LOCATION | Fallbacks: $FALLBACK_LOCATIONS"
az group create --name "$RG" --location "$LOCATION" --output none
ok "Resource group: $RG ($LOCATION)"

# ─── Register resource providers ───
sep
for NS in "Microsoft.DBforPostgreSQL" "Microsoft.Compute"; do
    STATE=$(az provider show --namespace "$NS" --query registrationState -o tsv 2>/dev/null || echo "NotRegistered")
    if [[ "$STATE" != "Registered" ]]; then
        warn "Registering $NS (current state: $STATE)..."
        az provider register --namespace "$NS" --output none
    fi
done
ok "Resource providers registered"

# ─── VM (B1s free tier — 750 hrs/month) ───
sep
if az vm show --name "$VM_NAME" --resource-group "$RG" &>/dev/null; then
    ok "VM already exists: $VM_NAME"
else
    CREATED=false
    for LOC in $LOCATION $FALLBACK_LOCATIONS; do
        for SIZE in "Standard_B1s" "Standard_B2ats_v2" "Standard_B2pts_v2"; do
            echo "  Attempting: SKU=$SIZE  Location=$LOC"
            VM_ERR=$(mktemp)
            if az vm create \
                --resource-group "$RG" --name "$VM_NAME" \
                --image "Canonical:ubuntu-24_04-lts:server:latest" --size "$SIZE" --location "$LOC" \
                --admin-username "$ADMIN_USER" --generate-ssh-keys \
                --os-disk-size-gb 30 --os-disk-delete-option Delete \
                --output none 2>"$VM_ERR"; then
                ok "VM created: $SIZE ($LOC)"
                CREATED=true
                rm -f "$VM_ERR"
                break 2
            fi
            ERR_MSG=$(cat "$VM_ERR")
            rm -f "$VM_ERR"
            if echo "$ERR_MSG" | grep -qi "AllocationFailed\|SkuNotAvailable\|OverConstrained\|ZonalAllocationFailed"; then
                warn "$SIZE in $LOC — capacity unavailable, trying next..."
            else
                warn "$SIZE in $LOC failed: ${ERR_MSG:0:200}"
            fi
            # Clean up partial resources from failed attempt before trying next location
            az vm delete --name "$VM_NAME" --resource-group "$RG" --yes --no-wait --output none 2>/dev/null || true
        done
    done
    $CREATED || fail "No VM SKU available in any region. Tried: $LOCATION $FALLBACK_LOCATIONS"
fi

for PORT_RULE in "22:1000" "80:1001" "443:1002"; do
    PORT="${PORT_RULE%%:*}"
    PRIO="${PORT_RULE##*:}"
    az vm open-port --resource-group "$RG" --name "$VM_NAME" --port "$PORT" --priority "$PRIO" --output none 2>/dev/null || true
done
ok "Ports 22, 80, 443 opened"

VM_IP=""
echo "  Looking up public IP for $VM_NAME..."
for PIP_NAME in "${VM_NAME}PublicIP" "${VM_NAME}-pip" "$(az network public-ip list --resource-group "$RG" --query "[0].name" -o tsv 2>/dev/null)"; do
    if [[ -n "$PIP_NAME" ]]; then
        VM_IP=$(az network public-ip show --resource-group "$RG" --name "$PIP_NAME" --query ipAddress -o tsv 2>/dev/null) || true
        [[ -n "$VM_IP" ]] && break
    fi
done
[[ -z "$VM_IP" ]] && fail "Could not get VM public IP (tried: ${VM_NAME}PublicIP, ${VM_NAME}-pip, first in list)"
ok "VM public IP: $VM_IP"

# ─── PostgreSQL Flexible Server (B1ms free tier — 750 hrs/month, 32 GB storage) ───
sep
PG_PASS=$(python3 -c "import secrets; print(secrets.token_urlsafe(24) + 'Pg1!')" 2>/dev/null)

if az postgres flexible-server show --name "$PG_SERVER" --resource-group "$RG" &>/dev/null; then
    ok "PostgreSQL already exists: $PG_SERVER"
    PG_PASS="<existing — check saved credentials>"
else
    warn "Creating PostgreSQL Flexible Server (2-5 min)..."

    CREATED=false
    for LOC in $LOCATION $FALLBACK_LOCATIONS; do
        echo "  Attempting: SKU=Standard_B1ms  Location=$LOC"
        PG_ERR=$(mktemp)
        if az postgres flexible-server create \
            --name "$PG_SERVER" \
            --resource-group "$RG" \
            --location "$LOC" \
            --admin-user "$PG_ADMIN" \
            --admin-password "$PG_PASS" \
            --sku-name Standard_B1ms \
            --tier Burstable \
            --storage-size 32 \
            --version 16 \
            --public-access 0.0.0.0 \
            --output none 2>"$PG_ERR"; then
            ok "PostgreSQL created: $PG_SERVER ($LOC)"
            CREATED=true
            rm -f "$PG_ERR"
            break
        fi
        ERR_MSG=$(cat "$PG_ERR")
        rm -f "$PG_ERR"
        warn "PostgreSQL failed in $LOC: ${ERR_MSG:0:200}"
    done
    $CREATED || fail "Could not create PostgreSQL in any region. Tried: $LOCATION $FALLBACK_LOCATIONS"

    az postgres flexible-server db create \
        --resource-group "$RG" \
        --server-name "$PG_SERVER" \
        --database-name "$PG_DB" \
        --output none
    ok "Database created: $PG_DB"
fi

PG_HOST="${PG_SERVER}.postgres.database.azure.com"

# Allow VM IP through PostgreSQL firewall
echo "  Adding firewall rule: AllowVM → $VM_IP"
az postgres flexible-server firewall-rule create \
    --resource-group "$RG" \
    --name "$PG_SERVER" \
    --rule-name "AllowVM" \
    --start-ip-address "$VM_IP" \
    --end-ip-address "$VM_IP" \
    --output none 2>/dev/null || true
ok "PostgreSQL firewall: VM IP ($VM_IP) allowed"

# ─── Install Docker on VM ───
sep
echo "  Checking Docker on VM ($VM_NAME)..."
DOCKER_CHECK=$(az vm run-command invoke \
    --resource-group "$RG" --name "$VM_NAME" \
    --command-id RunShellScript \
    --scripts "command -v docker &>/dev/null && echo 'installed' || echo 'missing'" \
    --query "value[0].message" -o tsv 2>/dev/null | tail -1)

if [[ "$DOCKER_CHECK" == *"installed"* ]]; then
    ok "Docker already installed on VM"
else
    warn "Installing Docker on VM (this may take 1-2 min)..."
    az vm run-command invoke \
        --resource-group "$RG" --name "$VM_NAME" \
        --command-id RunShellScript \
        --scripts "curl -fsSL https://get.docker.com | sudo sh && sudo usermod -aG docker $ADMIN_USER && sudo systemctl enable docker" \
        --output none
    ok "Docker installed on VM"
fi

# ─── Create deploy config on VM ───
sep
DATABASE_URL="postgresql+asyncpg://${PG_ADMIN}:${PG_PASS}@${PG_HOST}:5432/${PG_DB}?sslmode=require"
DEPLOY_ENV="/home/$ADMIN_USER/api-observatory.env"

echo "  Writing app config to VM: $DEPLOY_ENV"
az vm run-command invoke \
    --resource-group "$RG" --name "$VM_NAME" \
    --command-id RunShellScript \
    --scripts "mkdir -p /home/$ADMIN_USER/app && cat > $DEPLOY_ENV << 'ENVEOF'
DATABASE_URL=$DATABASE_URL
ENVIRONMENT=production
LOG_LEVEL=info
JWT_SECRET=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
REDIS_URL=redis://localhost:6379/0
ENVEOF
chmod 600 $DEPLOY_ENV" \
    --output none
ok "App config written to VM: $DEPLOY_ENV"

# ─── ACR login on VM ───
sep
ACR_LOGIN=$(az acr show --name "$ACR_NAME" --resource-group "audience-insights-rg" --query "loginServer" -o tsv 2>/dev/null || echo "$ACR_NAME.azurecr.io")
warn "ACR: $ACR_LOGIN (reusing from audience-insights)"
warn "To pull images on VM, run: az acr login --name $ACR_NAME (or configure SP)"

# ─── Summary ───
sep
echo ""
echo "  Resources (all free tier):"
echo "  🖥️  VM:          ssh $ADMIN_USER@$VM_IP (B1s — 750 hrs/month free)"
echo "  🗄️  PostgreSQL:  $PG_HOST (B1ms — 750 hrs/month free, 32 GB)"
echo "  📦 ACR:          $ACR_LOGIN (shared with audience-insights)"
echo ""
echo "  ── Estimated cost: \$0/month (within free tier) ──"
echo ""

# Save connection info
CRED_FILE="$(dirname "$0")/.azure_credentials"
cat > "$CRED_FILE" <<EOF
# API Observatory Azure credentials — do NOT commit this file
VM_IP=$VM_IP
VM_USER=$ADMIN_USER
PG_HOST=$PG_HOST
PG_DB=$PG_DB
PG_ADMIN=$PG_ADMIN
PG_PASS=$PG_PASS
DATABASE_URL=$DATABASE_URL
ACR_LOGIN=$ACR_LOGIN
EOF
chmod 600 "$CRED_FILE"
ok "Credentials saved to: $CRED_FILE"
echo ""
warn "Add infra/scripts/.azure_credentials to .gitignore"
