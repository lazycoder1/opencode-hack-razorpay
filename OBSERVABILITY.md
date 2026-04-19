# Observability

## Why This Exists

`SCORING_MECHANISMS.md` makes observability one of the highest-value levers in the `MaaS` track:

- `L2`: structured logs, no UI
- `L3`: specific run can be inspected step by step
- `L4`: trace tree, token/cost per step, filters
- `L5`: run diff, alerts, searchable runs, production-grade debugging

For this repo, the goal is to get to a credible `L3` immediately and leave a clear path to `L4`.

## Current Implementation

Microsite generation now records:

- per-run status
- per-step timings
- model name used
- token usage from the LLM call
- total run duration
- API request latency via backend middleware
- persisted run history in `backend/data/generation_runs.json`
- persisted API request latency history in `backend/data/api_requests.json`

## Current Surfaces

- `GET /api/observability/runs`
- `GET /api/observability/runs/{runId}`
- `GET /api/observability/requests`

These are the minimum contract for inspecting what happened in a generation run.

## LangGraph Positioning

Microsite creation is executed through a LangGraph workflow so generation is already structured as explicit nodes instead of one opaque function.

Current nodes:

- `prepare_prompt`
- `generate_content`
- `finalize_microsite`

That gives us a real run timeline even before adding hosted tracing.

## LangSmith Path

LangGraph documentation recommends pairing LangGraph with LangSmith for deep runtime visibility.

If these environment variables are added later, LangGraph traces can be exported to LangSmith with minimal code change:

- `LANGSMITH_TRACING=true`
- `LANGSMITH_API_KEY=...`
- `LANGSMITH_PROJECT=website-creator`

That is the fastest path from local `L3` observability to hosted `L4` style trace inspection.

## Rubric Mapping

### Implemented Now

- Structured persisted run records
- Step-by-step inspection for a specific run
- API latency capture
- Token usage capture for model calls

This is aimed at `L3`, with partial `L4` groundwork.

### Missing For L4

- Trace tree UI instead of API-only inspection
- Cost per step calculation and display
- Filtering in a dedicated observability page
- Better correlation across request logs and generation runs

### Missing For L5

- Run diff
- alerts
- searchable production run console
- failure clustering and automated anomaly detection

## OpenAI Build Guidance Applied

From current OpenAI docs, the relevant production choices here are:

- use env vars for API keys instead of hardcoding
- prefer structured outputs so generation returns predictable shapes
- choose a faster/cheaper model for latency-sensitive MVP paths
- capture token usage and latency early so cost and performance tuning are possible

## Next Step

The next high-leverage improvement is a frontend `/observability` page that lets a mentor or operator inspect a run without hitting raw JSON endpoints.
