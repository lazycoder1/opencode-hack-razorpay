# Batch Microsite Generator PRD

## Product Summary

Build a system that lets a user upload or enter a list of companies, click `Generate`, and create a unique sales microsite for each company.

Near-term target output per prospect:

- research JSON
- pain points from web search
- a 5-line narrative hook
- a local file path to a generated HTML microsite
- per-agent cost and duration logged to terminal

The product has four core surfaces for today:

- a create page to input or upload target companies
- a research page to research those company websites before generation
- a generation workflow that creates microsites for all targets using an agentic pipeline
- a `/microsites` page to browse generated microsites and open each unique microsite URL

This should optimize for speed to first usable version, not full workflow completeness.

## Team Split For Now

The work should be split into two parallel tracks:

- Research track: owned separately, focused on company input, research prompt editing, website research, and stored research artifacts.
- Microsite track: owned here for now, focused on listing microsites, unique microsite routes, and generating microsites from stored research outputs.

The two tracks must integrate through a stable backend contract rather than shared in-memory frontend state.

## Problem

Sales and growth teams want to generate personalized microsites for many accounts, but doing this one-by-one is too slow. The system should batch that work so a user can go from account list to a set of unique microsite pages in one run.

## Primary User

An internal operator creating outbound sales microsites for multiple target accounts.

## Goals For Today

1. A page where the user can either paste a list of companies or upload an Excel file.
2. A research page where we can research the websites for those companies.
3. A `Generate` action that creates microsites for every company in the list.
4. A `/microsites` page with a dropdown or selector to browse all generated microsites.
5. Each microsite must live at its own unique route.

## Target Demo Contract

For a demo such as:

- product context: `CRED`
- prospect: `Razorpay`

the system should be able to produce:

1. structured Razorpay research JSON
2. Razorpay pain points from web search
3. a concise 5-line narrative hook
4. a local microsite file path such as `backend/generated/cred-razorpay.html`
5. per-agent cost and duration visible in terminal logs

This is the most concrete short-term outcome and should guide implementation choices.

## MVP Scope

### In Scope

- manual list entry for companies
- Excel upload for company lists
- parsing uploaded spreadsheet rows into a company target list
- company website research page and stored research outputs
- batch generation job kickoff
- agentic generation flow per company
- persistence of generated microsites
- `/microsites` index page with dropdown selection
- unique microsite page for each generated microsite

### Current Delivery Focus

For the microsite-side implementation we should prioritize:

- `/microsites` page
- unique microsite detail route
- microsite persistence
- generation flow that reads stored research outputs
- local HTML microsite artifact generation
- observability from the first generation run onward

The research UI can be developed in parallel as long as it writes the agreed backend records.

### Out Of Scope For Today

- advanced user auth and permissions
- polished retry dashboards and deep observability UX
- rich editing after generation
- CRM syncing
- persona-specific variants per stakeholder
- multi-tenant billing and quotas

## User Experience

### Page 1: Create

Primary purpose: accept a target list and start batch generation.

Inputs:

- vendor/company context for the sender side
- either a pasted list of companies or an uploaded Excel file
- editable research prompt for the uploaded/pasted company list

User actions:

- paste company names or URLs into a text area
- upload `.xlsx` or `.csv`
- review parsed companies
- edit the research prompt before running batch research
- click `Generate`

Outputs:

- list of accepted companies
- active research prompt for the batch
- generation status for the current batch
- link to browse finished microsites

### Page 2: Research

Primary purpose: research the websites for companies in the batch before microsite generation.

Route shape:

- `/research`
- optionally `/research/[batchId]`

User actions:

- select a batch
- view all companies in that batch
- run website research for one company or the full batch
- review stored research outputs per company
- re-run research for a company if needed
- approve the batch for microsite generation

Outputs:

- research status per company
- normalized website/company inputs
- research prompt used for the run
- research summary per company
- extracted facts, themes, and notes that will feed generation
- structured research JSON artifact
- extracted pain points from web search

### Page 3: `/microsites`

Primary purpose: browse generated microsites.

User actions:

- open a dropdown of all generated microsites
- select one microsite
- navigate to the selected microsite page

Outputs:

- dropdown or searchable selector of microsites
- metadata such as company name, generation time, and generation status
- link/open action to the unique microsite route

### Page 4: Microsite Detail

Route shape:

- `/microsites/[micrositeId]`

Primary purpose: render the generated microsite for a single company.

Content can start simple for MVP:

- hero/title
- company-specific copy
- summary/value proposition
- generated sections from the pipeline

For the target demo, a generated local HTML artifact is also a first-class deliverable, even if the route-based microsite exists in parallel.

## Functional Requirements

### Team Boundary

The research side is responsible for:

- creating batches and targets
- storing the editable research prompt
- running website research
- persisting research artifacts and statuses

The microsite side is responsible for:

- reading completed research artifacts
- generating microsite records from those artifacts
- generating a local HTML microsite artifact from those artifacts
- rendering the `/microsites` list page
- rendering unique microsite detail pages

Microsite generation should not depend on the research page UI directly. It should depend only on persisted research data.

### Company Input

The system must support:

- manual text entry of multiple companies
- file upload of Excel spreadsheets
- parsing rows into a normalized company list
- rejecting empty or invalid rows

### Website Research

The system must support:

- storing a website or company URL per target where available
- storing a batch-level research prompt that the user can edit
- running research against each company website
- persisting research outputs so generation can reuse them
- tracking research status independently from generation status
- allowing re-run of research without recreating the batch
- outputting structured research JSON per company
- outputting explicit pain point lists from web research

### Batch Generation

On `Generate`, the system must:

- create a batch record
- create a target record for each company
- use existing research artifacts when present
- use the stored research prompt and research outputs as the main input to microsite generation
- start one generation workflow per company
- store status for each company generation
- persist the local output path to the generated HTML microsite artifact

### Agentic Generation

Each company generation should be handled by an agentic pipeline. For MVP that means:

- gather input company data
- use approved or latest company research data
- treat research outputs as the source material for microsite content creation
- generate a 5-line narrative hook
- generate microsite content
- generate a local HTML microsite artifact
- persist the microsite content and metadata
- mark that microsite as completed or failed

The implementation does not need full autonomous coding agents today. It needs a practical generation pipeline with clear stages and persisted outputs.

### Observability Requirements

Observability is a product requirement, not a nice-to-have.

The system must capture:

- per-agent duration
- per-agent cost
- per-run total duration
- per-run total token usage
- per-step status
- terminal logs during execution
- persisted run records for later inspection
- backend API latency

Minimum demo behavior:

- terminal logs clearly show each agent step, duration, and cost
- a mentor or operator can inspect the run after execution without reading raw application code

The immediate goal is at least `L3` observability on the rubric in `SCORING_MECHANISMS.md`, with clear groundwork for `L4`.

### Microsite Storage And Retrieval

The system must store:

- batch
- target company
- research artifact(s)
- microsite content
- local microsite file path
- generation status
- unique microsite identifier/slug

The `/microsites` page must read from stored microsites, not from in-memory state.

## Data Model

Minimum entities:

### Batch

- `id`
- `created_at`
- `source_type` (`manual` or `file`)
- `research_prompt`
- `status`

### CompanyTarget

- `id`
- `batch_id`
- `company_name`
- `company_url` nullable
- `status`
- `error_message` nullable

### ResearchArtifact

- `id`
- `company_target_id`
- `source_url` nullable
- `summary`
- `raw_notes_json`
- `pain_points_json`
- `status`
- `created_at`
- `updated_at`

### Integration Contract

Minimum data the microsite flow needs from research:

- `company_target_id`
- `company_name`
- `source_url` if available
- `research_prompt`
- `summary`
- `raw_notes_json`
- `pain_points_json`
- `status`

Minimum readiness rule:

- a company can be generated into a microsite when its research artifact status is `completed`

### Microsite

- `id`
- `company_target_id`
- `slug`
- `title`
- `content_json` or `content_markdown`
- `narrative_hook`
- `local_file_path`
- `status`
- `created_at`
- `updated_at`

### GenerationRun

- `id`
- `company_target_id`
- `status`
- `started_at`
- `completed_at`
- `total_duration_ms`
- `total_cost_usd`
- `total_tokens`
- `steps_json`
- `error_message` nullable

## Generation Flow

1. User submits companies manually or through Excel upload.
2. Backend parses and stores the batch.
3. User opens the research page for that batch.
4. Backend creates research jobs for each company website.
5. Research artifacts are stored per company.
6. Microsite flow reads completed research artifacts.
7. Backend creates generation jobs for each company.
8. Worker/agent pipeline generates microsites from stored research.
9. Worker emits per-agent duration and cost to terminal logs.
10. Generated microsites are persisted with unique slugs and local HTML file paths.
11. `/microsites` reads all generated microsites.
12. User opens a unique microsite page or uses the generated local file path.

## API Expectations

Minimum backend endpoints:

- `POST /api/batches/manual`
- `POST /api/batches/upload`
- `PATCH /api/batches/{batchId}/research-prompt`
- `POST /api/batches/{batchId}/research`
- `POST /api/company-targets/{companyTargetId}/research`
- `GET /api/batches/{batchId}/research`
- `POST /api/batches/{batchId}/generate`
- `POST /api/company-targets/{companyTargetId}/generate`
- `GET /api/batches/{batchId}`
- `GET /api/microsites`
- `GET /api/microsites/{micrositeId}`
- `GET /api/microsites/by-slug/{slug}`
- `GET /api/observability/runs`
- `GET /api/observability/runs/{runId}`
- `GET /api/observability/requests`

## Non-Functional Requirements

- Generation must be asynchronous. Do not block the request until every microsite finishes.
- Research must be asynchronous for the same reason.
- Failed companies should not fail the entire batch.
- Each microsite must have a stable unique route.
- Research outputs must be persisted and reusable.
- The UI should show partial progress as microsites complete.
- The UI should show partial progress as research completes.
- Local development should work with the current Next.js frontend and FastAPI backend setup.
- Per-agent cost and duration must be visible in terminal output during generation.
- Observability data must be persisted so runs can be inspected after completion.

## Success Criteria

- A user can input multiple companies manually.
- A user can upload an Excel file and see parsed companies.
- A user can edit the research prompt for that batch before running research.
- A user can run and review website research for the companies in a batch.
- Microsites are generated from stored research outputs, not from raw company rows alone.
- Clicking `Generate` creates microsites for all valid companies in the batch.
- `/microsites` lists generated microsites.
- Each microsite opens on its own unique route.
- A demo run can produce research JSON, pain points, a 5-line hook, and a local HTML file path for a prospect.
- Terminal logs show per-agent duration and cost.

## Recommended Tools And Infra

### Minimum Stack For Fast Delivery

- Frontend: Next.js
- Backend API: FastAPI
- Database: Postgres
- Local DB: Docker Compose Postgres on `5436`
- File parsing: `pandas` or `openpyxl` for `.xlsx`, plus CSV parsing
- Background jobs: FastAPI background tasks for first pass if volume is low, but prefer a proper worker queue quickly
- Queue/cache: Redis
- Agentic research/generation: Tavily for web research plus an LLM provider for content generation
- Object/file storage: local disk for dev, S3/R2 in hosted environments if uploaded files need persistence
- Orchestration and run structure: LangGraph
- Hosted trace/debug path: LangSmith

### Recommended Practical Infra

- Next.js app deployed on Vercel
- FastAPI app deployed on Railway, Render, or Fly.io
- Managed Postgres: Neon
- Redis: Upstash or Railway Redis
- File storage: Cloudflare R2 or S3 if uploads must be stored beyond request lifecycle
- Hosted trace inspection: LangSmith

### Recommendation For Today

For the fastest useful version:

- keep Next.js + FastAPI
- use local Docker Postgres for dev
- add Postgres persistence first
- add Excel parsing next
- use a simple async job model now
- upgrade to Redis-backed workers once generation volume or latency becomes painful

## Build Order

1. Postgres-backed schema for batches, targets, research artifacts, and microsites.
2. Manual company list entry on the create page.
3. Excel upload and parsing.
4. Research page and batch research endpoints.
5. Agentic generation pipeline that outputs research JSON, pain points, hook, and HTML artifact.
6. Observability logging for per-agent cost and duration.
7. `/microsites` listing page.
8. Unique microsite detail route.
9. Rich observability page and filtering.
