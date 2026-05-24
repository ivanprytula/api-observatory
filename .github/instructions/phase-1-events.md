# Phase 1 — Event Streaming Architecture

**Duration**: 2 weeks
**Goal**: Build real-time event producer/consumer with Redpanda + Celery
**Success Metric**: 10M+ events/day throughput, <100ms latency, zero message loss

---

## Core Learning Objective

Understand event-driven architecture: partitioning, consumer groups, idempotency, failure modes (DLQ, offset management).

---

## Interview Questions

### Core Q: "Design Real-Time ETL for 1000+ Events/Sec"

**Expected Answer:**

- Topic partitioning by entity ID (e.g., source_id) → ensures ordering within entity, parallelism across entities
- Consumer group for scale: multiple consumer instances pull from same group, messages distributed automatically
- Exactly-once semantics: idempotency key in payload, consumer deduplicates on process
- DLQ (dead-letter queue) for poison pills: if processing fails 3×, send to DLQ, alert ops
- Offset commit strategy: commit after processing (at-least-once) vs commit before (at-most-once) → choose based on use case

**Talking Points:**

- Redpanda vs Kafka: Redpanda simpler (single binary, no Zookeeper), 3× faster. Kafka-compatible API.
- Consumer lag: messages behind = lag. High lag = slow consumer (processor overloaded or crashed).
- Rebalancing: when consumer joins/leaves group, Kafka rebalances partitions (brief pause). Minimize rebalancing = stable consumer count.

---

### Follow-Up: "Consumer Lag Monitoring. How Detected and Fixed?"

**Expected Answer:**

- Lag = (latest offset) - (consumer committed offset) per partition
- Monitor via Prometheus `kafka_consumer_lag_sum` or equivalent
- Alert when lag > 100K (or configurable threshold)
- Diagnosis: (1) Check consumer logs for errors, (2) Check processor CPU/memory, (3) Check DLQ size
- Fix: Increase consumer parallelism (add consumer instances) OR optimize processing logic

**Talking Points:**

- Consumer group rebalancing adds 10–30s pause (avoid frequent joins/leaves)
- Sticky partition assignment (rebalance assigns same partitions to same consumer) → faster recovery
- Maximum wait time for rebalance: `session.timeout.ms` (default 10s, tune for slow processing)

---

### Follow-Up: "Your Consumer is 2 Hours Behind. Diagnosis Steps."

**Expected Answer:**

- [ ] Check lag metric: Is it growing or stable?
- [ ] Check processor logs: Error rate? Exception stack?
- [ ] Check DLQ size: Are messages stuck there?
- [ ] Check CPU/memory: Processor memory-starved or CPU throttled?
- [ ] Celery queue: Are tasks enqueued but not processed? Check Celery worker status.
- Fix options: (1) Increase parallelism (add consumers/workers), (2) Optimize processing logic, (3) Restart consumer (offset stays committed)

**Talking Points:**

- Stalled rebalancing: If rebalance took 1h, partitions unassigned. Tune `session.timeout.ms` and `heartbeat.interval.ms`.
- Poison pill handling: If single message causes exception, consumer crashes. DLQ prevents cascading failures.
- Offset reset strategy: `auto.offset.reset=earliest` starts from beginning, `latest` skips backlog → choose per use case

---

## Real life production example — Production-Ready

### Architecture

```text
Record created (POST /api/v1/records)
  ↓
app/main.py: route handler
  ↓
app/events.py: emit_event(RecordCreated)
  ↓
Celery producer: publish to Redpanda topic (records.events)
  ↓
Redpanda: 10 partitions by source_id (ordering per source, scale across sources)
  ↓
services/processor/main.py: async consumer loop
  ↓
[ Process event ] ← idempotency key checks duplicates
  ↓
Update database OR retry Celery task
  ↓
[ERROR] → DLQ (records.events.dlq)
  ↓
alerts/ script monitors DLQ, pages on-call

Monitoring:
  Prometheus: lag_sum, throughput, error_rate
  Grafana: dashboard with lag trend, lag per consumer, DLQ size
```

### Implementation Checklist

- [ ] **Redpanda Instance** (docker-compose.yml)

  ```yaml
  redpanda:
    image: redpandadata/redpanda:latest
    ports:
      - "9092:9092"  # Kafka protocol
    environment:
      REDPANDA_ADVERTISED_KAFKA_API_ADDRESSES: "redpanda:9092"
  ```

- [ ] **app/events.py** — Event emission with retry

  ```python
  from celery_app import app

  @app.task(bind=True, max_retries=3)
  def emit_event(self, event_type: str, payload: dict):
      """Publish event to Redpanda via Kafka protocol."""
      producer = KafkaProducer(
          bootstrap_servers=['redpanda:9092'],
          value_serializer=lambda v: json.dumps(v).encode('utf-8'),
      )
      try:
          producer.send(
              'records.events',
              value={
                  'event_type': event_type,
                  'idempotency_key': payload.get('id'),  # ← Prevents duplicates
                  'payload': payload,
              },
              partition=hash(payload['source_id']) % 10,  # ← Route to partition
          )
      except Exception as exc:
          raise self.retry(exc=exc, countdown=2 ** self.request.retries)  # ← Exponential backoff
  ```

- [ ] **services/processor/main.py** — Consumer + DLQ handling

  ```python
  async def consumer_loop():
      """Consume events, idempotency check, process, or DLQ on error."""
      consumer = KafkaConsumer(
          'records.events',
          bootstrap_servers=['redpanda:9092'],
          group_id='records_processor',
          auto_offset_reset='earliest',
      )

      for msg in consumer:
          event = json.loads(msg.value)
          idempotency_key = event['idempotency_key']

          # Check if already processed
          if await is_idempotent_processed(idempotency_key):
              logger.info(f"Event {idempotency_key} already processed, skipping")
              continue

          try:
              await process_event(event['payload'])
              await mark_idempotent_processed(idempotency_key)
          except Exception as e:
              logger.error(f"Failed processing {idempotency_key}: {e}")
              # Send to DLQ
              dlq_producer.send('records.events.dlq', value=msg.value)
              # Alert
  ```

- [ ] **Monitoring**

  ```python
  # Prometheus metrics
  consumer_lag = Gauge('kafka_consumer_lag_sum', 'Total lag across partitions')
  events_processed = Counter('events_processed_total', 'Total events')
  dlq_size = Gauge('dlq_size', 'Messages in DLQ')

  # Celery task tracking
  emit_event.apply_async(args=(...), countdown=0, retry=True)
  ```

- [ ] **docker-compose.yml** additions

  ```yaml
  services:
    redpanda:
      image: redpandadata/redpanda:latest
      ports: ["9092:9092"]

    processor:
      build: ./services/processor
      depends_on: [redpanda, web]
      environment:
        REDPANDA_BOOTSTRAP_SERVERS: redpanda:9092
  ```

---

## Weekly Checklist (2 weeks)

### Week 1: Setup + Baseline

- [ ] Redpanda + docker-compose running locally
- [ ] app/events.py emits RecordCreated on POST
- [ ] Celery task with exponential backoff (3 retries)
- [ ] Baseline test: emit 100K events, measure throughput (should be >1K events/sec)
- [ ] Interview Q: "Partition strategy?" → hash(source_id) % 10
- [ ] LinkedIn post draft (Week 1 learnings)
- [ ] Commits: 5–8 (setup, producer, retry logic, tests)

### Week 2: Consumer + Monitoring

- [ ] Consumer pulls from records.events, processes
- [ ] Idempotency key + DLQ for poison pills
- [ ] EXPLAIN ANALYZE on idempotency query (should be indexed)
- [ ] Prometheus: consumer_lag, throughput, error_rate
- [ ] Load test: 10M events/day sustained (100 events/sec × 86400 sec)
- [ ] Interview Q: "Consumer lag > 2h. Debug." → Diagnosis steps complete
- [ ] Commit: 5–7 (consumer setup, DLQ, monitoring, load test)
- [ ] Portfolio item drafted
- [ ] LinkedIn post published

---

## Success Metrics

| Metric        | Target         | How to Measure                                                                             |
| ------------- | -------------- | ------------------------------------------------------------------------------------------ |
| Throughput    | 10M events/day | `k6 run scripts/load_test.js --rps 100 --duration 60s` → 6K events/min = 10M/day sustained |
| Latency (p99) | <100ms         | Prometheus histogram `events_processed_duration_seconds` p99 < 0.1s                        |
| Consumer lag  | <10K messages  | Prometheus `kafka_consumer_lag_sum` alert if > 100K                                        |
| DLQ size      | <100 msgs      | Daily ops checklist: if DLQ growing, incident                                              |
| Commit count  | 10–15          | 1 commit per feature + test + monitoring setup                                             |
| Interview Q   | 3/3            | Mock interview: "Design 1000+ events/sec" + 2 follow-ups answered without notes            |

---

## Gotchas + Fixes

### Gotcha 1: "Partition Assignment Not Balanced"

**Symptom**: One partition processes 8M events, another 2M (lag skew).
**Cause**: Sticky partition assignment + consumer crash.
**Fix**: Manual partition assignment or set `partition.assignment.strategy=round_robin` (less sticky, forces rebalance more often but more balanced).

### Gotcha 2: "Messages Appear Out of Order"

**Symptom**: Record created at 10:00, event processed at 10:05, event processed at 10:01 (time-series broken).
**Cause**: Multiple partitions, each ordered but globally out-of-order.
**Fix**: Accepted design (order guaranteed per partition, not globally). If global order needed, use single partition (kills scale).

### Gotcha 3: "Consumer Stops Processing, No Error"

**Symptom**: Lag growing, consumer logs silent.
**Cause**: Poison pill (message causes exception), consumer crashes, group rebalances, new consumer starts, hits same message, crashes again.
**Fix**: DLQ after 3 retries, skip poison pill, continue. Celery task should not crash consumer (exception → task fails → Celery retries, not consumer crash).

### Gotcha 4: "Idempotency Key Check Slow"

**Symptom**: Consumer processing <1K events/sec, CPU idle.
**Cause**: Idempotency table query is seq scan (composite index missing).
**Fix**: Index on (idempotency_key, source_id). Retest: should see throughput jump to 5K+.

---

## Cleanup (End of Phase 1)

```bash
docker-compose down -v  # Remove Redpanda volume
rm -rf logs/processor.log
pytest tests/phase_1/ -v  # Verify integration tests pass
```

---

## Metrics to Monitor Ongoing

- `kafka_consumer_lag_sum`: Alert if > 100K
- `events_processed_total`: Trending (should grow uniformly)
- `celery_task_runtime`: Should be <1s per event (small processing)
- `dlq_size`: Alert if > 100
- Redpanda leader election time: Should be <5s

---

## Next Phase

**Phase 2: Data Scraping with Rate Limiting**
Build async scraper (GraphQL + Playwright) with semaphore-based rate limiting. Consume events from Phase 1 to trigger scrape jobs. Implement retry with exponential backoff for failed scrapes.

**Reference**: Phase 2 decision depends on Phase 1 stability. If consumer lag acceptable and DLQ empty after load test, Phase 2 ready to start.
