# AGENTS.md

## Read First

- `PRD.md` is the product source of truth.
- `CLAUDE.md` captures the operating constraints for future sessions.

## Current Repo State

- This repo now contains a Next.js mockup for the staged microsite flow.
- Optimize decisions for speed to first demo.

## Commands

- `npm install`
- `npm run dev`
- `npm run build`
- `npm run typecheck`

Run `build` and `typecheck` before treating a UI change as complete.

## App Structure

- `app/page.tsx` contains the current mockup flow and most UI state.
- `app/theme.css` holds global theme tokens. Default is light.
- `app/globals.css` holds component and layout styling built on top of the theme tokens.
- `app/layout.tsx` wires the global CSS files.

## Product Scope

- Build an agentic, configurable ABX sales collateral microsite flow.
- Primary example is `vendor x prospect`; `enmovil.ai` is only a placeholder.
- MVP inputs: vendor company URL and prospect company URL.
- Required research tool: Tavily for web research agents.

## Required Workflow

1. Research the vendor website and extract design language, theme, and messaging.
2. Stop for approval.
3. Research the prospect using public sources.
4. Stop for approval.
5. Generate the microsite draft and sales-copilot chatbot.
6. Stop for approval before finalizing/publishing.

Each stage must stay editable through chat; do not force full reruns when a user wants targeted changes.

## Important Constraints

- Keep all major parts agentic and configurable: skills, template skill, theme extraction, prompts, and generation settings should be inputs, not hardcoded behavior.
- Keep prompt editing first-class in the UI. The builder brief, research prompt, template prompt, and generation prompt should stay easy to modify.
- Cache research and generation artifacts so repeated runs can reuse prior work.
- Early prospect content should stay discovery-oriented and based on public evidence.
- Do not fabricate highly specific prospect pain points or stakeholder views.
- Persona-specific sections for CIO, CFO, and similar roles are a later phase, not first-touch MVP scope.

## UI Notes

- The current mockup is intentionally light-themed and builder-like, not a dark ops dashboard.
- Preserve the website-creator feel: visible prompt workspace, editable stages, live preview, and sales copilot on one page.

## Helpful Mental Model

- Vendor research cache -> prospect research cache -> microsite generation -> microsite link
- Separate prompt testing should exist for fast iteration on research and generation prompts
