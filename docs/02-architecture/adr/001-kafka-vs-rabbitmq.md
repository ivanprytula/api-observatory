# ADR 001: Message Broker — Kafka vs RabbitMQ

Track: C — Architecture and Platform Strategy


**Status**: Accepted
**Date**: April 18, 2026
**Part of**: [Architecture — Data Zoo Platform](../architecture.md)
**Related ADRs**: [ADR 002: Qdrant vs pgvector](002-qdrant-vs-pgvector.md) | [ADR 003: HTMX vs React](../../adr/003-htmx-vs-react.md)
**Context**: Data Zoo platform needs reliable event streaming across multiple services (ingestor → processor → inference → analytics).

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

**Chosen: Redpanda**

1. **Learning Value**: Kafka is the industry standard for event streaming at scale. Redpanda's Kafka API means you learn transferable skills.
2. **Local Development**: No Zookeeper = simpler Docker Compose = faster iteration.
3. **Production Parity**: When you deploy to cloud (Phase 7), you can use AWS MSK (Kafka-compatible API) — zero code changes.
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

**Phase 1**: Producer & consumer in `app/events.py` and `services/processor/main.py`

```python
from aiokafka import AIOKafkaProducer, AIOKafkaConsumer
# Works on Redpanda locally; same code works on AWS MSK in production
```

---

## Alternatives Reconsidered

If RabbitMQ was chosen instead:

- Would teach AMQP (less transferable to big data platforms)
- Would require learning separate mental models for queues vs streams
- Cloud deployment would require rewriting (AWS has no RabbitMQ equivalent)

→ **Rejected**: Kafka/Redpanda is the better choice for a distributed systems learning platform.
