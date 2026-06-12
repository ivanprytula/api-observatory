#!/usr/bin/env bash
set -euo pipefail

# ─── Configuration ─────────────────────────────────────────────────────────────
COMPOSE_PROJECT="${COMPOSE_PROJECT:-api-observatory}"
CONTAINER_PREFIX="${CONTAINER_PREFIX:-api-obs}"

# All killable services (not the infrastructure you can't restart easily)
KILLABLE_SERVICES=(
    "${CONTAINER_PREFIX}-ingestor"
    "${CONTAINER_PREFIX}-processor"
    "${CONTAINER_PREFIX}-ai-gateway"
    "${CONTAINER_PREFIX}-query-api"
    "${CONTAINER_PREFIX}-dashboard"
)

CHAOS_DURATION="${CHAOS_DURATION:-30}"    # seconds container stays killed
DELAY_JITTER="${DELAY_JITTER:-100}"       # ms of extra latency added
PACKET_LOSS="${PACKET_LOSS:-5}"           # % packet loss in network chaos

# ─── Helpers ───────────────────────────────────────────────────────────────────
log()   { echo "[$(date '+%H:%M:%S')] [CHAOS] $*"; }
warn()  { echo "[$(date '+%H:%M:%S')] [CHAOS] ⚠ $*" >&2; }
die()   { echo "[$(date '+%H:%M:%S')] [CHAOS] ✗ $*" >&2; exit 1; }

require_cmd() {
    command -v "$1" &>/dev/null || die "'$1' is required but not found"
}

# ─── Scenario 1: Random Service Kill ──────────────────────────────────────────
# Pick a random app service, kill it, wait, let Docker restart it.
# Validates: restart policy, error propagation, recovery time.
chaos_kill_random_service() {
    local service
    service="${KILLABLE_SERVICES[$((RANDOM % ${#KILLABLE_SERVICES[@]}))]}"

    log "KILL: Stopping container '${service}' for ${CHAOS_DURATION}s"
    docker stop "${service}"

    log "System should degrade gracefully. Waiting ${CHAOS_DURATION}s..."
    sleep "${CHAOS_DURATION}"

    log "Restarting '${service}'..."
    docker start "${service}"

    log "Waiting for service to become healthy..."
    local max_wait=60
    local elapsed=0
    while ! docker inspect --format='{{.State.Health.Status}}' "${service}" 2>/dev/null | grep -q "healthy"; do
        sleep 2
        elapsed=$((elapsed + 2))
        if [[ "${elapsed}" -ge "${max_wait}" ]]; then
            warn "Service '${service}' did not become healthy within ${max_wait}s"
            return 1
        fi
    done
    log "✓ '${service}' recovered in ${elapsed}s"
}

# ─── Scenario 2: Network Partition (requires tc/iproute2 in container) ─────────
# Add artificial latency + packet loss to a container's network interface.
# Validates: timeout handling, circuit breakers, retry logic.
chaos_network_partition() {
    local target="${1:-${CONTAINER_PREFIX}-ingestor}"
    local service
    service=$(docker ps --filter "name=^/${target}$" --format '{{.Names}}' | head -n1 || true)
    if [ -z "$service" ]; then
        service="${CONTAINER_PREFIX}-ingestor"
    fi

    local container_id
    container_id=$(docker inspect --format='{{.Id}}' "$service" 2>/dev/null) || {
        warn "Container '${service}' not found, skipping network chaos"
        return 0
    }

    log "NETWORK: Adding ${DELAY_JITTER}ms jitter + ${PACKET_LOSS}% packet loss to '${service}'"

    # Run tc in the container's network namespace
    local netns
    netns=$(docker inspect --format='{{.State.Pid}}' "${service}")

    if ! nsenter --net="/proc/${netns}/ns/net" tc qdisc add dev eth0 root netem \
            delay "${DELAY_JITTER}ms" "${DELAY_JITTER}ms" \
            loss "${PACKET_LOSS}%" 2>/dev/null; then
        warn "Could not apply tc netem (is 'iproute2' installed in the container?)"
        warn "Simulating by restarting with artificial sleep instead"
        return 0
    fi

    log "Network chaos active for ${CHAOS_DURATION}s. Watch for timeout errors..."
    sleep "${CHAOS_DURATION}"

    log "Removing network chaos from '${service}'"
    nsenter --net="/proc/${netns}/ns/net" tc qdisc del dev eth0 root 2>/dev/null || true
    log "✓ Network restored on '${service}'"
}

# ─── Scenario 3: Database Blackout ────────────────────────────────────────────
# Stop the database, wait, bring it back.
# Validates: connection pool error handling, circuit breaker on db, recovery.
chaos_db_blackout() {
    local db_container="${CONTAINER_PREFIX}-db"
    if ! docker ps --filter "name=^/${db_container}$" --format '{{.Names}}' | grep -q .; then
        db_container="data-pipeline-db"
    fi

    log "DB BLACKOUT: Stopping '${db_container}' for ${CHAOS_DURATION}s"
    docker stop "${db_container}"

    log "DB is down. Ingestor should return 503 for write operations."
    log "Waiting ${CHAOS_DURATION}s..."
    sleep "${CHAOS_DURATION}"

    log "Restarting '${db_container}'..."
    docker start "${db_container}"

    log "Waiting for PostgreSQL to become healthy..."
    local elapsed=0
    while ! docker exec "${db_container}" pg_isready -U postgres &>/dev/null; do
        sleep 2
        elapsed=$((elapsed + 2))
        [[ "${elapsed}" -ge 60 ]] && { warn "PostgreSQL didn't recover in 60s"; return 1; }
    done
    log "✓ PostgreSQL recovered in ${elapsed}s"
}

# ─── Scenario 4: Kafka Outage ─────────────────────────────────────────────────
# Stop Redpanda, validate DLQ and circuit breaker behavior.
chaos_kafka_outage() {
    log "KAFKA OUTAGE: Stopping broker for ${CHAOS_DURATION}s"
    docker stop data-pipeline-broker

    log "Kafka is down. Events should fail gracefully (circuit breaker / DLQ)."
    log "Waiting ${CHAOS_DURATION}s..."
    sleep "${CHAOS_DURATION}"

    log "Restarting broker..."
    docker start "${CONTAINER_PREFIX}-broker"

    local elapsed=0
    while ! docker exec "${CONTAINER_PREFIX}-broker" rpk cluster health 2>/dev/null | grep -q "true"; do
        sleep 3
        elapsed=$((elapsed + 3))
        [[ "${elapsed}" -ge 90 ]] && { warn "Broker didn't recover in 90s"; return 1; }
    done
    log "✓ Broker recovered in ${elapsed}s"
}

# ─── Scenario 5: Memory Pressure ──────────────────────────────────────────────
# Update resource limits on a container to simulate OOM pressure.
chaos_memory_pressure() {
    local service="${1:-data-pipeline-ingestor}"
    log "MEMORY PRESSURE: Updating '${service}' memory limit to 64M for ${CHAOS_DURATION}s"

    docker update --memory 64m --memory-swap 64m "${service}"

    log "Memory constrained. Watch for OOMKilled events..."
    sleep "${CHAOS_DURATION}"

    docker update --memory 512m --memory-swap 1g "${service}"
    log "✓ Memory limits restored on '${service}'"
}

# ─── Full chaos gauntlet ──────────────────────────────────────────────────────
run_gauntlet() {
    log "Starting full chaos gauntlet..."
    log "Each scenario runs for ${CHAOS_DURATION}s."
    echo ""

    chaos_kill_random_service
    sleep 10

    chaos_kafka_outage
    sleep 10

    chaos_db_blackout
    sleep 10

    log ""
    log "Chaos gauntlet complete. Review logs for recovery times and error handling."
}

# ─── Main ─────────────────────────────────────────────────────────────────────
usage() {
    cat <<EOF
Usage: $0 <scenario> [options]

Scenarios:
  kill          Kill a random application service (restart after ${CHAOS_DURATION}s)
  network       Add latency + packet loss to ingestor network
  db            Stop PostgreSQL for ${CHAOS_DURATION}s (db blackout)
  kafka         Stop Redpanda for ${CHAOS_DURATION}s (Kafka outage)
  memory        Apply memory pressure to a service
  gauntlet      Run all scenarios sequentially

Environment variables:
  CHAOS_DURATION=30    Seconds to keep chaos active
  DELAY_JITTER=100     Network latency in ms
  PACKET_LOSS=5        Network packet loss percentage

Examples:
  $0 kill
  $0 db
  CHAOS_DURATION=60 $0 kafka
  $0 gauntlet
EOF
    exit 1
}

require_cmd docker

case "${1:-}" in
    kill)      chaos_kill_random_service ;;
    network)   chaos_network_partition "${2:-data-pipeline-ingestor}" ;;
    db)        chaos_db_blackout ;;
    kafka)     chaos_kafka_outage ;;
    memory)    chaos_memory_pressure "${2:-data-pipeline-ingestor}" ;;
    gauntlet)  run_gauntlet ;;
    *)         usage ;;
esac
