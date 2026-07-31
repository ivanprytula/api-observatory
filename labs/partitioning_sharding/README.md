# Partitioning and Sharding Lab

**Status: Lab.** This deterministic model demonstrates key-to-partition routing, consumer
assignment, hotspots, resharding movement, and cross-shard query fan-out. It does not run a sharded
database and must not be presented as one.

Run the deterministic model without containers:

```bash
uv run python labs/partitioning_sharding/partition_demo.py
uv run pytest tests/unit/test_evergreen_labs.py -q
```

Run the isolated real Kafka-protocol experiment:

```bash
docker compose -f labs/partitioning_sharding/compose.yaml up -d
uv run python labs/partitioning_sharding/kafka_partition_demo.py
docker compose -f labs/partitioning_sharding/compose.yaml down
```

The script creates a temporary topic, proves that each stable key stays on one partition, starts a
consumer group, reports partition assignment and records per consumer, and deletes its topic.

Use `--hot-tenant-events` to show why a stable key can preserve ordering yet create a hotspot. Change
`--partitions` and `--consumers` independently: extra consumers beyond partitions are idle, while
adding partitions changes routing and can move many keys with simple modulo hashing.

## Concepts to Defend

- **Kafka partitioning:** distributes an ordered log by key; it is not database sharding.
- **PostgreSQL table partitioning:** splits one logical table inside one database authority and can
  improve pruning/lifecycle operations; joins and transactions remain local.
- **Cross-node sharding:** routes records to independent database nodes, introducing shard-key,
  hotspot, resharding, cross-shard query, transaction, backup, and consistency decisions.

API Observatory keeps cross-node PostgreSQL sharding **Deferred** until measured single-node limits
remain after indexing, query tuning, retention, table partitioning, vertical capacity, and replicas.
At 10x, tune those simpler controls. At 100x, evaluate tenant/source keys using real distribution and
query evidence before designing routing and rebalancing.
