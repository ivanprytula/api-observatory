"""Integration tests for schema integrity and data model.

Tests in this directory verify:
- Index definitions and performance hotspots
- Unique and primary key constraints
- Data retention and archival behavior
- Materialized views and partitioned tables
- Soft-delete functionality

Run with: pytest tests/integration/schema/ -v
"""
