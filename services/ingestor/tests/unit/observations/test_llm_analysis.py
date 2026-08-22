from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient


pytest.importorskip("openai", reason="openai is not in active MVP scope")

from services.ingestor.api_schemas.observations import ObservationClassification
from services.ingestor.models import Observation


@pytest.fixture
def mock_observation():
    return Observation(
        id=1,
        source_id=1,
        timestamp=datetime.now(UTC).replace(tzinfo=None),
        raw_data={"key": "value"},
        tags=["test"],
        processed=False,
        created_at=datetime.now(UTC).replace(tzinfo=None),
    )


@pytest.mark.integration
class TestLLMAnalysis:
    @patch("services.ingestor.api.routes.observations.settings")
    @patch("services.ingestor.api.routes.observations.get_observation_op")
    @patch(
        "services.ingestor.api.routes.observations.vs_bridge.search_observation_documents"
    )
    @patch("openai.AsyncOpenAI")
    async def test_analyze_observation_success(
        self,
        mock_openai_class,
        mock_search,
        mock_get_observation,
        mock_settings,
        mock_observation,
        client: AsyncClient,
    ):
        # Mock Settings
        mock_settings.openai_enabled = True
        mock_settings.openai_api_key = "test-key"
        mock_settings.openai_model = "gpt-4o"

        # Mock DB lookup
        mock_get_observation.return_value = mock_observation

        # Mock Vector Search
        mock_search.return_value = {"results": [{"text": "some context"}]}

        # Mock OpenAI
        mock_openai_instance = mock_openai_class.return_value
        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock()]
        mock_completion.choices[0].message.parsed = ObservationClassification(
            category="test", priority=1, summary="test summary", sentiment="neutral"
        )
        mock_completion.usage.prompt_tokens = 10

        # Mock beta.chat.completions.parse
        mock_openai_instance.beta.chat.completions.parse = AsyncMock(
            return_value=mock_completion
        )

        response = await client.post("/api/v1/observations/1/analyze")

        assert response.status_code == 200
        data = response.json()
        assert data["category"] == "test"
        assert data["priority"] == 1

        mock_get_observation.assert_called_once()
        mock_search.assert_called_once()
        mock_openai_instance.beta.chat.completions.parse.assert_called_once()

    @patch("services.ingestor.api.routes.observations.settings")
    @patch("services.ingestor.api.routes.observations.get_observation_op")
    @patch("openai.AsyncOpenAI")
    async def test_analyze_observation_stream_success(
        self,
        mock_openai_class,
        mock_get_observation,
        mock_settings,
        mock_observation,
        client: AsyncClient,
    ):
        # Mock Settings
        mock_settings.openai_enabled = True
        mock_settings.openai_api_key = "test-key"
        mock_settings.openai_model = "gpt-4o"

        mock_get_observation.return_value = mock_observation

        mock_openai_instance = mock_openai_class.return_value

        # Mock stream
        async def mock_stream_gen():
            yield MagicMock(choices=[MagicMock(delta=MagicMock(content="chunk1"))])
            yield MagicMock(choices=[MagicMock(delta=MagicMock(content="chunk2"))])

        mock_openai_instance.chat.completions.create = AsyncMock(
            return_value=mock_stream_gen()
        )

        response = await client.post("/api/v1/observations/1/analyze/stream")

        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]

        content = response.text
        assert "data: chunk1" in content
        assert "data: chunk2" in content

    @patch("services.ingestor.api.routes.observations.settings")
    @patch("services.ingestor.api.routes.observations.get_observation_op")
    async def test_analyze_observation_disabled(
        self, mock_get_observation, mock_settings, mock_observation, client: AsyncClient
    ):
        # Mock Settings: Disabled
        mock_settings.openai_enabled = False
        mock_get_observation.return_value = mock_observation

        response = await client.post("/api/v1/observations/1/analyze")

        assert response.status_code == 501
        assert "disabled" in response.json()["detail"]

    @patch("services.ingestor.api.routes.observations.settings")
    @patch("services.ingestor.api.routes.observations.get_observation_op")
    async def test_analyze_observation_missing_key(
        self, mock_get_observation, mock_settings, mock_observation, client: AsyncClient
    ):
        # Mock Settings: Enabled but no key
        mock_settings.openai_enabled = True
        mock_settings.openai_api_key = None
        mock_get_observation.return_value = mock_observation

        response = await client.post("/api/v1/observations/1/analyze")

        assert response.status_code == 501
        assert "missing" in response.json()["detail"]
