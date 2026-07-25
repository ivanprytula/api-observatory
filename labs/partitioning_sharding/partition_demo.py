"""Deterministic model of partition routing, consumer assignment, and resharding."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from dataclasses import asdict, dataclass


def partition_for(key: str, partition_count: int) -> int:
    if partition_count < 1:
        raise ValueError("partition_count must be positive")
    digest = hashlib.sha256(key.encode()).digest()
    return int.from_bytes(digest[:8], "big") % partition_count


def consumer_assignment(partition_count: int, consumer_count: int) -> dict[int, int]:
    if consumer_count < 1:
        raise ValueError("consumer_count must be positive")
    return {
        partition: partition % consumer_count for partition in range(partition_count)
    }


@dataclass(frozen=True)
class Analysis:
    partition_load: dict[int, int]
    consumer_load: dict[int, int]
    hottest_partition: int
    hottest_share: float
    keys_moved_when_doubled: int
    cross_shard_query_fanout: int


def analyze(keys: list[str], partition_count: int, consumer_count: int) -> Analysis:
    partitions = [partition_for(key, partition_count) for key in keys]
    partition_load = Counter(partitions)
    assignment = consumer_assignment(partition_count, consumer_count)
    consumer_load = Counter(assignment[partition] for partition in partitions)
    hottest_partition, hottest_count = partition_load.most_common(1)[0]
    moved = sum(
        partition_for(key, partition_count) != partition_for(key, partition_count * 2)
        for key in keys
    )
    return Analysis(
        partition_load=dict(sorted(partition_load.items())),
        consumer_load=dict(sorted(consumer_load.items())),
        hottest_partition=hottest_partition,
        hottest_share=round(hottest_count / len(keys), 4),
        keys_moved_when_doubled=moved,
        cross_shard_query_fanout=len(set(partitions)),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--partitions", type=int, default=6)
    parser.add_argument("--consumers", type=int, default=3)
    parser.add_argument("--hot-tenant-events", type=int, default=40)
    args = parser.parse_args()
    keys = [f"tenant-{number}" for number in range(30)]
    keys.extend(["tenant-hot"] * args.hot_tenant_events)
    result = analyze(keys, args.partitions, args.consumers)
    print(json.dumps(asdict(result), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
