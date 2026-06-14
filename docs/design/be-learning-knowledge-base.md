# Backend Learning Knowledge Base

Track: C — Architecture and Platform Strategy


Companion learning resource for **"Milestone Checklist: Junior → Strong Middle/Senior"** journey.

All materials organized by **7 pillars** — each expands on the checklist with practical examples, gotchas, decision trees, and code snippets.

---

## Navigation

### 📚 Pillars (Core Learning)

1. **[Pillar 1: Core Backend](pillar-1-core-backend.md)** — Python, FastAPI, Pydantic, Testing
2. **[Pillar 2: Database](pillar-2-database.md)** — PostgreSQL, SQLAlchemy, Alembic, Query Optimization
3. **[Pillar 3: Ops & Infrastructure](pillar-3-ops-infrastructure.md)** — Docker, CI/CD, Cloud, Kubernetes
4. **[Pillar 4: Observability](pillar-4-observability.md)** — Logging, Metrics, Tracing
5. **[Pillar 5: Security](pillar-5-security.md)** — Auth, Input Validation, API Hardening
6. **[Pillar 6: AI / LLM](pillar-6-ai-llm.md)** — LLM APIs, RAG, Agent Frameworks
7. **[Pillar 7: Data & ETL](pillar-7-data-etl.md)** — Pandas, ETL Patterns, Scraping

### ⚠️ [Common Gotchas & Pitfalls](../dev/gotchas.md)

Things that trip up developers, solutions, and how to spot them.

### 🔗 [References & External Resources](../setup/references.md)

Official docs, tutorials, tools, and where to learn more.

---

## How to Use This Knowledge Base

### 1. **Learning Path**

Start with **Pillar 1**, work through in order. Each pillar builds on prior knowledge.

### 2. **Quick Lookup**

Use IDE global search (VS Code: `Ctrl+Shift+F` or `Cmd+Shift+F` on Mac) to find:

- Specific pattern ("Cursor-based pagination")
- Technology you want to learn ("asyncio.gather")
- Common error (search "[gotchas]")

### 3. **Project-Driven Learning**

Each pillar doc links to specific additions in `api-observatory`. Build them:

```text
Week 1: Pillar 1 + 2 (Foundation)
Week 2: Pillar 3 Foundation + Pillar 1 Middle tier
Week 3: Pillar 3 Middle tier + Pillar 4
Week 4: Pillar 5 + 6 foundations
Weeks 5-6: Advanced tiers + integration
```

### 4. **Validate Your Learning**

Each pillar has a **"You should be able to"** section at the end. Check yourself:

- Can you explain it without the docs?
- Can you implement it from memory?
- Can you debug it when it breaks?

---

## Document Structure

Each pillar follows this pattern:

```text
## Pillar X: [Name]

### Foundation (🟢)
- Concept A
  - What it is
  - When to use
  - Example (with code)
  - Common mistakes

### Middle Tier (🟡)
- Advanced pattern
  - Theory
  - Trade-offs
  - Real-world scenario
  - How to implement

### Senior Differentiators (🔴)
- Cutting-edge topic
  - When it matters
  - Prerequisites
  - Further reading

### Decision Tree
"When should I choose X vs Y?"

### You Should Be Able To
Checklist of competencies by end of pillar.
```

---

## Coverage Map

| Pillar | JD Coverage | Tier |
| --- | --- | --- |
| 1 + 2 + 3 (Foundation) | 90-95% Junior | 🟢 |
| 1-3 (Middle) + 4 | 90%+ Middle | 🟡 |
| 4 + 5 + 6 + Cloud | ~60% Middle+ | 🟡 |
| K8s + Tracing + Agents + RLS | 50-60% Senior | 🔴 |

---

## Sync with Milestone Checklist

- Checklist = actionable, deliverable tasks
- Docs = theory, patterns, contexts, gotchas

Use together:

- **Read the pillar doc** to understand the concept
- **Check the checklist** for what to build
- **Build in `api-observatory`** to prove it
- **Reference docs again** when you get stuck

---

## Contributing / Updating

When you learn something new:

1. Add it to the relevant pillar doc
2. Update "You Should Be Able To" section
3. Link it from [gotchas.md](../dev/gotchas.md) if it's a common mistake
4. Add external resources to [references.md](../setup/references.md)

---

**Last updated**: April 2, 2026
**Tied to**: Milestone Checklist v1 + api-observatory project (formerly data-pipeline-async)
