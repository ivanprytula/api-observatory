"""Storage layer — platform-wide data access (events, documents, vectors, etc).

Modules in this package are shared across ingestor and processor services:
- events.py: ProcessedEvent CRUD (Kafka event tracking, idempotency, DLQ)
- mongo.py (Phase 2): MongoDB storage for scraped documents
- vectors.py (Phase 3): Vector storage for embeddings (Qdrant client wrapper)
"""
