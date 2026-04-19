# AGENTS.md

## Read First

- `PRD.md` is the product source of truth.
- `CLAUDE.md` captures the operating constraints for future sessions.

## Current Repo State

- This repo now contains a Next.js frontend and FastAPI backend for barebones microsite generation.
- Optimize decisions for speed to first demo.

## Commands

- `npm install`
- `npm run dev`
- `npm run build`
- `npm run typecheck`
- `python3 -m pip install -r backend/requirements.txt`
- `python3 -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000`
- `docker compose up -d postgres`

Run `build` and `typecheck` before treating a UI change as complete.

## App Structure

- `app/page.tsx` is the manual prospect entry and microsite generation page.
- `app/microsites/page.tsx` lists generated microsites.
- `app/microsites/[slug]/page.tsx` renders the unique microsite route.
- `app/observability/page.tsx` inspects generation runs and API latency.
- `app/globals.css` holds the current frontend styling.
- `backend/main.py` contains the FastAPI app, LangGraph generation flow, and observability APIs.
- `backend/data/` stores local JSON persistence for microsites and run logs.
- `OBSERVABILITY.md` explains the scoring-driven observability target and current implementation.

## Product Scope

- Current delivery focus is the microsite track, not the research track.
- Input is manual prospect entry for now, one prospect per line.
- Microsites are created with OpenAI via a LangGraph pipeline.
- Observability is part of the product surface now, not a later add-on.

## Current Workflow

1. Enter prospects manually.
2. Generate microsites in batch.
3. Persist each microsite with a unique slug.
4. Inspect generation runs in `/observability`.
5. Browse generated microsites in `/microsites`.

## Important Constraints

- Do not hardcode API keys in tracked files.
- Use env loading from ignored backend env files.
- Keep generation outputs structured and persisted.
- Preserve the observability endpoints and run logs when changing the pipeline.
- Track API latency and step timings whenever generation behavior changes.

## UI Notes

- The current UI is a light editorial builder surface.
- `/observability` should stay usable by a mentor or operator without reading raw JSON manually.

## Helpful Mental Model

- Manual prospects -> LangGraph run -> OpenAI structured output -> persisted microsite -> observability run record
