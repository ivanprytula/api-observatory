# Middle-Tier Grind Tracking — Output Format & Usage Guide

Track: E — Archive and Historical Snapshots

**What is this?** A structured 10-week interview prep program that bridges coding skills → system design competence. The output document is your **weekly progress report**.

---

## Quick Summary

The instruction (**[.github/instructions/middle-tier-grind-tracking.md](../../.github/instructions/middle-tier-grind-tracking.md)**) defines:

- **10 weeks** (70 days) organized into 7 phases (events → scrapers → docker+ci → AI+vectors → testing → database → security → terraform)
- **7 core interview questions** (one per phase) with follow-ups and design scenarios
- **Success metrics**: Code commits, tests passing, portfolio items, SQL patterns, pytest fixtures, async gotchas
- **Weekly cadence**: Every 2 weeks, update a progress report (this file)

---

## The Output Document Structure

Every **2-week phase completion** produces **ONE** output document (like `docs/weekly-progress-phase-2.md`) containing:

### 1. Phase Overview

- **Goal**: What you're building (e.g., "Design scraper for 100K URLs")
- **Status**: ✅ Complete, 🟡 In Progress, ❌ Blocked

### 2. Weekly Metrics

A table comparing goals vs actual:

| Metric               | Goal | Actual | Status |
| -------------------- | ---- | ------ | ------ |
| Core Q answered cold | 1/1  | ✅ 1/1 | ✅     |
| Code commits         | 8–15 | 12     | ✅     |
| Tests passing        | 100% | 70%    | 🟡     |

### 3. Interview Readiness (Most Important)

For each interview question:

- **Cold answer**: Full response (~3 min) you'd give in real interview
- **Follow-ups**: Prepared answers to 2 follow-up questions
- **Design scenario**: Worked through a design problem
- **Interview signals**: What this demonstrates (thinking, tradeoffs, practical knowledge)

### 4. Code Artifacts

Links to what you implemented:

- `app/scrapers/__init__.py` — ScraperFactory
- `app/storage/mongo.py` — Motor async client
- `app/routers/scraper.py` — Endpoint

### 5. Portfolio Item

Link to portfolio-phase-2-scrapers.md:

- What I built (metrics)
- Interview questions (Q + sketch answers)
- Key learning (fail-open architecture)
- Why it matters (production patterns)

### 6. ADR (Architecture Decision Record)

See Phase 2 Scraper Integration notes in this guide:

- Decision statement
- Rationale + trade-offs
- Consequences (positive/negative)

### 7. Learning Insights

- **What surprised me**: Unexpected findings
- **Mistakes avoided**: Problems you dodged
- **Concept clarity**: Confusions resolved

### 8. Next Phase Preview

What Phase 3 will focus on (start mental preparation):

- Questions to research
- Skills to strengthen
- Architecture patterns to study

---

## How to Use This Template

### Every 2 Weeks (Phase Completion)

**Friday EOD** (end of phase):

1. Create new file: `docs/weekly-progress-phase-{N}.md`
2. Copy structure from `weekly-progress-phase-2.md`
3. Fill in:
   - Phase goals
   - Metrics (commits, tests, coverage)
   - Interview questions (write cold answer like you're in room)
   - Code artifacts (links to implementation)
   - Portfolio item link
   - ADR link
   - Learning insights
4. Commit & push
5. Share on LinkedIn (optional): Summary of key learnings

### Daily (While Building)

- **Write down surprises** → Add to "Learning Insights" at end of phase
- **Practice core Q aloud** → Record yourself, listen back
- **Read code carefully** → Notice patterns, ADR-ify decisions
- **Log experiments** → What broke first time, why, how fixed

### End of 10 Weeks

You have:

- 7 portfolio items (one per phase)
- 7 ADRs (decision rationale documented)
- 7 weekly progress reports (proof of execution)
- 40+ SQL patterns implemented
- 10+ pytest fixtures written
- Deep understanding of 7 production patterns

---

## Interview Prep Strategy

This template is **designed for interview readiness**. Each component maps to interview questions:

| Output Component   | Interview Question                          | How It Helps                                  |
| ------------------ | ------------------------------------------- | --------------------------------------------- |
| Core Q Cold Answer | "Design a scraper for 100K URLs"            | Proves you can think on your feet             |
| Follow-up Answers  | "Rate limiting strategy?"                   | Shows deep understanding                      |
| Design Scenario    | "Scraper is failing 30% of time — diagnose" | Proves problem-solving, not just coding       |
| Code Artifacts     | "Walk me through your code"                 | Concrete evidence of ability                  |
| Portfolio Item     | "Tell me about a project"                   | Narrative that impresses (metrics + learning) |
| ADR                | "How do you make design decisions?"         | Shows architectural thinking                  |
| Learning Insights  | "What's something you learned?"             | Signals growth mindset                        |

**Interviewer mindset**: "Can this person ship? Do they think about tradeoffs? Do they learn from mistakes?"

This template answers all 3 yes.

---

## Example: Phase 2 (Scrapers)

**Output file**: `docs/weekly-progress-phase-2.md`

**Sections**:

1. ✅ **Phase goal**: "Design scraper for 100K URLs without ban"
2. ✅ **Metrics**: 12 commits, 70% tests, all interview Qs ready
3. ✅ **Interview cold answer**: Full response (~3 min) with structured thinking
4. ✅ **Two follow-ups worked through**: Rate limiting, concurrent vs sequential
5. ✅ **Design scenario**: Timeouts on 30% of requests — diagnosed + fixed
6. ✅ **Code links**: app/scrapers/**init**.py, app/storage/mongo.py, app/routers/scraper.py
7. ✅ **Portfolio**: docs/portfolio-phase-2-scrapers.md (what I built, why it matters, metrics)
8. ✅ **ADR**: Phase 2 (Factory pattern, Motor async, fail-open)
9. ✅ **Learning**: Fail-open is hidden complexity; Semaphore ≠ rate limiter; 70% test coverage is OK for MVP
10. ✅ **Next phase**: Phase 3 is semantic search — start thinking about embedding trade-offs

---

## Success Metrics (Track Weekly)

| Metric                             | Target                | How to Measure                            |
| ---------------------------------- | --------------------- | ----------------------------------------- |
| Interview Q answered cold per week | 1/phase               | Record yourself answering, review later   |
| Code commits/phase                 | 8–15                  | `git log --oneline --since='2 weeks ago'` |
| Tests passing                      | 100%                  | `pytest tests/ -v`                        |
| SQL patterns implemented           | 40/40 across 10 weeks | Checkboxes in phase report                |
| Pytest fixtures demonstrated       | 10/10 across 10 weeks | Checkboxes in phase report                |
| Async gotchas with examples        | 5/5 across 10 weeks   | Reference in phase report                 |
| Portfolio items written            | 1/phase               | Link to docs/portfolio-phase-{N}.md       |
| ADRs completed | 1/phase | Link to docs/02-architecture/adr/{N}-{title}.md |

---

## Why This Works

1. **Output = Accountability**: Writing down metrics makes progress visible
2. **Interview Prep = Active**: Cold answers force you to structure thinking
3. **Portfolio = Proof**: By week 10, you have concrete evidence (7 projects + 7 ADRs)
4. **Reflection = Learning**: Mistakes + insights documented = prevents repeat errors
5. **Cadence = Consistency**: Every 2 weeks, not chaotic

---

## Anti-Patterns to Avoid

❌ **"I'll write the portfolio item later"** → Write during, collect metrics as you go
❌ **"I'll practice interview Qs just before interviews"** → Practice cold each week; get comfortable
❌ **"I don't need an ADR, code is self-documenting"** → ADRs document *why*, not what
❌ **"100% test coverage isn't realistic"** → Aim high; 70%+ is good; document gaps
❌ **"One weekly report is enough"** → The *pattern* matters; consistency signals reliability

---

## Customization

**Adjust for your context**:

- **Time**: If 10 weeks is too fast, spread to 16 weeks (2 per phase instead of 1)
- **Phases**: Reorder based on your goal (prioritize distributed systems? Start with Phase 1; security? Start with Phase 6)
- **Patterns**: Change SQL/pytest patterns based on your stack (Go? Replace pytest with table tests; no SQL? Add query trade-offs)
- **Portfolio**: Tailor narrative to company you're targeting (startup? Emphasize speed; FAANG? Emphasize scale)

---

## Related Files

- **Instruction**: [.github/instructions/middle-tier-grind-tracking.md](../../.github/instructions/middle-tier-grind-tracking.md)
- **Portfolio Template**: portfolio-phase-2-scrapers.md
- **Phase 2 Output**: `docs/weekly-progress-phase-2.md` ← *Example*
- **Phase 2 Portfolio**: portfolio-phase-2-scrapers.md
- **Phase 2 ADR**: (not yet formalized)

---

**Next phase?** Duplicate `weekly-progress-phase-2.md` → `weekly-progress-phase-3.md` → Fill in your Phase 3 findings. 🚀
