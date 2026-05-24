"""Record validation strategies (Strategy pattern).

Each source type (CSV, JSON, API) has different validation rules.
This module defines the RecordValidationStrategy interface and pluggable implementations.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime


class RecordValidationStrategy(ABC):
    """Abstract interface for record validation.

    Each validator is responsible for checking that a record conforms to
    source-specific requirements (required fields, types, value ranges).
    """

    @abstractmethod
    async def validate(self, record: dict) -> tuple[bool, str | None]:
        """Validate a record.

        Args:
            record: The raw record dict to validate.

        Returns:
            Tuple of (is_valid, error_message).
            If valid: (True, None)
            If invalid: (False, error_message explaining why)
        """


class CSVRecordValidator(RecordValidationStrategy):
    """Validator for CSV/tabular sources.

    Enforces:
    - Required fields: ['id', 'price', 'timestamp']
    - Type coercion: price → float, timestamp → datetime
    - Value constraints: price >= 0, timestamp in past
    """

    REQUIRED_FIELDS = ["id", "price", "timestamp"]

    async def validate(self, record: dict) -> tuple[bool, str | None]:
        """Validate CSV-sourced record."""
        # Check required fields exist
        for field in self.REQUIRED_FIELDS:
            if field not in record or record[field] is None:
                return False, f"Missing required field: {field}"

        # Validate and coerce types
        if not await self._validate_id(record.get("id")):
            return False, "Invalid 'id': must be non-empty string"

        is_valid, error = await self._validate_price(record.get("price"))
        if not is_valid:
            return False, error

        is_valid, error = await self._validate_timestamp(record.get("timestamp"))
        if not is_valid:
            return False, error

        return True, None

    async def _validate_id(self, value: object) -> bool:
        """Check id is non-empty string."""
        return isinstance(value, str) and len(value) > 0

    async def _validate_price(self, value: object) -> tuple[bool, str | None]:
        """Check price is numeric and >= 0."""
        try:
            price = float(value) if not isinstance(value, float) else value
            if price < 0:
                return False, "Price must be >= 0"
            return True, None
        except ValueError, TypeError:
            return False, "Price must be numeric (int/float/string)"

    async def _validate_timestamp(self, value: object) -> tuple[bool, str | None]:
        """Check timestamp is ISO string and in past."""
        try:
            if isinstance(value, str):
                ts = datetime.fromisoformat(value.replace("Z", "+00:00"))
            elif isinstance(value, datetime):
                ts = value
            else:
                return False, "Timestamp must be ISO string or datetime"

            if ts > datetime.now(tz=ts.tzinfo) if ts.tzinfo else datetime.now():
                return False, "Timestamp cannot be in future"
            return True, None
        except (ValueError, AttributeError) as e:
            return False, f"Invalid timestamp format: {e}"


class JSONRecordValidator(RecordValidationStrategy):
    """Validator for JSON/nested sources.

    More lenient than CSV: allows nested structures,
    optional fields, flexible schema.
    """

    async def validate(self, record: dict) -> tuple[bool, str | None]:
        """Validate JSON-sourced record.

        Basic checks: is dict, has 'id', record not empty.
        """
        if not isinstance(record, dict):
            return False, "Record must be dict/object"

        if "id" not in record or record["id"] is None:
            return False, "Missing required field: 'id'"

        if len(record) == 0:
            return False, "Record cannot be empty"

        return True, None


class APIRecordValidator(RecordValidationStrategy):
    """Validator for API sources (minimal, trust contract).

    Assumes the API already validates; we do minimal checking
    to catch only obvious schema mismatches.
    """

    async def validate(self, record: dict) -> tuple[bool, str | None]:
        """Validate API-sourced record (permissive).

        Only check: record is dict and not empty.
        """
        if not isinstance(record, dict):
            return False, "Record must be dict/object"

        if len(record) == 0:
            return False, "Record cannot be empty"

        return True, None
