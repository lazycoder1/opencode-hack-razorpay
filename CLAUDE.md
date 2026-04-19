# CLAUDE.md

## Read First

Before making product or architecture decisions, read:

1. `PRD.md`
2. `AGENTS.md`

This repo now includes a Next.js mockup of the MVP flow. Treat it as a demo scaffold, not final production architecture.

## Product Intent

We are building an agentic sales collateral microsite system for ABX-style outreach.

Core flow:

1. Research the vendor website.
2. Extract theme, design language, and messaging.
3. Research the prospect.
4. Generate a `vendor x prospect` microsite draft.
5. Let the user chat to refine outputs.
6. Only move to the next stage after approval.

## Hard Constraints

- Optimize for speed to first demo.
- Keep the system configurable and agentic.
- Default to framework-agnostic decisions unless the user explicitly chooses a stack.
- Use Tavily for web research agents unless told otherwise.
- Treat `enmovil.ai` as an example, not a baked-in customer.
- Do not auto-advance stages without approval.
- Do not invent prospect-specific claims that were not supported by public evidence.

## MVP Assumptions

- Minimal required inputs are vendor company URL and prospect company URL.
- Early prospect outputs should focus on public signals, general trends, and discovery prompts.
- Persona-specific sections for roles like CIO and CFO belong to a later phase, after more account context exists.
- The chatbot is a sales copilot, not a generic support bot.

## Expected System Shape

Favor explicit stage boundaries and reusable artifacts:

- vendor research output
- vendor theme extraction output
- prospect research output
- microsite generation output
- chatbot configuration
- cache for stage results

If you implement code later, prefer designs where these artifacts can be inspected, edited, and rerun independently.

## Current Implementation Notes

- The mockup lives in `app/page.tsx`.
- Global theme tokens live in `app/theme.css`.
- Global component/layout styles live in `app/globals.css`.
- The current UI is intentionally light-themed and prompt-forward.
- The prompt workspace should stay prominent in the product surface, not hidden behind a modal or settings page.

## Working Style

- Keep human approval points visible in the product flow.
- Preserve editability: users should be able to chat and revise outputs instead of restarting.
- Prefer simple MVP paths over platform-heavy abstractions.
- When a choice would lock in architecture, ask first unless the repo already makes the choice clear.
- If docs and implementation diverge, fix the docs or call out the mismatch instead of silently drifting.

## When Writing Prompts Or Copy

- Keep first-touch messaging discovery-oriented.
- Use the vendor's extracted theme and messaging, not generic B2B copy.
- Ground prospect claims in evidence or clearly label them as hypotheses.
- Design chatbot behavior around helping a prospect explore fit and next steps.
