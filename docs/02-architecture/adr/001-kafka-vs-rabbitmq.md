# ADR 001: Message Broker — Kafka vs RabbitMQ

Track: C — Architecture and Platform Strategy

**Status**: Accepted
**Date**: April 18, 2026
**Part of**: [API Observatory application architecture](../application-architecture.md)
**Related ADRs**: [ADR 002: Qdrant vs pgvector](002-qdrant-vs-pgvector.md) | [ADR 003: HTMX vs React](../../adr/003-htmx-vs-react.md)
**Context**: API Observatory needs an executable reference for partitioned event delivery,
idempotent publication, consumer state, and replay. Kafka is not required for every request path.

---

## Decision

**Use Redpanda (Kafka-compatible) as the primary message broker.**

---

## Options Considered

### Option A: Redpanda (Kafka-compatible, Zookeeper-free)

- **Pros:**
  - Drop-in Kafka replacement; same `aiokafka` client API
  - No Zookeeper dependency (simpler Docker Compose setup for local dev)
  - Consumer groups, partitioning, topic replication out of the box
  - Web admin UI built-in (port 8082)
  - Fast, written in C++ (good for high throughput)
- **Cons:**
  - Smaller ecosystem than Kafka
  - Less StackOverflow content + community resources

### Option B: Apache Kafka

- **Pros:**
  - Industry standard; mature ecosystem
  - Extensive tooling and community support
  - Strong consistency guarantees
- **Cons:**
  - Zookeeper dependency (complexity)
  - Heavier resource footprint
  - Overkill for local development

### Option C: RabbitMQ

- **Pros:**
  - Simpler setup (no Zookeeper, no cluster complexity)
  - AMQP protocol well-documented
  - Lower resource usage
- **Cons:**
  - Different programming model (queues vs topics vs partitions)
  - Consumer groups less natural than Kafka
  - Doesn't teach distributed systems concepts as well

---

## Rationale

Chosen: Redpanda

1. **Learning Value**: Kafka is the industry standard for event streaming at scale. Redpanda's Kafka API means you learn transferable skills.
2. **Local Development**: No Zookeeper = simpler Docker Compose = faster iteration.
3. **Portability**: A managed Kafka-compatible broker remains possible if measured traffic later
   justifies it; no managed broker has been deployed or selected as a current requirement.
4. **Partitioning & Scaling**: Built-in support for partitioning by `source_id` teaches distributed systems concepts naturally.

---

## Consequences

### Positive

- Single `docker compose up` spins up entire platform locally
- `aiokafka` library works unchanged on both Redpanda and AWS MSK
- Consumer groups teach eventual consistency and acknowledgment semantics
- Partitioning teaches sharding and load distribution

### Negative

- Smaller community than Kafka (but active and growing)
- Some advanced Kafka tools (Confluent Control Center) not available

---

## Implementation

**Phase 1**: Add Redpanda service to `docker-compose.yml`

```yaml
broker:
  image: docker.broker.com/redpandadata/redpanda:latest
  ports:
    - "9092:9092"  # Kafka API
    - "8082:8082"  # Admin UI
  environment:
    - REDPANDA_ADVERTISED_KAFKA_API_ADDRESSES=broker:9092
```

Current producer, idempotency, and delivery evidence lives in
`services/ingestor/events.py`, `services/ingestor/repositories/messaging.py`, and the
outbox/inbox integration tests. There is no standalone processor service.

```python
from aiokafka import AIOKafkaProducer, AIOKafkaConsumer
# Works against the local Kafka-compatible Redpanda broker.
```

---

## Alternatives Reconsidered

If RabbitMQ was chosen instead:

- Would teach AMQP (less transferable to big data platforms)
- Would require learning separate mental models for queues vs streams
- A future managed-broker choice would require an explicit security, cost, and operations ADR.

→ **Rejected**: Kafka/Redpanda is the better choice for a distributed systems learning platform.
