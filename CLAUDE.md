# CLAUDE.md

## Read First

Before making product or architecture decisions, read:

1. `PRD.md`
2. `AGENTS.md`

This repo now includes a working Next.js frontend and FastAPI backend for barebones microsite generation. Treat it as an MVP scaffold, not final production architecture.

## Product Intent

We are building an agentic sales collateral microsite system for ABX-style outreach, with the microsite generation track currently prioritized.

Current working flow:

1. Enter manual prospect names.
2. Generate microsites in batch.
3. Persist them with unique slugs.
4. Inspect generation runs and latency in the observability surface.
5. Open each microsite on its own route.

## Hard Constraints

- Optimize for speed to first demo.
- Keep the system configurable and agentic.
- Default to framework-agnostic decisions unless the user explicitly chooses a stack.
- Do not commit secrets.
- Use OpenAI for microsite creation on the backend.
- Use LangGraph for the generation workflow and observability structure.
- Do not invent private prospect facts or unsupported pain points.

## MVP Assumptions

- Minimal required input for the current build is manual prospect entry.
- Research remains a separate track owned in parallel.
- Generated microsites should remain credible and first-touch safe.
- Observability is part of the MVP because the scoring rubric rewards it heavily.

## Expected System Shape

Favor explicit stage boundaries and reusable artifacts:

- generation run record
- step timings
- API latency logs
- persisted microsite output
- future research artifacts

If you implement code later, prefer designs where these artifacts can be inspected, edited, and rerun independently.

## Current Implementation Notes

- Frontend pages live in `app/`.
- Backend generation and observability logic lives in `backend/main.py`.
- The current UI is intentionally light-themed and builder-like.
- `OBSERVABILITY.md` explains the current scoring-aligned observability target.

## Working Style

- Keep human approval points visible in the product flow.
- Prefer simple MVP paths over platform-heavy abstractions.
- When a choice would lock in architecture, ask first unless the repo already makes the choice clear.
- If docs and implementation diverge, fix the docs or call out the mismatch instead of silently drifting.

## When Writing Prompts Or Copy

- Keep first-touch messaging discovery-oriented.
- Use the vendor's extracted theme and messaging, not generic B2B copy.
- Ground prospect claims in evidence or clearly label them as hypotheses.
- Design chatbot behavior around helping a prospect explore fit and next steps.
