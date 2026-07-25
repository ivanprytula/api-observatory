# AI Learning Session Checklist

Use AI as a repository navigator, reviewer, and debugging partner without outsourcing project
ownership.

## Topic Lookup

Ask: `Where is <topic> in this project?`

The agent must follow the lookup protocol in [`AGENTS.md`](../../AGENTS.md): status, exact
evidence, current behavior, missing evidence, tradeoff, scale trigger, bounded exercise, and
interview questions. It must inspect current files before answering; archived plans do not prove
current behavior.

## Critical-Flow Session

Limit one learning session to three production files and two test files. Ask the agent to follow:

`purpose → architecture → code → data → dependencies → failure → proof → tradeoff`

Finish with:

1. A verbal teach-back in your own words, without generated notes.
2. One debugging scenario where the agent withholds the answer initially.
3. One focused proof command.
4. Any correction to the canonical topic index if repository evidence changed.

## Small Change Prompt

```text
Goal: <one measurable behavior>.
Practical value: <user failure or cost reduced>.
Evidence to inspect: <up to three production files and two tests>.
Failure to exercise: <one bounded scenario>.
Done when: <focused test, signal, and rollback statement>.
Constraints: preserve contracts; no new service or dependency without a measured trigger.
```

Never paste secrets or private environment values. Prefer exact paths, focused output, and small
reviewable changes.
