---
description: "Use when writing, adding, or reviewing Pydantic v2 schemas, validators, serializers, or settings. Covers BaseModel conventions, Field() usage, field_validator / model_validator patterns, model_config, ORM integration, TypeAdapter, and pydantic-settings."
applyTo: "app/**/*.py"
---

# Pydantic v2 Best Practices

## Model Definition

Use `BaseModel` for all request/response schemas. Declare fields with `Field()` for constraints and
documentation; bare annotations are fine only for required fields with no extras.

```python
# CORRECT
class RecordRequest(BaseModel):
    source: str = Field(..., min_length=1, max_length=255)
    data: dict[str, Any]
    tags: list[str] = Field(default_factory=list, max_length=10)

# WRONG — no constraints or documentation
class RecordRequest(BaseModel):
    source: str
    data: dict
    tags: list = []          # mutable default — never do this
```

- Use `...` (Ellipsis) for required fields; omit the default entirely — do not pass `default=None`
  when the field is required.
- Use `default_factory=` for mutable defaults (list, dict) and for dynamic values like
  `datetime.now`.
- Provide `description=` on every public field that will appear in OpenAPI.

---

## `model_config` (v2 Config)

Always use the `model_config` class variable — never the inner `Config` class (v1 style).

```python
# CORRECT — v2 style
class RecordResponse(BaseModel):
    model_config = {"from_attributes": True}

# WRONG — v1 style, ignored in v2
class RecordResponse(BaseModel):
    class Config:
        orm_mode = True
```

Common `model_config` keys:

| Key | When to Use |
|-----|-------------|
| `from_attributes = True` | ORM / dataclass → model conversion (`model_validate(orm_obj)`) |
| `str_strip_whitespace = True` | Auto-strip leading/trailing whitespace in strings |
| `validate_default = True` | Run validators on default values too |
| `populate_by_name = True` | Allow both field name and alias to populate the field |
| `strict = True` | Disable coercion — int stays int, no "1" → 1 casting |
| `frozen = True` | Immutable model (enables `__hash__`) |

---

## `Field()` — Constraints and Metadata

```python
from pydantic import Field

# String constraints
source: str = Field(..., min_length=1, max_length=255, pattern=r"^[\w\.\-]+$")

# Numeric constraints
price: float = Field(..., gt=0, le=1_000_000)

# List constraints (item count, not item type)
tags: list[str] = Field(default_factory=list, max_length=10)

# Alias for JSON input key that differs from Python attribute name
raw_data: dict[str, Any] = Field(..., alias="data")

# Serialization alias (output only)
created_at: datetime = Field(..., serialization_alias="createdAt")

# Exclude this field from model_dump() / serialization by default
internal_flag: bool = Field(default=False, exclude=True)
```

---

## `field_validator` — Per-Field Validation

```python
from pydantic import field_validator

# mode="before" — runs BEFORE Pydantic type coercion
# Use to normalize raw input (strip tz, lowercase, cast types).
@field_validator("timestamp", mode="before")
@classmethod
def normalize_timestamp(cls, v: object) -> object:
    if isinstance(v, datetime) and v.tzinfo is not None:
        return v.replace(tzinfo=None)
    return v

# mode="after" (default) — runs AFTER type coercion
# Use to validate the already-typed value.
@field_validator("timestamp")
@classmethod
def not_in_future(cls, v: datetime) -> datetime:
    if v > datetime.now(UTC).replace(tzinfo=None):
        raise ValueError("timestamp cannot be in the future")
    return v

# Validate multiple fields with one validator
@field_validator("source", "tags", mode="before")
@classmethod
def strip_whitespace(cls, v: object) -> object:
    if isinstance(v, str):
        return v.strip()
    return v
```

**Rules:**
- Always decorate with `@classmethod` — required in v2.
- `mode="before"` receives raw Python value (`str | int | Any`); don't assume the target type.
- `mode="after"` receives the already-coerced type; safe to type-hint as the field type.
- Defensive normalization: if the same invariant must hold in both modes (e.g., tz-naive datetime),
  normalize in *both* validators — Pydantic's `TypeAdapter.validate_python()` can bypass
  `mode="before"` validators in some call paths.
- Raise `ValueError` (or `PydanticCustomError`) — not `TypeError` or `AssertionError`.

---

## `model_validator` — Cross-Field Validation

```python
from pydantic import model_validator
from typing import Self

class DateRange(BaseModel):
    start: datetime
    end: datetime

    @model_validator(mode="after")
    def end_after_start(self) -> Self:
        if self.end <= self.start:
            raise ValueError("end must be after start")
        return self

# mode="before" receives raw dict — use for whole-model normalization
@model_validator(mode="before")
@classmethod
def normalize_input(cls, data: dict[str, Any]) -> dict[str, Any]:
    if "ts" in data and "timestamp" not in data:
        data["timestamp"] = data.pop("ts")
    return data
```

- Prefer `mode="after"` for cross-field constraints — the typed model is available as `self`.
- Return `self` (or a mutated copy) from `mode="after"` validators.
- Use `mode="before"` sparingly; accessing raw dicts is fragile.

---

## `field_serializer` — Custom Serialization

```python
from pydantic import field_serializer

class RecordResponse(BaseModel):
    timestamp: datetime

    @field_serializer("timestamp")
    def serialize_timestamp(self, v: datetime) -> str:
        return v.isoformat()
```

Prefer `field_serializer` over `model_serializer` unless you need to control the whole output dict.

---

## `@computed_field` — Derived Properties

```python
from pydantic import computed_field

class Record(BaseModel):
    tags: list[str]

    @computed_field
    @property
    def tag_count(self) -> int:
        return len(self.tags)
```

Computed fields appear in `model_dump()` and JSON output automatically.
Do not use plain `@property` if you want the value in serialization.

---

## ORM Integration (`from_attributes`)

```python
# Convert ORM model → response schema
record_orm = await db.get(RecordModel, record_id)
response = RecordResponse.model_validate(record_orm)   # CORRECT

# WRONG — passes dict, misses ORM attribute access
response = RecordResponse(**record_orm.__dict__)
```

Always use `model_validate()` (not the constructor) to convert ORM objects.
`from_attributes = True` must be set in `model_config`.

---

## `TypeAdapter` — Validate Outside a Model

```python
from pydantic import TypeAdapter

# Validate a plain list or primitive without wrapping in a model
ta = TypeAdapter(list[RecordRequest])
records = ta.validate_python(raw_list)

# JSON bytes → validated list
records = ta.validate_json(raw_bytes)
```

`TypeAdapter` skips `mode="before"` field validators in some call paths — always validate
defensively inside `mode="after"` validators for invariants that must hold regardless of call site.

---

## `pydantic-settings` (`BaseSettings`)

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str
    debug: bool = False
    db_echo: bool = False

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",        # silently ignore unknown env vars
    }
```

- Use `@lru_cache` to make settings a singleton:
  ```python
  from functools import lru_cache

  @lru_cache(maxsize=1)
  def get_settings() -> Settings:
      return Settings()
  ```
- Never hardcode secrets — read from env vars only.
- Set `extra = "ignore"` to prevent `ValidationError` from unexpected env vars in CI.

---

## `model_dump()` — Serialization

```python
record = RecordRequest(source="api.example.com", data={})

# Exclude unset fields (great for PATCH payloads)
record.model_dump(exclude_unset=True)

# Exclude None values
record.model_dump(exclude_none=True)

# Serialize by alias
record.model_dump(by_alias=True)

# Dict with nested models serialized too
record.model_dump(mode="json")   # all types → JSON-compatible (datetime → str, etc.)
```

---

## Strict Mode vs Lax Mode

Default (lax): Pydantic coerces types — `"123"` → `int`, `1` → `bool`.
Strict: no coercion — type mismatch raises `ValidationError` immediately.

```python
# Per-field strict
from pydantic import Strict
from typing import Annotated

class Request(BaseModel):
    record_id: Annotated[int, Strict()]   # "42" will fail, 42 passes

# Model-wide strict (usually too aggressive for API layers)
class Request(BaseModel):
    model_config = {"strict": True}
```

For API boundaries (FastAPI routes), lax mode is recommended — clients send JSON strings.
For internal domain models, strict is safer.

---

## Discriminated Unions

```python
from typing import Literal, Union
from pydantic import Field

class EmailEvent(BaseModel):
    kind: Literal["email"]
    to: str

class WebhookEvent(BaseModel):
    kind: Literal["webhook"]
    url: str

class EventRequest(BaseModel):
    event: Union[EmailEvent, WebhookEvent] = Field(discriminator="kind")
```

Always use `discriminator=` when the union has a known tag field — Pydantic skips trying all
branches and validation is O(1).

---

## Validation Errors

```python
from pydantic import ValidationError

try:
    RecordRequest(source="", data={})
except ValidationError as exc:
    print(exc.error_count())    # number of errors
    print(exc.errors())         # list of error dicts with loc, msg, type
```

- In FastAPI, Pydantic `ValidationError` on request bodies is automatically converted to a 422
  response — do not catch it in routes.
- For programmatic validation (background tasks, scripts), catch `ValidationError` explicitly.

---

## Anti-patterns

```python
# ✗ v1-style inner Config class
class MyModel(BaseModel):
    class Config:
        orm_mode = True

# ✗ mutable default (shared across all instances)
class Bad(BaseModel):
    tags: list = []

# ✗ constructor to convert ORM object
response = RecordResponse(**record.__dict__)

# ✗ bare @property for a field you want in JSON output—use @computed_field
class Bad(BaseModel):
    @property
    def label(self) -> str: ...

# ✗ raising TypeError in a validator
@field_validator("source")
@classmethod
def check(cls, v: str) -> str:
    if not v:
        raise TypeError("empty")   # use ValueError

# ✗ accessing self.other_field in a field_validator — use model_validator instead
@field_validator("end")
@classmethod
def after_start(cls, v: datetime) -> datetime:
    # self.start is not available here!
    ...
```
