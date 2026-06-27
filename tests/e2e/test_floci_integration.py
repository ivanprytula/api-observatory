"""End-to-end tests for floci-az (local Azure emulator) sandbox integration.

Verifies that the floci-az sandbox is running and that core service operations work:
1. floci-az container is running and accessible at http://127.0.0.1:4577
2. Blob Storage operations (create container, upload, download, list)
3. Queue Storage operations (create queue, send, receive messages)

Prerequisites:
    just floci-az-up    # starts floci-az and provisions base resources

Run with:
    uv run pytest tests/e2e/test_floci_integration.py -v -m azure
"""

import json
import os
import socket
from urllib.parse import urlparse
from uuid import uuid4

import pytest
from azure.storage.blob import BlobServiceClient
from azure.storage.queue import QueueServiceClient


pytestmark = [pytest.mark.e2e, pytest.mark.azure]

_AZURITE_CONN_STR = (
    "DefaultEndpointsProtocol=http;"
    "AccountName=devstoreaccount1;"
    "AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/"
    "K1SZFPTOtr/KBHBeksoGMGw==;"
    "BlobEndpoint=http://127.0.0.1:4577/devstoreaccount1;"
    "QueueEndpoint=http://127.0.0.1:4577/devstoreaccount1;"
)


def _unique_name(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:8]}"


@pytest.fixture(scope="session")
def azure_config() -> dict[str, str]:
    """Get Azure emulator configuration from environment."""
    return {
        "connection_string": os.getenv(
            "AZURE_STORAGE_CONNECTION_STRING", _AZURITE_CONN_STR
        ),
        "endpoint": os.getenv("AZURE_ENDPOINT_URL", "http://127.0.0.1:4577"),
    }


@pytest.fixture(scope="session", autouse=True)
def require_floci_az_endpoint(azure_config: dict[str, str]) -> None:
    """Skip this module when floci-az is not reachable."""
    endpoint = azure_config["endpoint"]
    parsed = urlparse(endpoint)
    host = parsed.hostname or "localhost"
    port = parsed.port or 4577

    try:
        with socket.create_connection((host, port), timeout=1.0):
            return
    except OSError:
        pytest.skip(
            f"floci-az endpoint is unreachable at {endpoint}. Run `just floci-az-up`.",
            allow_module_level=True,
        )


@pytest.fixture
def blob_client(azure_config: dict[str, str]) -> BlobServiceClient:
    return BlobServiceClient.from_connection_string(azure_config["connection_string"])


@pytest.fixture
def queue_client(azure_config: dict[str, str]) -> QueueServiceClient:
    return QueueServiceClient.from_connection_string(azure_config["connection_string"])


# ---------------------------------------------------------------------------
# Blob Storage Tests
# ---------------------------------------------------------------------------


def test_blob_container_creation(blob_client: BlobServiceClient) -> None:
    container_name = _unique_name("test-container")

    blob_client.create_container(container_name)

    containers = [c["name"] for c in blob_client.list_containers()]
    assert container_name in containers


def test_blob_upload_download(blob_client: BlobServiceClient) -> None:
    container_name = _unique_name("test-blobs")
    blob_client.create_container(container_name)

    test_data = json.dumps({"message": "Hello from floci-az", "phase": 1})
    blob_name = "test-data.json"

    container = blob_client.get_container_client(container_name)
    container.upload_blob(blob_name, test_data)

    blobs = [b["name"] for b in container.list_blobs()]
    assert blob_name in blobs

    downloaded = container.download_blob(blob_name).readall().decode()
    assert json.loads(downloaded) == json.loads(test_data)


def test_blob_multiple_objects(blob_client: BlobServiceClient) -> None:
    container_name = _unique_name("test-multi")
    blob_client.create_container(container_name)

    objects = {
        "data/event-1.json": {"event_id": 1, "type": "order"},
        "data/event-2.json": {"event_id": 2, "type": "payment"},
        "metadata/schema.json": {"version": "1.0", "schema": "pipeline"},
    }

    container = blob_client.get_container_client(container_name)
    for name, content in objects.items():
        container.upload_blob(name, json.dumps(content))

    uploaded = sorted([b["name"] for b in container.list_blobs()])
    assert uploaded == sorted(objects.keys())


# ---------------------------------------------------------------------------
# Queue Storage Tests
# ---------------------------------------------------------------------------


def test_queue_creation(queue_client: QueueServiceClient) -> None:
    queue_name = _unique_name("test-queue")

    queue_client.create_queue(queue_name)

    queues = [q["name"] for q in queue_client.list_queues()]
    assert queue_name in queues


def test_queue_message_operations(queue_client: QueueServiceClient) -> None:
    queue_name = _unique_name("test-messages")
    queue = queue_client.create_queue(queue_name)

    test_message = json.dumps({"order_id": 123, "status": "pending"})
    queue.send_message(test_message)

    messages = queue.receive_messages()
    received = [json.loads(m.content) for m in messages]

    assert len(received) == 1
    assert received[0]["order_id"] == 123
    assert received[0]["status"] == "pending"


def test_queue_batch_messages(queue_client: QueueServiceClient) -> None:
    queue_name = _unique_name("test-batch")
    queue = queue_client.create_queue(queue_name)

    payloads = [{"order_id": i, "customer": f"customer-{i}"} for i in range(1, 4)]
    for msg in payloads:
        queue.send_message(json.dumps(msg))

    messages = queue.receive_messages(messages_per_page=10)
    received_ids = {json.loads(m.content)["order_id"] for m in messages}

    assert received_ids == {1, 2, 3}


# ---------------------------------------------------------------------------
# Integration Tests (Cross-Service)
# ---------------------------------------------------------------------------


def test_blob_and_queue_integration(
    blob_client: BlobServiceClient, queue_client: QueueServiceClient
) -> None:
    """Upload data to Blob Storage, notify via Queue, verify both."""
    container_name = _unique_name("integration")
    blob_client.create_container(container_name)

    queue_name = _unique_name("integration-q")
    queue = queue_client.create_queue(queue_name)

    data_blob = "processed/data-001.json"
    data_content = {"observations": [{"id": 1}, {"id": 2}]}
    container = blob_client.get_container_client(container_name)
    container.upload_blob(data_blob, json.dumps(data_content))

    notification = {"container": container_name, "blob": data_blob, "status": "ready"}
    queue.send_message(json.dumps(notification))

    messages = queue.receive_messages()
    msg_body = json.loads(list(messages)[0].content)
    assert msg_body["container"] == container_name
    assert msg_body["blob"] == data_blob

    retrieved = json.loads(container.download_blob(data_blob).readall())
    assert retrieved == data_content
