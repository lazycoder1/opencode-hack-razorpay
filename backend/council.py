"""Council of agents for microsite generation.

Architecture:
    Manager (planner) -> Seller Researcher + Prospect Researcher -> Manager (reviewer) -> Microsite Generator

Each agent reads its system+user prompt from state, so prompts are fully
editable from the sandbox UI. Every step produces observability metadata.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, TypedDict
from uuid import uuid4

from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

logger = logging.getLogger("council")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_model_name() -> str:
    return os.getenv("OPENAI_MODEL", "gpt-4.1-mini")


def get_llm(temperature: float = 0.7) -> ChatOpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")
    return ChatOpenAI(model=get_model_name(), api_key=api_key, temperature=temperature)


def normalize_usage(raw_message: Any) -> dict[str, int | None]:
    usage_metadata = getattr(raw_message, "usage_metadata", None) or {}
    response_usage = getattr(raw_message, "response_metadata", {}).get("token_usage", {})
    return {
        "input_tokens": usage_metadata.get("input_tokens") or response_usage.get("prompt_tokens"),
        "output_tokens": usage_metadata.get("output_tokens") or response_usage.get("completion_tokens"),
        "total_tokens": usage_metadata.get("total_tokens") or response_usage.get("total_tokens"),
    }


def stringify_content(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str) and item.strip():
                parts.append(item.strip())
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(text.strip())
        return "\n".join(parts)
    return ""


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    rates: dict[str, tuple[float, float]] = {
        "gpt-4.1-mini": (0.0004, 0.0016),
        "gpt-4.1": (0.002, 0.008),
        "gpt-5.4-mini": (0.0004, 0.0016),
    }
    base = model.split("-2")[0] if "-2" in model else model
    input_rate, output_rate = rates.get(base, (0.001, 0.004))
    return round((input_tokens / 1000) * input_rate + (output_tokens / 1000) * output_rate, 6)


def _invoke_llm(system: str, user: str, temperature: float = 0.5) -> tuple[str, str, dict[str, int | None], float, float]:
    """Shared LLM call. Returns (output, model, usage, duration_ms, cost)."""
    llm = get_llm(temperature=temperature)
    start = time.perf_counter()
    result = llm.invoke([{"role": "system", "content": system}, {"role": "user", "content": user}])
    duration_ms = round((time.perf_counter() - start) * 1000, 2)
    usage = normalize_usage(result)
    model = getattr(result, "response_metadata", {}).get("model_name", get_model_name())
    cost = estimate_cost(model, usage.get("input_tokens") or 0, usage.get("output_tokens") or 0)
    return stringify_content(result.content), model, usage, duration_ms, cost


# ---------------------------------------------------------------------------
# Default prompts per stage
# ---------------------------------------------------------------------------

DEFAULT_PROMPTS: dict[str, dict[str, str]] = {
    "manager_plan": {
        "system": (
            "You are the Manager agent in a council of AI agents building a sales microsite. "
            "Your job is to create a research plan. You will delegate to two specialist agents:\n"
            "1. Seller Researcher - will research the source/seller company\n"
            "2. Prospect Researcher - will research the target/prospect company\n\n"
            "Output a concise plan that tells each researcher what to focus on. "
            "Include what the final microsite should emphasize based on the pairing.\n"
            "Be specific about what data points each researcher should find."
        ),
        "user": (
            "Source company (seller): {{source_company}}\n"
            "Prospect company (target): {{prospect}}\n\n"
            "Create a research plan for this microsite. What should each researcher find? "
            "What angle should the microsite take?"
        ),
    },
    "seller_research": {
        "system": (
            "You are the Seller Research Agent. Your job is to research the SOURCE company that is selling/pitching. "
            "Find and organize:\n"
            "1. Core products and solutions\n"
            "2. Key case studies or success stories\n"
            "3. Brand positioning and differentiators\n"
            "4. Relevant metrics, scale, and credibility signals\n"
            "5. Integration capabilities or technical strengths\n\n"
            "Be factual. Use only publicly available information. Do not invent case studies or stats. "
            "If you don't know something, say so. Structure your output clearly with headers."
        ),
        "user": (
            "Research this company as the SELLER in a B2B pitch:\n"
            "Company: {{source_company}}\n\n"
            "Manager's plan:\n{{generation_plan}}\n\n"
            "Provide structured research output."
        ),
    },
    "prospect_research": {
        "system": (
            "You are the Prospect Research Agent. Your job is to research the TARGET company being pitched to. "
            "Find and organize:\n"
            "1. Core business model and operations\n"
            "2. Key pain points relevant to the seller's offering\n"
            "3. Decision-maker personas (CTO, VP Eng, Head of Payments, etc.)\n"
            "4. Recent news, funding, or growth signals\n"
            "5. Technology stack or infrastructure hints\n"
            "6. Competitive pressures they face\n\n"
            "Be factual. Use only publicly available information. Do not invent quotes or internal details. "
            "Structure your output clearly with headers."
        ),
        "user": (
            "Research this company as the PROSPECT being pitched to:\n"
            "Company: {{prospect}}\n"
            "Being pitched by: {{source_company}}\n\n"
            "Manager's plan:\n{{generation_plan}}\n\n"
            "Provide structured research output focused on pain points relevant to what the seller offers."
        ),
    },
    "manager_review": {
        "system": (
            "You are the Manager agent reviewing research from your specialist agents. "
            "Evaluate the quality and completeness of both research outputs. "
            "Decide whether the research is sufficient to generate a compelling microsite.\n\n"
            "Output:\n"
            "1. Brief quality assessment of seller research\n"
            "2. Brief quality assessment of prospect research\n"
            "3. Key insights to emphasize in the microsite\n"
            "4. Any gaps or concerns\n"
            "5. Final verdict: APPROVED or NEEDS_MORE_RESEARCH\n\n"
            "Be concise. End with exactly one line: VERDICT: APPROVED or VERDICT: NEEDS_MORE_RESEARCH"
        ),
        "user": (
            "Source company: {{source_company}}\n"
            "Prospect: {{prospect}}\n\n"
            "Original plan:\n{{generation_plan}}\n\n"
            "Seller research:\n{{seller_research}}\n\n"
            "Prospect research:\n{{prospect_research}}\n\n"
            "Review the research and decide if we can proceed to microsite generation."
        ),
    },
    "generate_microsite": {
        "system": (
            "You are a world-class frontend designer and developer. "
            "You create distinctive, production-grade HTML microsites with exceptional attention to aesthetic details. "
            "Return ONLY a single, complete, self-contained HTML document. No markdown fences, no explanation. "
            "The HTML must be a complete standalone page with inline CSS, responsive design, and Google Fonts. "
            "Use distinctive typography (never Inter, Roboto, Arial). Have a cohesive color palette. "
            "Include CSS animations for page load. Feel like a real designer made it."
        ),
        "user": (
            "Create a sales microsite for: {{source_company}} selling to {{company_name}}.\n\n"
            "Include a hero section, 3-4 value propositions, stats, a CTA section, and a footer.\n"
            "Make it feel premium and modern.\n\n"
            "--- SELLER RESEARCH ---\n{{seller_research}}\n\n"
            "--- PROSPECT RESEARCH ---\n{{prospect_research}}\n\n"
            "--- MANAGER REVIEW NOTES ---\n{{review_notes}}\n\n"
            "Use the research above to make the microsite specific and grounded. "
            "Do NOT invent facts not in the research. Return ONLY the raw HTML."
        ),
    },
}


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class AgentStepResult(BaseModel):
    step_name: str
    agent_role: str
    status: str
    started_at: str
    duration_ms: float
    output: str
    model_name: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cost_usd: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CouncilRunResult(BaseModel):
    run_id: str
    prospect: str
    source_company: str
    status: str
    started_at: str
    completed_at: str
    total_duration_ms: float
    total_cost_usd: float
    steps: list[AgentStepResult]
    seller_research: str
    prospect_research: str
    generation_plan: str
    review_notes: str
    final_html: str


class StagePrompts(BaseModel):
    """Per-stage prompt overrides. If empty, defaults are used."""
    manager_plan_system: str = ""
    manager_plan_user: str = ""
    seller_research_system: str = ""
    seller_research_user: str = ""
    prospect_research_system: str = ""
    prospect_research_user: str = ""
    manager_review_system: str = ""
    manager_review_user: str = ""
    generator_system: str = ""
    generator_user: str = ""


# ---------------------------------------------------------------------------
# LangGraph state
# ---------------------------------------------------------------------------

class CouncilState(TypedDict, total=False):
    run_id: str
    prospect: str
    source_company: str

    # Per-stage prompt overrides
    prompts: dict[str, dict[str, str]]

    # Cache control
    force_seller_refresh: bool

    # Stage outputs
    generation_plan: str
    seller_research: str
    prospect_research: str
    review_notes: str
    approved: bool
    final_html: str

    # Observability
    steps: list[dict[str, Any]]
    error: str


def _get_prompt(state: CouncilState, stage: str, key: str) -> str:
    """Get prompt for a stage, falling back to defaults."""
    custom = (state.get("prompts") or {}).get(stage, {}).get(key, "")
    if custom.strip():
        return custom
    return DEFAULT_PROMPTS.get(stage, {}).get(key, "")


def _render(template: str, state: CouncilState) -> str:
    """Replace placeholders in a prompt template."""
    return (
        template
        .replace("{{prospect}}", state.get("prospect", ""))
        .replace("{{company_name}}", state.get("prospect", ""))
        .replace("{{source_company}}", state.get("source_company", ""))
        .replace("{{generation_plan}}", state.get("generation_plan", "No plan provided."))
        .replace("{{seller_research}}", state.get("seller_research", "No seller research available."))
        .replace("{{prospect_research}}", state.get("prospect_research", "No prospect research available."))
        .replace("{{review_notes}}", state.get("review_notes", "No review notes."))
    )


# ---------------------------------------------------------------------------
# Agent nodes
# ---------------------------------------------------------------------------

def _run_agent_node(
    state: CouncilState,
    stage: str,
    agent_role: str,
    temperature: float = 0.5,
    output_key: str | None = None,
) -> CouncilState:
    """Generic agent node runner."""
    started_at = utc_now_iso()
    start_perf = time.perf_counter()

    system = _render(_get_prompt(state, stage, "system"), state)
    user = _render(_get_prompt(state, stage, "user"), state)

    try:
        output, model, usage, duration_ms, cost = _invoke_llm(system, user, temperature)

        step = AgentStepResult(
            step_name=stage, agent_role=agent_role, status="completed",
            started_at=started_at, duration_ms=duration_ms, output=output[:500],
            model_name=model, input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"), total_tokens=usage.get("total_tokens"),
            cost_usd=cost,
            metadata={
                "system_prompt_len": len(system),
                "user_prompt_len": len(user),
                "output_chars": len(output),
            },
        )
        updates: dict[str, Any] = {"steps": [*state.get("steps", []), step.model_dump()]}
        if output_key:
            updates[output_key] = output
        return updates
    except Exception as exc:
        logger.exception("%s failed", stage)
        step = AgentStepResult(
            step_name=stage, agent_role=agent_role, status="failed",
            started_at=started_at, duration_ms=round((time.perf_counter() - start_perf) * 1000, 2),
            output="", metadata={"error": str(exc)},
        )
        updates = {"steps": [*state.get("steps", []), step.model_dump()]}
        if output_key:
            updates[output_key] = ""
        updates["error"] = str(exc)
        return updates


def manager_plan_node(state: CouncilState) -> CouncilState:
    return _run_agent_node(state, "manager_plan", "manager", temperature=0.5, output_key="generation_plan")


def seller_research_node(state: CouncilState) -> CouncilState:
    """Check cache first. Only call LLM if no cached research exists."""
    try:
        from .db import get_cached_seller_research, save_seller_research_cache
    except ImportError:
        from db import get_cached_seller_research, save_seller_research_cache

    company = state.get("source_company", "")
    force_refresh = state.get("force_seller_refresh", False)

    if not force_refresh:
        try:
            cached = get_cached_seller_research(company)
            if cached and cached.get("research_output", "").strip():
                logger.info("Seller research cache HIT for %s", company)
                step = AgentStepResult(
                    step_name="seller_research",
                    agent_role="seller_researcher",
                    status="cached",
                    started_at=utc_now_iso(),
                    duration_ms=0.0,
                    output=cached["research_output"][:500],
                    model_name=cached.get("model_name"),
                    input_tokens=cached.get("input_tokens"),
                    output_tokens=cached.get("output_tokens"),
                    total_tokens=cached.get("total_tokens"),
                    cost_usd=0.0,
                    metadata={
                        "cache": "hit",
                        "company": company,
                        "cached_at": cached.get("updated_at", cached.get("created_at", "")),
                        "output_chars": len(cached["research_output"]),
                    },
                )
                return {
                    "seller_research": cached["research_output"],
                    "steps": [*state.get("steps", []), step.model_dump()],
                }
        except Exception:
            logger.exception("Seller research cache lookup failed, falling back to LLM")

    # Cache miss or forced refresh -- run the agent
    result = _run_agent_node(state, "seller_research", "seller_researcher", temperature=0.3, output_key="seller_research")

    # Persist to cache
    research_output = result.get("seller_research", "")
    if research_output.strip():
        last_step = result.get("steps", [])[-1] if result.get("steps") else {}
        try:
            save_seller_research_cache({
                "id": uuid4().hex,
                "company_name": company,
                "research_output": research_output,
                "prompt_system": _render(_get_prompt(state, "seller_research", "system"), state),
                "prompt_user": _render(_get_prompt(state, "seller_research", "user"), state),
                "model_name": last_step.get("model_name"),
                "input_tokens": last_step.get("input_tokens"),
                "output_tokens": last_step.get("output_tokens"),
                "total_tokens": last_step.get("total_tokens"),
                "cost_usd": last_step.get("cost_usd"),
                "duration_ms": last_step.get("duration_ms"),
                "metadata": {"cache": "miss", "forced_refresh": force_refresh},
            })
            logger.info("Seller research cached for %s", company)
        except Exception:
            logger.exception("Failed to cache seller research for %s", company)

        # Mark the step as cache miss
        if result.get("steps"):
            result["steps"][-1]["metadata"] = {**result["steps"][-1].get("metadata", {}), "cache": "miss"}

    return result


def prospect_research_node(state: CouncilState) -> CouncilState:
    return _run_agent_node(state, "prospect_research", "prospect_researcher", temperature=0.3, output_key="prospect_research")


def manager_review_node(state: CouncilState) -> CouncilState:
    result = _run_agent_node(state, "manager_review", "manager", temperature=0.3, output_key="review_notes")
    review_text = result.get("review_notes", "")
    result["approved"] = "VERDICT: APPROVED" in review_text.upper() if review_text else True
    return result


def generate_microsite_node(state: CouncilState) -> CouncilState:
    started_at = utc_now_iso()
    start_perf = time.perf_counter()

    system = _render(_get_prompt(state, "generate_microsite", "system"), state)
    user = _render(_get_prompt(state, "generate_microsite", "user"), state)

    try:
        html, model, usage, duration_ms, cost = _invoke_llm(system, user, temperature=0.9)

        if "```html" in html:
            html = html.replace("```html\n", "").replace("```\n", "").replace("```", "")
        html = html.strip()

        step = AgentStepResult(
            step_name="generate_microsite", agent_role="generator", status="completed",
            started_at=started_at, duration_ms=duration_ms, output=f"HTML: {len(html)} chars",
            model_name=model, input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"), total_tokens=usage.get("total_tokens"),
            cost_usd=cost, metadata={"html_chars": len(html)},
        )
        return {"final_html": html, "steps": [*state.get("steps", []), step.model_dump()]}
    except Exception as exc:
        logger.exception("Microsite generation failed")
        step = AgentStepResult(
            step_name="generate_microsite", agent_role="generator", status="failed",
            started_at=started_at, duration_ms=round((time.perf_counter() - start_perf) * 1000, 2),
            output="", metadata={"error": str(exc)},
        )
        return {"final_html": "", "error": str(exc), "steps": [*state.get("steps", []), step.model_dump()]}


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------

def should_generate(state: CouncilState) -> str:
    if state.get("approved", True):
        return "generate_microsite"
    return END


def build_council_graph() -> Any:
    graph = StateGraph(CouncilState)
    graph.add_node("manager_plan", manager_plan_node)
    graph.add_node("seller_research", seller_research_node)
    graph.add_node("prospect_research", prospect_research_node)
    graph.add_node("manager_review", manager_review_node)
    graph.add_node("generate_microsite", generate_microsite_node)

    graph.add_edge(START, "manager_plan")
    graph.add_edge("manager_plan", "seller_research")
    graph.add_edge("manager_plan", "prospect_research")
    graph.add_edge("seller_research", "manager_review")
    graph.add_edge("prospect_research", "manager_review")
    graph.add_conditional_edges("manager_review", should_generate, {"generate_microsite": "generate_microsite", END: END})
    graph.add_edge("generate_microsite", END)
    return graph.compile()


# ---------------------------------------------------------------------------
# Single-stage runner (for sandbox testing)
# ---------------------------------------------------------------------------

def run_single_stage(
    stage: str,
    prospect: str,
    source_company: str,
    prompts: dict[str, dict[str, str]],
    context: dict[str, str] | None = None,
) -> AgentStepResult:
    """Run a single council stage with custom prompts. Context provides outputs from previous stages."""
    state: CouncilState = {
        "run_id": uuid4().hex,
        "prospect": prospect,
        "source_company": source_company,
        "prompts": prompts,
        "steps": [],
        "generation_plan": (context or {}).get("generation_plan", ""),
        "seller_research": (context or {}).get("seller_research", ""),
        "prospect_research": (context or {}).get("prospect_research", ""),
        "review_notes": (context or {}).get("review_notes", ""),
    }

    node_map = {
        "manager_plan": manager_plan_node,
        "seller_research": seller_research_node,
        "prospect_research": prospect_research_node,
        "manager_review": manager_review_node,
        "generate_microsite": generate_microsite_node,
    }

    node_fn = node_map.get(stage)
    if not node_fn:
        raise ValueError(f"Unknown stage: {stage}")

    result_state = node_fn(state)
    steps = result_state.get("steps", [])
    if steps:
        return AgentStepResult.model_validate(steps[-1])
    raise RuntimeError(f"Stage {stage} produced no step result")


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------

def run_council(
    prospect: str,
    source_company: str,
    skill_prompt: str = "",
    user_prompt_template: str = "",
    stage_prompts: StagePrompts | None = None,
    force_seller_refresh: bool = False,
) -> CouncilRunResult:
    run_id = uuid4().hex
    run_started_at = utc_now_iso()
    run_start_perf = time.perf_counter()

    prompts: dict[str, dict[str, str]] = {}
    if stage_prompts:
        sp = stage_prompts
        if sp.manager_plan_system or sp.manager_plan_user:
            prompts["manager_plan"] = {"system": sp.manager_plan_system, "user": sp.manager_plan_user}
        if sp.seller_research_system or sp.seller_research_user:
            prompts["seller_research"] = {"system": sp.seller_research_system, "user": sp.seller_research_user}
        if sp.prospect_research_system or sp.prospect_research_user:
            prompts["prospect_research"] = {"system": sp.prospect_research_system, "user": sp.prospect_research_user}
        if sp.manager_review_system or sp.manager_review_user:
            prompts["manager_review"] = {"system": sp.manager_review_system, "user": sp.manager_review_user}
        if sp.generator_system or sp.generator_user:
            prompts["generate_microsite"] = {"system": sp.generator_system, "user": sp.generator_user}

    # Legacy: if caller only sent skill_prompt + user_prompt_template, use as generator overrides
    if not prompts.get("generate_microsite"):
        if skill_prompt.strip() or user_prompt_template.strip():
            prompts["generate_microsite"] = {
                "system": skill_prompt,
                "user": user_prompt_template,
            }

    council = build_council_graph()
    final_state = council.invoke({
        "run_id": run_id,
        "prospect": prospect,
        "source_company": source_company,
        "prompts": prompts,
        "force_seller_refresh": force_seller_refresh,
        "steps": [],
    })

    steps = [AgentStepResult.model_validate(s) for s in final_state.get("steps", [])]
    total_cost = sum(s.cost_usd or 0 for s in steps)
    html = final_state.get("final_html", "")

    return CouncilRunResult(
        run_id=run_id,
        prospect=prospect,
        source_company=source_company,
        status="completed" if html else "failed",
        started_at=run_started_at,
        completed_at=utc_now_iso(),
        total_duration_ms=round((time.perf_counter() - run_start_perf) * 1000, 2),
        total_cost_usd=total_cost,
        steps=steps,
        seller_research=final_state.get("seller_research", ""),
        prospect_research=final_state.get("prospect_research", ""),
        generation_plan=final_state.get("generation_plan", ""),
        review_notes=final_state.get("review_notes", ""),
        final_html=html,
    )
