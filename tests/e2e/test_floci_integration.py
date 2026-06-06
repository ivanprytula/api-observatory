"""End-to-end tests for Floci (local AWS emulator) sandbox integration.

Verifies that the Floci sandbox is running and that core AWS service operations work:
1. Floci container is running and accessible at http://localhost:4566
2. S3 bucket operations (create, list, upload, download)
3. SQS queue operations (create, send, receive messages)

Prerequisites:
    just sandbox-up       # starts Floci and provisions base resources

Run with:
    just sandbox-test
    uv run pytest tests/e2e/test_floci_integration.py -v -m aws
"""

import json
import os
import socket
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

import boto3
import pytest


# Markers: e2e + aws specific
pytestmark = [pytest.mark.e2e, pytest.mark.aws]


def _unique_name(prefix: str) -> str:
    """Generate a deterministic-safe unique resource name per test run."""
    return f"{prefix}-{uuid4().hex[:8]}"


@pytest.fixture(scope="session")
def aws_config() -> dict[str, str]:
    """Get AWS configuration from environment.

    LocalStack should be running:
        just sandbox-up

    Environment variables expected:
        AWS_ENDPOINT_URL=http://localhost:4566
        AWS_REGION=us-east-1
        AWS_ACCESS_KEY_ID=test
        AWS_SECRET_ACCESS_KEY=test
        AWS_ACCOUNT_ID=000000000000
    """
    return {
        "endpoint_url": os.getenv("AWS_ENDPOINT_URL", "http://localhost:4566"),
        "region_name": os.getenv("AWS_REGION", "us-east-1"),
        "aws_access_key_id": os.getenv("AWS_ACCESS_KEY_ID", "test"),
        "aws_secret_access_key": os.getenv("AWS_SECRET_ACCESS_KEY", "test"),
        "account_id": os.getenv("AWS_ACCOUNT_ID", "000000000000"),
    }


@pytest.fixture(scope="session", autouse=True)
def require_floci_endpoint(aws_config: dict[str, str]) -> None:
    """Skip this module when Floci/LocalStack is not reachable.

    Keeps local and CI runs deterministic by treating missing emulator
    infrastructure as a skip, not a hard failure.
    """
    endpoint = aws_config["endpoint_url"]
    parsed = urlparse(endpoint)
    host = parsed.hostname or "localhost"
    if parsed.port is not None:
        port = parsed.port
    elif parsed.scheme == "https":
        port = 443
    else:
        port = 80

    try:
        with socket.create_connection((host, port), timeout=1.0):
            return
    except OSError:
        pytest.skip(
            f"Floci/LocalStack endpoint is unreachable at {endpoint}. Run `just sandbox-up`.",
            allow_module_level=True,
        )


@pytest.fixture
def s3_client(aws_config: dict[str, str]) -> Any:
    """Create S3 client pointing to Floci."""
    return boto3.client(
        "s3",
        endpoint_url=aws_config["endpoint_url"],
        region_name=aws_config["region_name"],
        aws_access_key_id=aws_config["aws_access_key_id"],
        aws_secret_access_key=aws_config["aws_secret_access_key"],
    )


@pytest.fixture
def sqs_client(aws_config: dict[str, str]) -> Any:
    """Create SQS client pointing to LocalStack."""
    return boto3.client(
        "sqs",
        endpoint_url=aws_config["endpoint_url"],
        region_name=aws_config["region_name"],
        aws_access_key_id=aws_config["aws_access_key_id"],
        aws_secret_access_key=aws_config["aws_secret_access_key"],
    )


# ---------------------------------------------------------------------------
# S3 Tests
# ---------------------------------------------------------------------------


def test_s3_bucket_creation(s3_client: Any) -> None:
    """Test S3 bucket creation and listing.

    Verifies:
    - Can create a bucket
    - Can list buckets
    """
    bucket_name = _unique_name("test-bucket-phase1")

    # Create bucket
    s3_client.create_bucket(Bucket=bucket_name)

    # List buckets
    response = s3_client.list_buckets()
    bucket_names = [b["Name"] for b in response["Buckets"]]

    assert bucket_name in bucket_names


def test_s3_object_operations(s3_client: Any) -> None:
    """Test S3 object upload, download, and listing.

    Verifies:
    - Can upload objects to bucket
    - Can download objects from bucket
    - Can list objects in bucket
    """
    bucket_name = _unique_name("test-bucket-objects")
    s3_client.create_bucket(Bucket=bucket_name)

    # Upload object
    test_key = "test-data.json"
    test_content = json.dumps({"message": "Hello from LocalStack", "phase": 1})
    s3_client.put_object(Bucket=bucket_name, Key=test_key, Body=test_content)

    # List objects
    response = s3_client.list_objects_v2(Bucket=bucket_name)
    object_keys = [obj["Key"] for obj in response.get("Contents", [])]
    assert test_key in object_keys

    # Download object
    response = s3_client.get_object(Bucket=bucket_name, Key=test_key)
    downloaded_content = response["Body"].read().decode()
    assert json.loads(downloaded_content) == json.loads(test_content)


def test_s3_multiple_objects(s3_client: Any) -> None:
    """Test uploading and managing multiple objects.

    Verifies:
    - Can upload multiple objects
    - Objects are retrievable independently
    """
    bucket_name = _unique_name("test-bucket-multi")
    s3_client.create_bucket(Bucket=bucket_name)

    # Upload multiple objects
    objects = {
        "data/event-1.json": {"event_id": 1, "type": "order"},
        "data/event-2.json": {"event_id": 2, "type": "payment"},
        "metadata/schema.json": {"version": "1.0", "schema": "pipeline"},
    }

    for key, content in objects.items():
        s3_client.put_object(Bucket=bucket_name, Key=key, Body=json.dumps(content))

    # Verify all objects exist
    response = s3_client.list_objects_v2(Bucket=bucket_name)
    uploaded_keys = sorted([obj["Key"] for obj in response["Contents"]])
    assert uploaded_keys == sorted(objects.keys())


# ---------------------------------------------------------------------------
# SQS Tests
# ---------------------------------------------------------------------------


def test_sqs_queue_creation(sqs_client: Any) -> None:
    """Test SQS queue creation and listing.

    Verifies:
    - Can create queue
    - Can list queues
    """
    queue_name = _unique_name("test-queue-phase1")

    # Create queue
    response = sqs_client.create_queue(QueueName=queue_name)
    queue_url = response["QueueUrl"]
    assert queue_url is not None

    # List queues
    response = sqs_client.list_queues()
    queue_urls = response.get("QueueUrls", [])
    assert any(queue_name in url for url in queue_urls)


def test_sqs_message_operations(sqs_client: Any) -> None:
    """Test SQS message send and receive.

    Verifies:
    - Can send message to queue
    - Can receive message from queue
    - Message body is preserved
    """
    queue_name = _unique_name("test-queue-messages")
    response = sqs_client.create_queue(QueueName=queue_name)
    queue_url = response["QueueUrl"]

    # Send message
    test_message = json.dumps({"order_id": 123, "status": "pending"})
    sqs_client.send_message(QueueUrl=queue_url, MessageBody=test_message)

    # Receive message
    response = sqs_client.receive_message(QueueUrl=queue_url)
    messages = response.get("Messages", [])

    assert len(messages) == 1
    received_body = json.loads(messages[0]["Body"])
    assert received_body["order_id"] == 123
    assert received_body["status"] == "pending"


def test_sqs_batch_messages(sqs_client: Any) -> None:
    """Test SQS batch message operations.

    Verifies:
    - Can send multiple messages
    - Can receive multiple messages
    """
    queue_name = _unique_name("test-queue-batch")
    response = sqs_client.create_queue(QueueName=queue_name)
    queue_url = response["QueueUrl"]

    # Send batch of messages
    messages = [{"order_id": i, "customer": f"customer-{i}"} for i in range(1, 4)]
    for _, msg in enumerate(messages):
        sqs_client.send_message(QueueUrl=queue_url, MessageBody=json.dumps(msg))

    # Receive messages
    response = sqs_client.receive_message(QueueUrl=queue_url, MaxNumberOfMessages=10)
    received_messages = response.get("Messages", [])

    assert len(received_messages) == 3
    received_order_ids = [
        json.loads(msg["Body"])["order_id"] for msg in received_messages
    ]
    assert set(received_order_ids) == {1, 2, 3}


# ---------------------------------------------------------------------------
# Integration Tests (Cross-Service)
# ---------------------------------------------------------------------------


def test_s3_and_sqs_integration(s3_client: Any, sqs_client: Any) -> None:
    """Test S3 and SQS working together.

    Workflow:
    1. Upload data to S3
    2. Send notification to SQS with S3 reference
    3. Retrieve and verify both
    """
    # Setup S3
    bucket_name = _unique_name("integration-bucket")
    s3_client.create_bucket(Bucket=bucket_name)

    # Setup SQS
    queue_name = _unique_name("integration-queue")
    response = sqs_client.create_queue(QueueName=queue_name)
    queue_url = response["QueueUrl"]

    # Upload data to S3
    data_key = "processed/data-001.json"
    data_content = {"observations": [{"id": 1}, {"id": 2}]}
    s3_client.put_object(
        Bucket=bucket_name, Key=data_key, Body=json.dumps(data_content)
    )

    # Send notification to SQS
    notification = {"bucket": bucket_name, "key": data_key, "status": "ready"}
    sqs_client.send_message(QueueUrl=queue_url, MessageBody=json.dumps(notification))

    # Verify: Retrieve from SQS
    response = sqs_client.receive_message(QueueUrl=queue_url)
    message_body = json.loads(response["Messages"][0]["Body"])
    assert message_body["bucket"] == bucket_name
    assert message_body["key"] == data_key

    # Verify: Retrieve from S3
    s3_response = s3_client.get_object(Bucket=bucket_name, Key=data_key)
    retrieved_data = json.loads(s3_response["Body"].read())
    assert retrieved_data == data_content
