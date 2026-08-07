"""Exercise Blob Storage contracts against the local Azure emulator."""

import json
import os
import socket
from urllib.parse import urlparse
from uuid import uuid4

import pytest
from azure.storage.blob import BlobServiceClient


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
            "floci-az endpoint is unreachable at "
            f"{endpoint}. Run `just --justfile just/labs.just lab-cloud-up azure`.",
            allow_module_level=True,
        )


@pytest.fixture
def blob_client(azure_config: dict[str, str]) -> BlobServiceClient:
    return BlobServiceClient.from_connection_string(azure_config["connection_string"])


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
