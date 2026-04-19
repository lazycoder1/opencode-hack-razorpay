# Sales Collateral Microsite MVP PRD

## Product Summary

Build an agentic, configurable system that creates ABX-style sales collateral microsites vendors can send to prospects instead of static PPTs. The working example is `vendor x prospect`, such as `enmovil x target-account`, but `enmovil.ai` is only a placeholder.

The MVP should optimize for speed to first demo, while keeping every major step reviewable and editable before moving forward.

## Problem

Sales teams need lightweight, tailored collateral for prospecting, but today the workflow is slow, manual, and locked inside decks. We want a microsite workflow that:

- researches the vendor website to learn design language, theme, and messaging
- researches the prospect to identify public signals and likely challenges
- turns both into a sendable microsite draft
- includes a chat experience that acts as a sales copilot
- lets a human review and refine each stage before proceeding

## Primary User

An internal sales, growth, or marketing operator creating an ABX microsite for a target account.

## MVP Goal

Given only:

- vendor company URL
- prospect company URL

the system should generate stage-by-stage outputs, stop for approval at each stage, allow the user to chat and refine outputs, and finally produce a sendable microsite draft/link.

## Product Principles

- Agentic by default: each major step should be handled by an explicit agent or configurable pipeline step.
- Configurable inputs: skills, template skill, extracted theme, prompts, and other generation settings should be swappable inputs, not hardcoded logic.
- Approval-gated: do not auto-advance to the next stage without user approval.
- Evidence-aware: do not invent prospect-specific claims. In early interactions, stay with general trends, public signals, and discovery-oriented positioning.
- Framework-agnostic: do not assume a fixed frontend or backend stack unless the user later chooses one.
- Cache where possible: research and generation outputs should be reusable so repeated runs are fast.

## End-to-End Workflow

### Stage 1: Vendor Research

Input:

- vendor company URL

Tasks:

- crawl and summarize the vendor website
- extract design language, visual theme, tone, and content patterns
- identify product positioning, ICP clues, proof points, and CTAs
- store reusable research artifacts in cache

Output:

- vendor research summary
- extracted theme/design profile
- reusable brand and messaging profile

Gate:

- wait for human approval or edits before moving on

### Stage 2: Prospect Research

Input:

- prospect company URL
- approved vendor context from Stage 1

Tasks:

- research the prospect using public sources
- identify likely business context, public initiatives, industry trends, and generic problem themes
- prepare discovery-oriented hypotheses instead of overconfident personalization
- store reusable research artifacts in cache

Output:

- prospect research summary
- likely challenges and opportunity themes
- discovery questions and initial angle recommendations

Gate:

- wait for human approval or edits before moving on

### Stage 3: Microsite Draft Generation

Input:

- approved vendor research
- approved prospect research
- configurable template skill
- configurable generation skills/prompts

Tasks:

- create the microsite structure and copy
- apply the extracted vendor theme to the microsite
- generate sections that are useful for first outreach
- generate a chatbot/copilot prompt aligned to the account context

Output:

- microsite draft
- section plan and copy blocks
- chatbot configuration/prompt
- preview or microsite link

Gate:

- wait for human approval or edits before publishing/finalizing

### Stage 4: Chat-Led Refinement

The user should be able to chat with the system to modify outputs at any stage. This includes:

- refining research summaries
- adjusting positioning
- changing sections, tone, or layout direction
- improving chatbot behavior

The system should preserve stage state and use prior outputs as editable inputs instead of starting over.

## Chatbot Role

The chatbot is a sales copilot inside the microsite. For MVP it should:

- answer prospect-facing questions using the approved microsite context
- guide discovery conversations
- tailor responses to the current account context
- recommend next steps or follow-up angles

It should not pretend to know private prospect details that were never verified.

## Prompt Tester

Include a prompt testing surface or workflow so prompt changes for research and microsite generation can be tested quickly during MVP iteration.

## Required External Research Tool

Use Tavily for web research agents unless the user explicitly changes the tooling choice.

## Core Configurable Inputs

- vendor URL
- prospect URL
- research skill(s)
- template skill
- extracted theme/design system
- microsite generation prompt/config
- chatbot prompt/config

## Data/Artifact Expectations

The system should treat each stage output as a reusable artifact:

- vendor research cache
- prospect research cache
- approved summaries
- extracted theme tokens/profile
- microsite draft data
- chatbot configuration

These artifacts should be easy for later agents to inspect, edit, and reuse.

## MVP Boundaries

In scope:

- vendor website research
- prospect research from public web sources
- approval-gated generation workflow
- editable stage outputs via chat
- microsite draft generation
- sales copilot chatbot
- caching
- prompt testing workflow

Out of scope for now:

- deep persona-specific sections for CIO, CFO, and other decision makers at first touch
- private CRM or internal data integrations
- fully autonomous outreach without review
- assuming a fixed app framework before implementation starts

## Later Phase Direction

After initial discovery interactions, the microsite should evolve to support persona-specific sections for decision-makers such as:

- CIO
- CFO
- other functional heads involved in the buying committee

Those sections should be generated only after enough account context exists.

## Success Criteria For MVP

- A user can provide vendor and prospect URLs and get meaningful staged outputs.
- Each stage is reviewable and editable before the next stage starts.
- The generated microsite feels aligned to the vendor's design language.
- Prospect-facing content stays credible and discovery-oriented.
- A chatbot can act as a useful sales copilot on the microsite.
- The system is fast enough to demo end-to-end without rebuilding context from scratch.
