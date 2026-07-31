"""Deterministic proof for the isolated partitioning lab."""

import pytest

from labs.partitioning_sharding.partition_demo import (
    analyze,
    consumer_assignment,
    partition_for,
)


pytestmark = pytest.mark.unit


def test_same_key_routes_to_same_partition() -> None:
    assert partition_for("tenant-42", 12) == partition_for("tenant-42", 12)


def test_consumers_share_partitions_round_robin() -> None:
    assert consumer_assignment(6, 3) == {0: 0, 1: 1, 2: 2, 3: 0, 4: 1, 5: 2}


def test_hot_key_and_resharding_cost_are_visible() -> None:
    keys = [f"tenant-{number}" for number in range(20)] + ["tenant-hot"] * 50
    result = analyze(keys, partition_count=4, consumer_count=2)
    assert result.hottest_share > 0.5
    assert result.keys_moved_when_doubled > 0
    assert 1 <= result.cross_shard_query_fanout <= 4
