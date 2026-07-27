"""Executable Kafka partition and consumer-group experiment using isolated Redpanda."""

from __future__ import annotations

import argparse
import asyncio
import json
import uuid
from collections import defaultdict

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from aiokafka.admin import AIOKafkaAdminClient, NewTopic


async def _wait_for_assignments(consumers: list[AIOKafkaConsumer]) -> None:
    async with asyncio.timeout(10):
        while not all(consumer.assignment() for consumer in consumers):
            await asyncio.sleep(0.1)


async def _consume_expected(
    consumers: list[AIOKafkaConsumer], expected: int
) -> list[int]:
    counts = [0 for _ in consumers]
    async with asyncio.timeout(10):
        while sum(counts) < expected:
            batches = await asyncio.gather(
                *(
                    consumer.getmany(timeout_ms=500, max_records=expected)
                    for consumer in consumers
                )
            )
            for index, batch in enumerate(batches):
                counts[index] += sum(len(records) for records in batch.values())
    return counts


async def run(broker: str, partitions: int, consumers_count: int) -> dict:
    topic = f"api-observatory-partition-lab-{uuid.uuid4().hex[:8]}"
    group_id = f"partition-lab-{uuid.uuid4().hex[:8]}"
    admin = AIOKafkaAdminClient(bootstrap_servers=broker)
    producer = AIOKafkaProducer(bootstrap_servers=broker)
    consumers = [
        AIOKafkaConsumer(
            topic,
            bootstrap_servers=broker,
            group_id=group_id,
            auto_offset_reset="earliest",
            enable_auto_commit=False,
        )
        for _ in range(consumers_count)
    ]
    await admin.start()
    try:
        await admin.create_topics(
            [NewTopic(topic, num_partitions=partitions, replication_factor=1)]
        )
        await asyncio.gather(*(consumer.start() for consumer in consumers))
        await _wait_for_assignments(consumers)
        await producer.start()

        keys = [f"tenant-{number % 8}" for number in range(32)]
        routed: dict[str, set[int]] = defaultdict(set)
        for index, key in enumerate(keys):
            metadata = await producer.send_and_wait(
                topic,
                key=key.encode(),
                value=json.dumps({"index": index, "key": key}).encode(),
            )
            routed[key].add(metadata.partition)

        consumed = await _consume_expected(consumers, len(keys))
        assignments = [
            sorted(partition.partition for partition in consumer.assignment())
            for consumer in consumers
        ]
        if any(len(partitions_for_key) != 1 for partitions_for_key in routed.values()):
            raise RuntimeError("A stable key was routed to more than one partition.")
        if sum(consumed) != len(keys):
            raise RuntimeError(
                f"Expected {len(keys)} consumed records, observed {sum(consumed)}."
            )
        return {
            "topic": topic,
            "key_to_partition": {
                key: next(iter(value)) for key, value in sorted(routed.items())
            },
            "consumer_assignments": assignments,
            "records_per_consumer": consumed,
        }
    finally:
        await producer.stop()
        await asyncio.gather(*(consumer.stop() for consumer in consumers))
        try:
            await admin.delete_topics([topic])
        finally:
            await admin.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--broker", default="127.0.0.1:19092")
    parser.add_argument("--partitions", type=int, default=6)
    parser.add_argument("--consumers", type=int, default=3)
    args = parser.parse_args()
    if args.partitions < 1 or args.consumers < 1:
        raise SystemExit("partitions and consumers must be positive")
    print(
        json.dumps(
            asyncio.run(run(args.broker, args.partitions, args.consumers)),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
