"""Tests for storage layer (MinIO client and watermark manager)."""

from __future__ import annotations

import sys
import types
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock


def _get_minio_client_class() -> type:
    """Load MinIOClient with a local minio stub when dependency is absent."""
    if "minio" not in sys.modules:
        minio_module = types.ModuleType("minio")

        class _DummyMinio:  # noqa: N801
            def __init__(self, *_args: object, **_kwargs: object) -> None:
                pass

        minio_module.Minio = _DummyMinio
        sys.modules["minio"] = minio_module

    if "minio.error" not in sys.modules:
        minio_error_module = types.ModuleType("minio.error")

        class _DummyS3Error(Exception):
            pass

        minio_error_module.S3Error = _DummyS3Error
        sys.modules["minio.error"] = minio_error_module

    from services.ingestor.storage.minios3 import MinIOClient

    return MinIOClient


def _get_watermark_manager_class() -> type:
    """Load WatermarkManager lazily for consistency with MinIO loader."""
    from services.ingestor.storage.watermark import WatermarkManager

    return WatermarkManager


class TestMinIOClient:
    """Test MinIO backup and audit storage behavior."""

    async def test_backup_raw_payload_uploads_and_returns_s3_path(self) -> None:
        """backup_raw_payload uploads bytes and returns canonical S3 path."""
        minio_client_cls = _get_minio_client_class()
        mock_minio_client = MagicMock()
        mock_minio_client.bucket_exists.return_value = True

        minio_client = minio_client_cls("minio.local:9000", "key", "secret")
        minio_client.client = mock_minio_client

        source = SimpleNamespace(id=42)
        payload = b"raw-payload"

        result = await minio_client.backup_raw_payload(source, "batch-1", payload)

        assert result == "s3://minio.local:9000/raw-backups-42/batch-1/payload.bin"
        mock_minio_client.put_object.assert_called_once()
        bucket_arg, object_arg, _stream_arg, len_arg = (
            mock_minio_client.put_object.call_args.args
        )
        assert bucket_arg == "raw-backups-42"
        assert object_arg == "batch-1/payload.bin"
        assert len_arg == len(payload)

    async def test_store_audit_log_uploads_jsonl_and_returns_s3_path(self) -> None:
        """store_audit_log serializes JSONL and uploads it to MinIO."""
        minio_client_cls = _get_minio_client_class()
        mock_minio_client = MagicMock()
        mock_minio_client.bucket_exists.return_value = True

        minio_client = minio_client_cls("minio.local:9000", "key", "secret")
        minio_client.client = mock_minio_client

        source = SimpleNamespace(id=7)
        audit_events = [{"event": "validated"}, {"event": "enriched", "ok": True}]

        result = await minio_client.store_audit_log(source, "batch-2", audit_events)

        assert result == "s3://minio.local:9000/audit-logs-7/batch-2/events.jsonl"
        mock_minio_client.put_object.assert_called_once()
        bucket_arg, object_arg, _stream_arg, len_arg = (
            mock_minio_client.put_object.call_args.args
        )
        assert bucket_arg == "audit-logs-7"
        assert object_arg == "batch-2/events.jsonl"
        assert len_arg > 0

    async def test_retrieve_backup_reads_bytes_from_object(self) -> None:
        """retrieve_backup parses S3 URL and returns object bytes."""
        minio_client_cls = _get_minio_client_class()
        mock_minio_client = MagicMock()
        mock_response = MagicMock()
        mock_response.read.return_value = b"payload-bytes"
        mock_minio_client.get_object.return_value = mock_response

        minio_client = minio_client_cls("minio.local:9000", "key", "secret")
        minio_client.client = mock_minio_client

        result = await minio_client.retrieve_backup(
            "s3://minio.local:9000/raw-backups-11/batch-55/payload.bin"
        )

        assert result == b"payload-bytes"
        mock_minio_client.get_object.assert_called_once_with(
            "raw-backups-11",
            "batch-55/payload.bin",
        )

    async def test_ensure_bucket_creates_missing_bucket(self) -> None:
        """_ensure_bucket creates bucket when it does not exist."""
        minio_client_cls = _get_minio_client_class()
        mock_minio_client = MagicMock()
        mock_minio_client.bucket_exists.return_value = False

        minio_client = minio_client_cls("minio.local:9000", "key", "secret")
        minio_client.client = mock_minio_client

        await minio_client._ensure_bucket("raw-backups-1")

        mock_minio_client.bucket_exists.assert_called_once_with("raw-backups-1")
        mock_minio_client.make_bucket.assert_called_once_with("raw-backups-1")

    async def test_ensure_bucket_skips_existing_bucket(self) -> None:
        """_ensure_bucket does not create bucket when it already exists."""
        minio_client_cls = _get_minio_client_class()
        mock_minio_client = MagicMock()
        mock_minio_client.bucket_exists.return_value = True

        minio_client = minio_client_cls("minio.local:9000", "key", "secret")
        minio_client.client = mock_minio_client

        await minio_client._ensure_bucket("raw-backups-1")

        mock_minio_client.bucket_exists.assert_called_once_with("raw-backups-1")
        mock_minio_client.make_bucket.assert_not_called()


class TestWatermarkManager:
    """Test watermark read/update and sync mode decisions."""

    async def test_get_watermark_returns_none_when_absent(self) -> None:
        """get_watermark returns None when source has never synced."""
        watermark_manager_cls = _get_watermark_manager_class()
        db = SimpleNamespace(add=MagicMock(), commit=AsyncMock())
        manager = watermark_manager_cls(db)

        source = SimpleNamespace(id=1)

        watermark = await manager.get_watermark(source)

        assert watermark is None

    async def test_get_watermark_returns_datetime_when_present(self) -> None:
        """get_watermark returns existing _last_synced_at value."""
        watermark_manager_cls = _get_watermark_manager_class()
        db = SimpleNamespace(add=MagicMock(), commit=AsyncMock())
        manager = watermark_manager_cls(db)

        sync_time = datetime(2026, 5, 7, 8, 30, tzinfo=UTC)
        source = SimpleNamespace(id=1, _last_synced_at=sync_time)

        watermark = await manager.get_watermark(source)

        assert watermark == sync_time

    async def test_update_watermark_uses_explicit_time_and_commits(self) -> None:
        """update_watermark stores explicit timestamp and commits transaction."""
        watermark_manager_cls = _get_watermark_manager_class()
        db = SimpleNamespace(add=MagicMock(), commit=AsyncMock())
        manager = watermark_manager_cls(db)

        source = SimpleNamespace(id=10)
        sync_time = datetime(2026, 5, 7, 12, 0, tzinfo=UTC)

        await manager.update_watermark(source, sync_time)

        assert source._last_synced_at == sync_time
        db.add.assert_called_once_with(source)
        db.commit.assert_awaited_once()

    async def test_update_watermark_sets_now_when_time_not_provided(self) -> None:
        """update_watermark uses current UTC time if sync_time is omitted."""
        watermark_manager_cls = _get_watermark_manager_class()
        db = SimpleNamespace(add=MagicMock(), commit=AsyncMock())
        manager = watermark_manager_cls(db)

        source = SimpleNamespace(id=11)

        await manager.update_watermark(source)

        assert isinstance(source._last_synced_at, datetime)
        assert source._last_synced_at.tzinfo is UTC
        db.add.assert_called_once_with(source)
        db.commit.assert_awaited_once()

    async def test_should_full_sync_true_when_no_watermark(self) -> None:
        """should_full_sync is True when there is no prior watermark."""
        watermark_manager_cls = _get_watermark_manager_class()
        db = SimpleNamespace(add=MagicMock(), commit=AsyncMock())
        manager = watermark_manager_cls(db)

        source = SimpleNamespace(id=20)

        should_full = await manager.should_full_sync(source)

        assert should_full is True

    async def test_should_full_sync_false_when_watermark_exists(self) -> None:
        """should_full_sync is False once watermark has been set."""
        watermark_manager_cls = _get_watermark_manager_class()
        db = SimpleNamespace(add=MagicMock(), commit=AsyncMock())
        manager = watermark_manager_cls(db)

        source = SimpleNamespace(
            id=20, _last_synced_at=datetime(2026, 5, 7, 9, 0, tzinfo=UTC)
        )

        should_full = await manager.should_full_sync(source)

        assert should_full is False
