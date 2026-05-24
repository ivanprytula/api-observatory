---
name: api-docs-standards
description: "Apply to: routes (services/**/routers/*.py), schemas (services/**/schemas.py), GraphQL (services/**/graphql/schema.py). Enforces OpenAPI and GraphQL documentation completeness for QA, AQA, and UAT audiences."
applyTo: "services/**/routers/*.py, services/**/schemas.py, services/**/graphql/schema.py, libs/**/*.py"
---

# API Documentation Standards

## OpenAPI (FastAPI REST)

### Pydantic schemas

Every public field on a request or response model MUST have `Field(description="...")`.

Rules:
- Describe constraints and semantics, not the field name.
- Add `examples=[...]` for scalar fields where practical.
- Add `model_config = {"json_schema_extra": {"examples": [...]}}` to every request schema with one realistic payload.

```python
class RecordRequest(BaseModel):
    model_config = {
        "json_schema_extra": {
            "examples": [{"source": "sensor.prod", "data": {"temp": 22.5}, "tags": ["iot"]}]
        }
    }

    source: str = Field(
        ...,
        description="Hostname, service name, or sensor ID. Cannot be a loopback address.",
        examples=["sensor.prod.us-east-1"],
    )
```

### Route decorators

Every route should define:
1. `summary="Verb-object phrase"`.
2. `responses=` including reachable non-2xx status codes.

```python
@router.get(
    "/{record_id}",
    summary="Get a record by ID",
    response_model=RecordResponse,
    responses={**_R404},
)
```

### Shared response dicts

Define reusable response constants in each router, for example `_R401`, `_R403`, `_R404`, `_R409`, `_R422`, `_R429`, and compose with spread syntax:

```python
responses={**_R404, **_R422}
```

### openapi_tags in main.py

Define `_OPENAPI_TAGS` before `FastAPI()` and pass via `FastAPI(openapi_tags=_OPENAPI_TAGS, ...)` with one descriptive entry per tag.

## GraphQL (Strawberry)

### Type fields

Every field in `@strawberry.type` should use `strawberry.field(description="...")`.

```python
@strawberry.type
class DataSourceType:
    id: strawberry.ID = strawberry.field(description="Auto-generated primary key.")
    is_active: bool = strawberry.field(description="True if ingestion is enabled.")
```

For nullable defaults, keep both default and description:

```python
ts: str | None = strawberry.field(default=None, description="ISO 8601 timestamp, or null.")
```

### Query/Subscription arguments

Wrap resolver arguments with `Annotated[T, strawberry.argument(description="...")]`.

```python
async def data_sources(
    self,
    is_active: Annotated[bool | None, strawberry.argument(description="Filter by active state.")] = None,
    limit: Annotated[int, strawberry.argument(description="Max results (1-200). Default: 50.")] = 50,
) -> list[DataSourceType]:
```

### Resolver descriptions

Use `@strawberry.field(description="...")` on query resolvers so descriptions appear in GraphiQL schema docs.

## Maintenance checklist

When adding a REST endpoint:
- [ ] `summary=` set on decorator
- [ ] `responses=` includes all non-2xx paths
- [ ] Request schema fields include `Field(description=...)`
- [ ] Request schema has `json_schema_extra` example payload

When adding a GraphQL type or resolver:
- [ ] Every type field uses `strawberry.field(description="...")`
- [ ] Every query/subscription argument uses `Annotated[..., strawberry.argument(description="...")]`
- [ ] Resolver has `@strawberry.field(description="...")`
