"""MinIO S3-compatible object storage client.

Handles:
- Raw payload backup (before transformation)
- Audit log storage (per-sync events)
- Metadata versioning for disaster recovery
"""

from __future__ import annotations

import json
from importlib import import_module
from io import BytesIO
from typing import TYPE_CHECKING, Any, Protocol


try:
    Minio = import_module("minio").Minio
    S3Error = import_module("minio.error").S3Error
except ModuleNotFoundError:

    class S3Error(Exception):
        """Fallback S3 error when MinIO dependency is unavailable."""

    class Minio:  # type: ignore[no-redef]
        """Fallback MinIO client placeholder for environments without minio."""

        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass


if TYPE_CHECKING:

    class DataSource(Protocol):
        """Minimal protocol required by MinIO storage helpers."""

        id: Any


class MinIOClient:
    """Wrapper around MinIO S3-compatible client.

    Provides typed interface for backup and audit operations.
    """

    def __init__(self, endpoint: str, access_key: str, secret_key: str):
        """Initialize MinIO client.

        Args:
            endpoint: MinIO server endpoint (e.g., 'localhost:9000').
            access_key: MinIO access key.
            secret_key: MinIO secret key.
        """
        self.client = Minio(endpoint, access_key=access_key, secret_key=secret_key)
        self.endpoint = endpoint

    async def backup_raw_payload(
        self, source: DataSource, batch_id: str, payload: bytes
    ) -> str:
        """Backup raw (pre-transformation) payload to MinIO.

        Args:
            source: The DataSource being synced.
            batch_id: Unique ID for this sync batch.
            payload: Raw bytes (e.g., CSV file content).

        Returns:
            Object path in MinIO (for audit trail).

        Raises:
            S3Error: If upload fails.
        """
        bucket = f"raw-backups-{source.id}"
        object_name = f"{batch_id}/payload.bin"

        # Ensure bucket exists
        await self._ensure_bucket(bucket)

        # Upload payload
        payload_stream = BytesIO(payload)
        self.client.put_object(bucket, object_name, payload_stream, len(payload))

        return f"s3://{self.endpoint}/{bucket}/{object_name}"

    async def store_audit_log(
        self, source: DataSource, batch_id: str, audit_events: list[dict]
    ) -> str:
        """Store audit log (transformation events) to MinIO.

        Args:
            source: The DataSource being synced.
            batch_id: Unique ID for this sync batch.
            audit_events: List of event dicts (validation, dedup, enrichment).

        Returns:
            Object path in MinIO.

        Raises:
            S3Error: If upload fails.
        """
        bucket = f"audit-logs-{source.id}"
        object_name = f"{batch_id}/events.jsonl"

        # Ensure bucket exists
        await self._ensure_bucket(bucket)

        # Serialize audit events to JSONL
        jsonl_content = "\n".join(json.dumps(event) for event in audit_events)
        audit_stream = BytesIO(jsonl_content.encode("utf-8"))

        self.client.put_object(
            bucket, object_name, audit_stream, len(jsonl_content.encode())
        )

        return f"s3://{self.endpoint}/{bucket}/{object_name}"

    async def retrieve_backup(self, backup_path: str) -> bytes:
        """Retrieve raw payload backup from MinIO.

        Args:
            backup_path: Object path (from backup_raw_payload).

        Returns:
            Raw payload bytes.

        Raises:
            S3Error: If download fails.
        """
        # Parse s3:// URL
        parts = backup_path.replace("s3://", "").split("/", 2)
        bucket = parts[1]
        object_name = "/".join(parts[2:])

        response = self.client.get_object(bucket, object_name)
        return response.read()

    async def _ensure_bucket(self, bucket: str) -> None:
        """Ensure bucket exists; create if not.

        Args:
            bucket: Bucket name.
        """
        try:
            if not self.client.bucket_exists(bucket):
                self.client.make_bucket(bucket)
        except S3Error as e:
            raise S3Error(f"Failed to ensure bucket {bucket}: {e}") from e
