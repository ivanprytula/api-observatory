# References & External Resources

Track: B — Engineering Execution


**Official documentation, tutorials, libraries, and tools** for each pillar.

---

## Pillar 1: Core Backend (Python + FastAPI)

### Python

- [Python 3.14 Docs](https://docs.python.org/3.14/) — Official
- [Real Python Async Guides](https://realpython.com/async-io-python/) — Excellent tutorials
- [Type Hints (PEP 484)](https://peps.python.org/pep-0484/)
- [asyncio Docs](https://docs.python.org/3/library/asyncio.html)

### FastAPI

- [FastAPI Official Docs](https://fastapi.tiangolo.com/) — Most important
- [FastAPI Best Practices](https://github.com/zhanymkanov/fastapi_best_practices)
- [Dependencies Deep Dive](https://fastapi.tiangolo.com/tutorial/dependencies/)

### Pydantic

- [Pydantic v2 Docs](https://docs.pydantic.dev/latest/)
- [Validators Guide](https://docs.pydantic.dev/latest/concepts/validators/)
- [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)

### Testing

- [pytest Docs](https://docs.pytest.org/) — De facto standard
- [pytest-asyncio](https://github.com/pytest-dev/pytest-asyncio)
- [httpx Docs](https://www.python-httpx.org/)

---

## Pillar 2: Database (PostgreSQL + SQLAlchemy)

### PostgreSQL

- [PostgreSQL Official Docs](https://www.postgresql.org/docs/current/) — Authoritative
- [PostgreSQL EXPLAIN](https://www.postgresql.org/docs/current/sql-explain.html)
- [MVCC Explained](https://www.postgresql.org/docs/current/mvcc-intro.html)
- [pg_stat_statements Extension](https://www.postgresql.org/docs/current/pgstatstatements.html)

### SQLAlchemy

- [SQLAlchemy 2.0 ORM Docs](https://docs.sqlalchemy.org/en/20/orm/)
- [Core Concepts](https://docs.sqlalchemy.org/en/20/orm/quickstart.html)
- [Async Usage](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)

### Alembic

- [Alembic Docs](https://alembic.sqlalchemy.org/) — Database migrations
- [Autogenerate Guide](https://alembic.sqlalchemy.org/en/latest/autogenerate.html)

### Query Optimization

- [Use The Index, Luke!](https://use-the-index-luke.com/) — Free book on indexing
- [PostgreSQL Query Performance](https://explain.depesz.com/) — Visualize plans online
- [pgBadger](https://pgbadger.readthedocs.io/) — Log analyzer

### Tools

- `pgAdmin` — Web UI for PostgreSQL
- `DBeaver` — SQL IDE (free community edition)
- `EXPLAIN.DEPESZ.COM` — Paste EXPLAIN output for visual analysis

---

## Pillar 3: Ops & Infrastructure

### Docker

- [Docker Docs](https://docs.docker.com/) — Official
- [Best Practices](https://docs.docker.com/develop/dev-best-practices/)
- [Dockerfile Reference](https://docs.docker.com/engine/reference/builder/)

### Git

- [Git Docs](https://git-scm.com/docs)
- [Conventional Commits](https://www.conventionalcommits.org/) — Commit message standard
- [GitHub Flow](https://guides.github.com/introduction/flow/)

### CI/CD

- [GitHub Actions Docs](https://docs.github.com/en/actions)
- [GitHub Actions Best Practices](https://docs.github.com/en/actions/guides)

### Cloud Platforms

- [Google Cloud Run](https://cloud.google.com/run/docs)
- [AWS ECS Fargate](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/launch_types.html)
- [Azure Container Instances](https://learn.microsoft.com/en-us/azure/container-instances/)

### Kubernetes

- [Kubernetes Docs](https://kubernetes.io/docs/)
- [Kubernetes Best Practices](https://kubernetes.io/docs/concepts/configuration/overview/)
- [Helm Package Manager](https://helm.sh/docs/)

### Infrastructure as Code

- [Terraform Docs](https://www.terraform.io/language)
- [AWS CDK (Python)](https://docs.aws.amazon.com/cdk/v2/guide/home.html)
- [CloudFormation (AWS)](https://docs.aws.amazon.com/cloudformation/)

### Tools

- `docker compose` — Local dev (built into Docker Desktop)
- `kubectl` — Kubernetes CLI
- `helm` — Kubernetes package manager
- `OrbStack` or `Colima` — Lightweight Docker replacements
- `act` — Run GitHub Actions locally

---

## Pillar 4: Observability

### Logging

- [python-json-logger](https://github.com/madzak/python-json-logger)
- [structlog](https://www.structlog.org/en/stable/) — More advanced logging
- [Datadog Logs](https://docs.datadoghq.com/logs/)

### Metrics

- [Prometheus Docs](https://prometheus.io/docs/)
- [Grafana Docs](https://grafana.com/docs/grafana/latest/)
- [prometheus-fastapi-instrumentator](https://github.com/trallnag/prometheus-fastapi-instrumentator)

### Tracing

- [OpenTelemetry Docs](https://opentelemetry.io/docs/)
- [Jaeger](https://www.jaegertracing.io/docs/)
- [Zipkin](https://zipkin.io/)

### APM Platforms

- [Datadog APM](https://docs.datadoghq.com/tracing/)
- [New Relic](https://newrelic.com/)
- [Elastic APM](https://www.elastic.co/apm)

### Tools

- `prometheus` — Metrics storage
- `grafana` — Visualization
- `jaeger` — Distributed tracing
- `loki` — Log aggregation (lightweight alternative to ELK)

---

## Pillar 5: Security

### Authentication & Authorization

- [FastAPI Security](https://fastapi.tiangolo.com/tutorial/security/)
- [python-jose (JWT)](https://github.com/mpdavis/python-jose)
- [PyJWT](https://pyjwt.readthedocs.io/)
- [OAuth 2.0 Docs](https://oauth.net/2/)

### Security Best Practices

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [OWASP API Top 10](https://owasp.org/www-project-api-security/)
- [NIST Cybersecurity Framework](https://www.nist.gov/cyberframework)

### Secret Management

- [HashiCorp Vault](https://www.vaultproject.io/)
- [AWS Secrets Manager](https://aws.amazon.com/secrets-manager/)
- [Google Cloud Secret Manager](https://cloud.google.com/secret-manager)
- [1Password for Teams](https://1password.com/teams/)

### Secret Scanning

- [gitleaks](https://github.com/gitleaks/gitleaks)
- [truffleHog](https://github.com/trufflesecurity/trufflehog)

### Tools

- `bruteforce-wallets` — Test weak credentials
- `OWASP ZAP` — Security scanning tool
- `sqlmap` — SQL injection testing

---

## Pillar 6: AI / LLM Integration

### LLM APIs

- [OpenAI Python SDK](https://github.com/openai/openai-python)
- [Anthropic Python SDK](https://github.com/anthropics/anthropic-sdk-python)
- [Google Vertex AI](https://cloud.google.com/vertex-ai/docs)

### Agent Frameworks

- [LangChain](https://langchain.com/) — Most popular
- [LangGraph](https://langchain-ai.github.io/langgraph/) — Stateful agents
- [CrewAI](https://docs.crewai.com/) — Multi-agent orchestration

### RAG

- [LangChain RAG Guide](https://python.langchain.com/docs/use_cases/question_answering/)
- [pgvector](https://github.com/pgvector/pgvector) — Vector storage in PostgreSQL
- [Chroma](https://docs.trychroma.com/) — Vector database
- [Pinecone](https://www.pinecone.io/) — Hosted vector database
- [Weaviate](https://weaviate.io/) — GraphQL vector search

### Evaluation

- [RAGAS](https://ragas.io/) — RAG evaluation metrics
- [DeepEval](https://github.com/confident-ai/deepeval)

### MCP

- [Model Context Protocol Docs](https://modelcontextprotocol.io/)
- [MCP Client Example](https://github.com/anthropics/mcp-client)

### Tools

- `ollama` — Run local LLMs offline
- `vLLM` — Optimize LLM serving
- `llamaindex` — Index external data for RAG

---

## Pillar 7: Data & ETL

### Data Processing

- [Pandas Docs](https://pandas.pydata.org/docs/)
- [Polars](https://docs.pola.rs/) — Modern, faster alternative
- [DuckDB](https://duckdb.org/) — In-process SQL database

### Web Scraping

- [BeautifulSoup](https://www.crummy.com/software/BeautifulSoup/bs4/doc/)
- [Scrapy](https://scrapy.org/) — Full framework
- [Playwright Python](https://playwright.dev/python/)
- [Selenium](https://selenium-python.readthedocs.io/)

### Task Queues

- [Celery](https://docs.celeryproject.io/) — Most popular
- [arq](https://arq-docs.helpmanual.io/) — Async-native (simpler)
- [RQ (Cache Queue)](https://python-rq.org/)

### Workflow Orchestration

- [Prefect](https://docs.prefect.io/) — Modern DAG orchestration
- [Airflow](https://airflow.apache.org/docs/) — Industry standard
- [Dask](https://dask.org/) — Distributed computing

### Data Validation

- [Great Expectations](https://greatexpectations.io/) — Data quality checks
- [Pandera](https://pandera.readthedocs.io/) — Schema validation for pandas

### Tools

- `fake-useragent` — Random user-agents for scraping
- `2captcha-python` — CAPTCHA solving
- `requests-html` — Simple scraping (requests + HTML parsing)

---

## Cross-Cutting Tools

### IDE & Code Quality

- [VS Code](https://code.visualstudio.com/) — Lightweight IDE
- [PyCharm](https://www.jetbrains.com/pycharm/) — Full-featured IDE
- [Ruff](https://github.com/astral-sh/ruff) — Fast linter + formatter
- [Black](https://black.readthedocs.io/) — Code formatter
- [mypy](http://mypy-lang.org/) — Static type checker

### Package Management

- [uv](https://github.com/astral-sh/uv) — Fast Python package manager (recommended)
- [pip](https://pip.pypa.io/) — Standard Python package manager
- [poetry](https://python-poetry.org/) — Dependency lock (nice alternative to pip)

### Profiling & Debugging

- [py-spy](https://github.com/benfred/py-spy) — CPU profiler (sampling)
- [Pyinstrument](https://github.com/jorenretel/Pyinstrument) — Deterministic profiler
- `pdb` — Python debugger (built-in, use `breakpoint()`)
- [VSCode Debugger](https://code.visualstudio.com/docs/python/debugging)

### Load Testing

- [k6](https://k6.io/) — Load testing (simple JavaScript)
- [locust](https://locust.io/) — Load testing (Python-based)
- [Apache JMeter](https://jmeter.apache.org/) — Enterprise load testing

### API Testing

- [Postman](https://www.postman.com/) — API testing GUI
- [REST Client (VS Code Extension)](https://marketplace.visualstudio.com/items?itemName=humao.rest-client) — Lightweight alternative
- `curl` — Command-line HTTP testing

---

## Learning Resources

### Courses

- [Real Python](https://realpython.com/) — Best Python tutorials online
- [Full Stack Python](https://www.fullstackpython.com/) — comprehensive reference
- [Udemy FastAPI Course](https://www.udemy.com/course/build-web-apis-with-fastapi/) — Practical
- [LinkedIn Learning](https://www.linkedin.com/learning/) — Video courses

### Books

- "Database Internals" by Alex Petrov
- "System Design Interview" by Designing Data-Intensive Applications
- "The Pragmatic Programmer"

### YouTube Channels

- [Techwith Tim](https://www.youtube.com/channel/UC4JX40jDee_tINbkjycV4CQ) — Python tutorials
- [Fireship](https://www.youtube.com/c/Fireship) — Quick tech explanations
- [Hussein Nasser](https://www.youtube.com/c/HusseinNasser) — Systems design + networking

### Communities

- [r/Python](https://www.reddit.com/r/Python/) — Reddit community
- [FastAPI Discord](https://discord.gg/VQjSZaeJmf) — Community chat
- [Stack Overflow](https://stackoverflow.com/) — Q&A

---

## Quick Command Reference

```bash
# Python
uv venv                           # Create venv
uv sync                           # Install from lockfile
uv add package_name               # Add package
ruff check . && ruff format .     # Lint + format

# FastAPI
uv run uvicorn app.main:app --reload

# Testing
uv run pytest tests/ -v           # Run tests
uv run pytest tests/ --cov=app    # With coverage

# Database
alembic revision --autogenerate -m "reason"
alembic upgrade head

# Docker
docker compose up --build
docker compose logs ingestor
docker exec -it <container> bash

# Git
git commit -m "feat: add cursor pagination"
git push origin feature/branch

# PostgreSQL
psql -U postgres -d data_pipeline
\dt                               # List tables
\d observations                        # Describe table
```

---

**Last updated**: April 2, 2026
