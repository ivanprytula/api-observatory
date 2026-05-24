---
name: toml-standards
description:
    'Apply to: pyproject.toml, tool configuration files (*.toml). Enforces semantic versioning, clear
    sections, and best practices for dependency and tool configuration.'
applyTo: 'pyproject.toml, **/pyproject.toml, **/*.toml'
---

# TOML Code Standards

## Structure & Formatting

### Indentation & Syntax

- **Indentation**: 2 spaces for nested tables.
- **Comments**: Use `#` to explain non-obvious settings.
- **Quotes**: Always use double quotes for string values.
- **Keys**: Lowercase with dashes for readability (e.g., `python-version`, `max-line-length`).

---

## pyproject.toml (Python Projects)

### Project Metadata

```toml
[project]
name = "architecture-patterns-lab"
version = "0.1.0"
description = "Hands-on distributed systems learning platform via Docker Compose"
authors = [
    { name = "Ivan P", email = "ivan@example.com" }
]
readme = "README.md"
license = { text = "MIT" }
requires-python = ">=3.14"
keywords = ["architecture", "distributed-systems", "docker", "fastapi"]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Intended Audience :: Education",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3.14",
]
```

### Dependencies

```toml
[project]
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",
    "pydantic-settings>=2.5.0",
    "sqlalchemy[asyncio]>=2.0.0",
    "asyncpg>=0.29.0",
    "python-json-logger>=2.0.0",
    "httpx>=0.27.0",
    "redis>=5.0.0",
]
```

### Development Dependencies

```toml
[dependency-groups]
dev = [
    "ruff>=0.6.0",
    "ty>=0.0.23",
    "pytest>=8.0.0",
    "pytest-asyncio>=0.24.0",
    "pytest-cov>=4.0.0",
    "bandit>=1.7.0",
    "pre-commit>=4.0.0",
]

docs = [
    "mkdocs>=1.5.0",
    "mkdocs-material>=9.0.0",
]

optional = [
    "diagrams>=0.23.0",  # For architecture diagrams
]
```

### Tool Configuration (Ruff)

```toml
[tool.ruff]
line-length = 119
target-version = "py314"
include = ["src/**/*.py"]

[tool.ruff.lint]
select = [
    "E",    # pycodestyle errors
    "W",    # pycodestyle warnings
    "F",    # pyflakes
    "I",    # isort
    "B",    # flake8-bugbear
    "UP",   # pyupgrade
    "SIM",  # flake8-simplify
]
ignore = []

[tool.ruff.format]
quote-style = "double"
indent-style = "space"
line-ending = "lf"

[tool.ruff.isort]
known-first-party = ["src"]
```

### Tool Configuration (Type Checker)

```toml
[tool.ty]
strict = true
```

### Tool Configuration (Pytest)

```toml
[tool.pytest.ini_options]
minversion = "8.0"
testpaths = ["tests"]
python_files = ["test_*.py", "*_test.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
asyncio_mode = "auto"
addopts = "-v --cov=src --cov-report=html --cov-report=term-missing"
```

### Tool Configuration (Bandit - Security)

```toml
[tool.bandit]
exclude_dirs = [".venv", "tests", "docs"]
skips = ["B101"]  # B101 is assert - common for testing
```

### URLs & Links

```toml
[project.urls]
Homepage = "https://github.com/user/architecture-patterns-lab"
Documentation = "https://architecture-patterns-lab.pages.dev"
Repository = "https://github.com/user/architecture-patterns-lab.git"
"Bug Tracker" = "https://github.com/user/architecture-patterns-lab/issues"
```

---

## Best Practices

### Semantic Versioning

Use `MAJOR.MINOR.PATCH` format:

- `MAJOR`: Breaking changes.
- `MINOR`: Backward-compatible new features.
- `PATCH`: Backward-compatible bug fixes.

Example: `0.1.0` (pre-release), `1.0.0` (stable), `1.1.0` (feature), `1.1.1` (patch).

### Dependency Pinning

- Use `>=` for minimum versions that are likely to be stable.
- Avoid `==` pinning in libraries (use in `pyproject.toml` only for applications).
- Use `<` for major version upper bounds if needed (e.g., `fastapi<1.0`).

```toml
# Good for applications (tight pinning):
dependencies = [
    "fastapi==0.115.0",
    "asyncpg==0.29.0",
]

# Good for libraries (flexible):
dependencies = [
    "fastapi>=0.115.0,<1.0",
    "asyncpg>=0.29.0",
]
```

### Optional Dependencies

Group optional dependencies for specific use cases:

```toml
[dependency-groups]
dev = [...]      # Development tools
docs = [...]     # Documentation generation
optional = [...] # Optional features

# Usage: pip install package[dev,docs]
```

### Exclude Unnecessary Files

```toml
[tool.ruff]
include = ["src/**/*.py"]  # Only lint application code

[tool.bandit]
exclude_dirs = [".venv", "tests", "docs", "__pycache__"]
```

---

## Common Pitfalls

- **Mismatched versions**: `requires-python = ">=3.14"` but dependencies specify older versions.
- **Unquoted strings**: Numeric versions unquoted, breaking TOML parsing.
- **Missing metadata**: No description, url, or license (useful for publishing to PyPI).
- **Bloated dependency groups**: Too many tools in `dev`; consider splitting into `lint`, `test`,
  `docs`.
