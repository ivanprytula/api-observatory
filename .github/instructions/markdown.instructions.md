---
name: markdown-standards
description: "Apply to: docs, READMEs (**/*.md). Enforces clear hierarchy, consistent formatting, linked code references, and best practices for technical documentation."
applyTo: "docs/**/*.md, **/*.md, README.md"
---

# Markdown Standards

## Document Structure

### Hierarchy & Headings
- Use H1 (`#`) for document title (only one per file).
- Use H2 (`##`) for major sections.
- Use H3 (`###`) for subsections.
- Avoid skipping heading levels (e.g., don't jump from H2 to H4).

### Example Structure
```markdown
# Scenario 1: Monolith Scaling Bottleneck

## Overview
[Brief description of what this scenario teaches]

## Learning Objectives
- Understand vertical vs horizontal scaling
- Measure bottlenecks with `k6` load testing

## Prerequisites
- Docker, Docker Compose, Python 3.14+

## Getting Started
[Step-by-step setup]

## Architecture
[Diagram, component descriptions]

## Phase 1: Baseline
[Expected behavior at normal load]

## Phase 2: Breaking Point
[How to trigger failure with k6]

## Phase 3: Fix (Pattern Application)
[How to apply the pattern and improve]

## Metrics & Analysis
[What to measure, expected improvements]

## Cleanup
[How to tear down the scenario]

## Further Reading
[Links to related patterns, docs]
```

---

## Formatting & Style

### Text Formatting
- **Bold**: `**important**` for emphasis.
- **Code**: `` `code` `` for inline code (function names, variables, commands).
- **Inline links**: `[Text](url)` for readability.
- **Lists**: Consistent bullet style (use `-` for unordered, `1.` for ordered).

### Code Blocks
```markdown
Use triple backticks with language identifier for syntax highlighting:

\`\`\`python
async def get_user(user_id: int) -> User:
    return await db.get(User, user_id)
\`\`\`

\`\`\`bash
docker-compose up --build
\`\`\`

\`\`\`yaml
services:
  web:
    image: python:3.14
\`\`\`
```

### Tables
```markdown
| Column 1 | Column 2 | Column 3 |
|----------|----------|----------|
| Value 1  | Value 2  | Value 3  |
| Value 4  | Value 5  | Value 6  |
```

---

## Documentation Best Practices

### README.md Structure (for Scenarios)
```markdown
# Scenario 1: Monolith Scaling Bottleneck

One-liner describing the learning objective.

## Quick Start

### Prerequisites
- Docker, Docker Compose
- Python 3.14+
- k6 (for load testing)

### Spin Up
```bash
cd src/scenario_1_monolith/scripts
./start.sh
```

### Check Health
\`\`\`bash
curl http://localhost:8000/health
\`\`\`

## Architecture Overview

[Diagram or ASCII art showing services and flow]

## Phases

### Phase 1: Baseline (Unoptimized)
Expected behavior at normal load. Metrics: latency ~50ms, throughput ~200 req/s.

### Phase 2: Breaking Point
Run load test with k6:
\`\`\`bash
k6 run scripts/load_test.js
\`\`\`
Expected failure: latency spikes to 5000ms+, errors appear at ~50 concurrent users.

### Phase 3: Fix (Add Redis Cache)
Apply caching pattern:
\`\`\`bash
# Uncomment cache logic in backend/app/api.py
# Restart services
docker-compose restart web cache
\`\`\`
Expected improvement: latency drops to 50ms, throughput increases to 2000 req/s.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/users` | List all users |
| GET | `/users/{id}` | Get user by ID |
| POST | `/users` | Create user |

## Cleanup
\`\`\`bash
./scripts/cleanup.sh
\`\`\`

## Further Reading
- [12-Factor App on Caching](https://12factor.net/)
- [Redis Best Practices](https://redis.io/docs/)
```

### Technical Writing Tips
- **Be concrete**: Use examples, metrics, commands (not abstractions).
- **Prioritize readability**: Use short paragraphs, bullet points, and clear headings.
- **Link liberally**: Reference related docs, code files, external resources.
- **Show, don't tell**: Include commands, output, and expected results.
- **Explain the "why"**: Help readers understand learning objectives.

---

## Links & References

### Internal Links
Link to related docs:
```markdown
See [Python Code Standards](./.github/instructions/python.instructions.md) for async patterns.

Refer to [Getting Started Guide](../docs/QUICKSTART.md) for setup instructions.
```

### Code References
Link to specific files or lines in the codebase (workspace-relative):
```markdown
The database setup is in [app/database.py](../../app/database.py).

See the async session pattern in [database.py:get_db()](../../app/database.py#L25-L35).
```

### External Links
```markdown
Learn more in the [12-Factor App](https://12factor.net/) guide.
See [ByteByteGo's Caching Guide](https://bytebytego.com/guides/).
```

---

## Special Formatting

### Callout Blocks
```markdown
> **Note**: This is important context readers should know.

> **Warning**: This could break things if done incorrectly.

> **Tip**: A helpful suggestion or best practice.
```

### Code Diff
```markdown
\`\`\`diff
- # Old way (no caching)
+ # New way (with Redis cache)
  result = db.query(User).filter(...).all()
\`\`\`
```

---

## Common Pitfalls

- **Inconsistent heading levels**: Skip from H2 to H4.
- **No code blocks**: Use inline code for everything, making wall-of-text.
- **Dead links**: Broken internal references (keep links updated during refactoring).
- **Poor table formatting**: Misaligned columns, missing headers.
- **Unclear examples**: Examples that don't map to actual code or commands.

## MD036 Guardrail (Docs Quality Hook)

The repository pre-commit hook `docs-quality-markdown` fails on emphasis-only headings.

- Never put a standalone bold line that acts like a heading, for example:
  - `**Manual method:**`
  - `**Settings:**`
  - `**Notes:**`
- Replace these with real headings (`###`, `####`) or convert them into plain paragraph text.
- If a label is short and does not deserve a section, keep it inline in a sentence instead of a standalone line.

Pre-flight check before finalizing markdown edits:

1. Scan for standalone lines matching `**...**`.
2. Convert each to a markdown heading or inline sentence.
3. Ensure heading levels are consistent after conversion.
