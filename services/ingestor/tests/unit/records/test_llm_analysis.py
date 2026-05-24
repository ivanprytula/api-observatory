from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from services.ingestor.api_schemas.records import RecordClassification
from services.ingestor.models import Record


@pytest.fixture
def mock_record():
    return Record(
        id=1,
        source="test-source",
        timestamp=datetime.now(UTC).replace(tzinfo=None),
        raw_data={"key": "value"},
        tags=["test"],
        processed=False,
        created_at=datetime.now(UTC).replace(tzinfo=None),
    )


@pytest.mark.unit
class TestLLMAnalysis:
    @patch("services.ingestor.routers.records.settings")
    @patch("services.ingestor.routers.records.get_record_op")
    @patch("services.ingestor.routers.records.vs_bridge.search_record_documents")
    @patch("services.ingestor.routers.records.AsyncOpenAI")
    async def test_analyze_record_success(
        self,
        mock_openai_class,
        mock_search,
        mock_get_record,
        mock_settings,
        mock_record,
        client: AsyncClient,
    ):
        # Mock Settings
        mock_settings.openai_enabled = True
        mock_settings.openai_api_key = "test-key"
        mock_settings.openai_model = "gpt-4o"

        # Mock DB lookup
        mock_get_record.return_value = mock_record

        # Mock Vector Search
        mock_search.return_value = {"results": [{"text": "some context"}]}

        # Mock OpenAI
        mock_openai_instance = mock_openai_class.return_value
        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock()]
        mock_completion.choices[0].message.parsed = RecordClassification(
            category="test", priority=1, summary="test summary", sentiment="neutral"
        )
        mock_completion.usage.prompt_tokens = 10

        # Mock beta.chat.completions.parse
        mock_openai_instance.beta.chat.completions.parse = AsyncMock(
            return_value=mock_completion
        )

        response = await client.post("/api/v1/records/1/analyze")

        assert response.status_code == 200
        data = response.json()
        assert data["category"] == "test"
        assert data["priority"] == 1

        mock_get_record.assert_called_once()
        mock_search.assert_called_once()
        mock_openai_instance.beta.chat.completions.parse.assert_called_once()

    @patch("services.ingestor.routers.records.settings")
    @patch("services.ingestor.routers.records.get_record_op")
    @patch("services.ingestor.routers.records.AsyncOpenAI")
    async def test_analyze_record_stream_success(
        self,
        mock_openai_class,
        mock_get_record,
        mock_settings,
        mock_record,
        client: AsyncClient,
    ):
        # Mock Settings
        mock_settings.openai_enabled = True
        mock_settings.openai_api_key = "test-key"
        mock_settings.openai_model = "gpt-4o"

        mock_get_record.return_value = mock_record

        mock_openai_instance = mock_openai_class.return_value

        # Mock stream
        async def mock_stream_gen():
            yield MagicMock(choices=[MagicMock(delta=MagicMock(content="chunk1"))])
            yield MagicMock(choices=[MagicMock(delta=MagicMock(content="chunk2"))])

        mock_openai_instance.chat.completions.create = AsyncMock(
            return_value=mock_stream_gen()
        )

        response = await client.post("/api/v1/records/1/analyze/stream")

        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]

        content = response.text
        assert "data: chunk1" in content
        assert "data: chunk2" in content

    @patch("services.ingestor.routers.records.settings")
    @patch("services.ingestor.routers.records.get_record_op")
    async def test_analyze_record_disabled(
        self, mock_get_record, mock_settings, mock_record, client: AsyncClient
    ):
        # Mock Settings: Disabled
        mock_settings.openai_enabled = False
        mock_get_record.return_value = mock_record

        response = await client.post("/api/v1/records/1/analyze")

        assert response.status_code == 501
        assert "disabled" in response.json()["detail"]

    @patch("services.ingestor.routers.records.settings")
    @patch("services.ingestor.routers.records.get_record_op")
    async def test_analyze_record_missing_key(
        self, mock_get_record, mock_settings, mock_record, client: AsyncClient
    ):
        # Mock Settings: Enabled but no key
        mock_settings.openai_enabled = True
        mock_settings.openai_api_key = None
        mock_get_record.return_value = mock_record

        response = await client.post("/api/v1/records/1/analyze")

        assert response.status_code == 501
        assert "missing" in response.json()["detail"]
