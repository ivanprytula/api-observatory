# Evergreen Engineering Labs

Labs are opt-in executable experiments. They do not run with the default application stack and do
not prove production operation.

| Lab | Learning target | Proof |
| --- | --- | --- |
| [Gateway and load balancing](gateway_load_balancing/README.md) | Distribution, passive health removal, graceful shutdown, recovery, and local-state hazards | Standalone Compose plus verification script |
| [Partitioning and sharding](partitioning_sharding/README.md) | Stable key routing, hotspots, consumer assignment, resharding, and cross-shard cost | Deterministic stdlib Python model plus tests |

Run one lab at a time, record observations, and tear down its isolated resources afterward.
