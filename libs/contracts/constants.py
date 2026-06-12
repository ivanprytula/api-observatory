"""Constants for cross-service dashboard contracts.

These are a minimal subset of values that Pydantic schema field definitions
need. They live here instead of in services/ingestor/constants.py so that
libs.contracts has zero service imports.
"""

# Provider Scorecards
SCORECARD_DEFAULT_SLO_TARGET_PCT: float = 99.9
HEALTH_SAMPLE_ERROR_MSG_MAX: int = 512
HEALTH_SAMPLE_REGION_MAX: int = 64

# Contract & Drift Detection
CONTRACT_SCHEMA_VERSION_MAX: int = 64
CONTRACT_SNAPSHOT_NOTE_MAX: int = 512

# Source Registry
SOURCE_PROFILE_NAME_MAX: int = 255
SOURCE_PROFILE_URL_MAX: int = 2048
SOURCE_HEALTH_UNHEALTHY_THRESHOLD_MS: int = 5000
