"""Council of agents for microsite generation.

Architecture:
    Manager (planner) -> Seller Researcher + Prospect Researcher -> Manager (reviewer) -> Microsite Generator

Each agent writes structured output to LangGraph state and produces
observability metadata (duration, tokens, cost) per step.
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
    """Rough cost estimate in USD. Good enough for observability."""
    rates: dict[str, tuple[float, float]] = {
        "gpt-4.1-mini": (0.0004, 0.0016),
        "gpt-4.1": (0.002, 0.008),
        "gpt-5.4-mini": (0.0004, 0.0016),
    }
    base = model.split("-2")[0] if "-2" in model else model
    input_rate, output_rate = rates.get(base, (0.001, 0.004))
    return round((input_tokens / 1000) * input_rate + (output_tokens / 1000) * output_rate, 6)


# ---------------------------------------------------------------------------
# Step result model
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


# ---------------------------------------------------------------------------
# LangGraph state
# ---------------------------------------------------------------------------

class CouncilState(TypedDict, total=False):
    run_id: str
    prospect: str
    source_company: str
    skill_prompt: str
    user_prompt_template: str

    # Manager planner output
    generation_plan: str

    # Research outputs
    seller_research: str
    prospect_research: str

    # Manager reviewer output
    review_notes: str
    approved: bool

    # Generator output
    final_html: str

    # Observability
    steps: list[dict[str, Any]]
    error: str


# ---------------------------------------------------------------------------
# Agent nodes
# ---------------------------------------------------------------------------

def manager_plan_node(state: CouncilState) -> CouncilState:
    """Manager plans which research is needed and what the microsite should cover."""
    started_at = utc_now_iso()
    start_perf = time.perf_counter()

    system = (
        "You are the Manager agent in a council of AI agents building a sales microsite. "
        "Your job is to create a research plan. You will delegate to two specialist agents:\n"
        "1. Seller Researcher - will research the source/seller company\n"
        "2. Prospect Researcher - will research the target/prospect company\n\n"
        "Output a concise plan that tells each researcher what to focus on. "
        "Include what the final microsite should emphasize based on the pairing.\n"
        "Be specific about what data points each researcher should find."
    )
    user = (
        f"Source company (seller): {state['source_company']}\n"
        f"Prospect company (target): {state['prospect']}\n\n"
        "Create a research plan for this microsite. What should each researcher find? "
        "What angle should the microsite take?"
    )

    try:
        llm = get_llm(temperature=0.5)
        result = llm.invoke([
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ])
        usage = normalize_usage(result)
        model = getattr(result, "response_metadata", {}).get("model_name", get_model_name())
        output = stringify_content(result.content)
        duration_ms = round((time.perf_counter() - start_perf) * 1000, 2)
        cost = estimate_cost(model, usage.get("input_tokens") or 0, usage.get("output_tokens") or 0)

        step = AgentStepResult(
            step_name="manager_plan",
            agent_role="manager",
            status="completed",
            started_at=started_at,
            duration_ms=duration_ms,
            output=output,
            model_name=model,
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
            total_tokens=usage.get("total_tokens"),
            cost_usd=cost,
            metadata={"source_company": state["source_company"], "prospect": state["prospect"]},
        )
        return {
            "generation_plan": output,
            "steps": [*state.get("steps", []), step.model_dump()],
        }
    except Exception as exc:
        logger.exception("Manager planning failed")
        step = AgentStepResult(
            step_name="manager_plan", agent_role="manager", status="failed",
            started_at=started_at, duration_ms=round((time.perf_counter() - start_perf) * 1000, 2),
            output="", metadata={"error": str(exc)},
        )
        return {"error": str(exc), "generation_plan": "", "steps": [*state.get("steps", []), step.model_dump()]}


def seller_research_node(state: CouncilState) -> CouncilState:
    """Researches the source/seller company: solutions, case studies, brand positioning."""
    started_at = utc_now_iso()
    start_perf = time.perf_counter()

    system = (
        "You are the Seller Research Agent. Your job is to research the SOURCE company that is selling/pitching. "
        "Find and organize:\n"
        "1. Core products and solutions\n"
        "2. Key case studies or success stories\n"
        "3. Brand positioning and differentiators\n"
        "4. Relevant metrics, scale, and credibility signals\n"
        "5. Integration capabilities or technical strengths\n\n"
        "Be factual. Use only publicly available information. Do not invent case studies or stats. "
        "If you don't know something, say so. Structure your output clearly with headers."
    )
    user = (
        f"Research this company as the SELLER in a B2B pitch:\n"
        f"Company: {state['source_company']}\n\n"
        f"Manager's plan:\n{state.get('generation_plan', 'No plan provided.')}\n\n"
        "Provide structured research output."
    )

    try:
        llm = get_llm(temperature=0.3)
        result = llm.invoke([
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ])
        usage = normalize_usage(result)
        model = getattr(result, "response_metadata", {}).get("model_name", get_model_name())
        output = stringify_content(result.content)
        duration_ms = round((time.perf_counter() - start_perf) * 1000, 2)
        cost = estimate_cost(model, usage.get("input_tokens") or 0, usage.get("output_tokens") or 0)

        step = AgentStepResult(
            step_name="seller_research", agent_role="seller_researcher", status="completed",
            started_at=started_at, duration_ms=duration_ms, output=output[:500],
            model_name=model, input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"), total_tokens=usage.get("total_tokens"),
            cost_usd=cost, metadata={"company": state["source_company"], "output_chars": len(output)},
        )
        return {"seller_research": output, "steps": [*state.get("steps", []), step.model_dump()]}
    except Exception as exc:
        logger.exception("Seller research failed for %s", state["source_company"])
        step = AgentStepResult(
            step_name="seller_research", agent_role="seller_researcher", status="failed",
            started_at=started_at, duration_ms=round((time.perf_counter() - start_perf) * 1000, 2),
            output="", metadata={"error": str(exc)},
        )
        return {"seller_research": "", "steps": [*state.get("steps", []), step.model_dump()]}


def prospect_research_node(state: CouncilState) -> CouncilState:
    """Researches the prospect/target company: pain points, personas, market context."""
    started_at = utc_now_iso()
    start_perf = time.perf_counter()

    system = (
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
    )
    user = (
        f"Research this company as the PROSPECT being pitched to:\n"
        f"Company: {state['prospect']}\n"
        f"Being pitched by: {state['source_company']}\n\n"
        f"Manager's plan:\n{state.get('generation_plan', 'No plan provided.')}\n\n"
        "Provide structured research output focused on pain points relevant to what the seller offers."
    )

    try:
        llm = get_llm(temperature=0.3)
        result = llm.invoke([
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ])
        usage = normalize_usage(result)
        model = getattr(result, "response_metadata", {}).get("model_name", get_model_name())
        output = stringify_content(result.content)
        duration_ms = round((time.perf_counter() - start_perf) * 1000, 2)
        cost = estimate_cost(model, usage.get("input_tokens") or 0, usage.get("output_tokens") or 0)

        step = AgentStepResult(
            step_name="prospect_research", agent_role="prospect_researcher", status="completed",
            started_at=started_at, duration_ms=duration_ms, output=output[:500],
            model_name=model, input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"), total_tokens=usage.get("total_tokens"),
            cost_usd=cost, metadata={"company": state["prospect"], "output_chars": len(output)},
        )
        return {"prospect_research": output, "steps": [*state.get("steps", []), step.model_dump()]}
    except Exception as exc:
        logger.exception("Prospect research failed for %s", state["prospect"])
        step = AgentStepResult(
            step_name="prospect_research", agent_role="prospect_researcher", status="failed",
            started_at=started_at, duration_ms=round((time.perf_counter() - start_perf) * 1000, 2),
            output="", metadata={"error": str(exc)},
        )
        return {"prospect_research": "", "steps": [*state.get("steps", []), step.model_dump()]}


def manager_review_node(state: CouncilState) -> CouncilState:
    """Manager reviews research quality and decides whether to proceed to generation."""
    started_at = utc_now_iso()
    start_perf = time.perf_counter()

    system = (
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
    )
    user = (
        f"Source company: {state['source_company']}\n"
        f"Prospect: {state['prospect']}\n\n"
        f"Original plan:\n{state.get('generation_plan', 'N/A')}\n\n"
        f"Seller research:\n{state.get('seller_research', 'No research available.')}\n\n"
        f"Prospect research:\n{state.get('prospect_research', 'No research available.')}\n\n"
        "Review the research and decide if we can proceed to microsite generation."
    )

    try:
        llm = get_llm(temperature=0.3)
        result = llm.invoke([
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ])
        usage = normalize_usage(result)
        model = getattr(result, "response_metadata", {}).get("model_name", get_model_name())
        output = stringify_content(result.content)
        duration_ms = round((time.perf_counter() - start_perf) * 1000, 2)
        cost = estimate_cost(model, usage.get("input_tokens") or 0, usage.get("output_tokens") or 0)
        approved = "VERDICT: APPROVED" in output.upper()

        step = AgentStepResult(
            step_name="manager_review", agent_role="manager", status="completed",
            started_at=started_at, duration_ms=duration_ms, output=output[:500],
            model_name=model, input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"), total_tokens=usage.get("total_tokens"),
            cost_usd=cost, metadata={"approved": approved},
        )
        return {
            "review_notes": output,
            "approved": approved,
            "steps": [*state.get("steps", []), step.model_dump()],
        }
    except Exception as exc:
        logger.exception("Manager review failed")
        step = AgentStepResult(
            step_name="manager_review", agent_role="manager", status="failed",
            started_at=started_at, duration_ms=round((time.perf_counter() - start_perf) * 1000, 2),
            output="", metadata={"error": str(exc)},
        )
        return {
            "review_notes": "",
            "approved": True,
            "steps": [*state.get("steps", []), step.model_dump()],
        }


def generate_microsite_node(state: CouncilState) -> CouncilState:
    """Generates the final HTML microsite using research + skill instructions."""
    started_at = utc_now_iso()
    start_perf = time.perf_counter()

    skill = state.get("skill_prompt", "")
    template = state.get("user_prompt_template", "")

    user_prompt = template.replace("{{company_name}}", state["prospect"])
    user_prompt = user_prompt.replace("{{source_company}}", state["source_company"])

    user_prompt += (
        "\n\n--- SELLER RESEARCH (from Seller Research Agent) ---\n"
        f"{state.get('seller_research', 'No seller research available.')}\n\n"
        "--- PROSPECT RESEARCH (from Prospect Research Agent) ---\n"
        f"{state.get('prospect_research', 'No prospect research available.')}\n\n"
        "--- MANAGER REVIEW NOTES ---\n"
        f"{state.get('review_notes', 'No review notes.')}\n\n"
        "Use the research above to make the microsite specific, credible, and grounded in real facts. "
        "Do NOT invent facts that aren't in the research. "
        "Return ONLY the raw HTML. No markdown fences, no explanation."
    )

    try:
        llm = get_llm(temperature=0.9)
        result = llm.invoke([
            {"role": "system", "content": skill},
            {"role": "user", "content": user_prompt},
        ])
        usage = normalize_usage(result)
        model = getattr(result, "response_metadata", {}).get("model_name", get_model_name())
        html = stringify_content(result.content)
        duration_ms = round((time.perf_counter() - start_perf) * 1000, 2)
        cost = estimate_cost(model, usage.get("input_tokens") or 0, usage.get("output_tokens") or 0)

        if "```html" in html:
            html = html.replace("```html\n", "").replace("```\n", "").replace("```", "")
        html = html.strip()

        step = AgentStepResult(
            step_name="generate_microsite", agent_role="generator", status="completed",
            started_at=started_at, duration_ms=duration_ms, output=f"HTML generated: {len(html)} chars",
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
# Graph assembly
# ---------------------------------------------------------------------------

def should_generate(state: CouncilState) -> str:
    """Router: proceed to generation if approved, otherwise end."""
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

    # Flow: plan -> parallel research -> review -> conditional generate
    graph.add_edge(START, "manager_plan")
    graph.add_edge("manager_plan", "seller_research")
    graph.add_edge("manager_plan", "prospect_research")
    graph.add_edge("seller_research", "manager_review")
    graph.add_edge("prospect_research", "manager_review")
    graph.add_conditional_edges("manager_review", should_generate, {"generate_microsite": "generate_microsite", END: END})
    graph.add_edge("generate_microsite", END)

    return graph.compile()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_council(
    prospect: str,
    source_company: str,
    skill_prompt: str,
    user_prompt_template: str,
) -> CouncilRunResult:
    """Execute the full council pipeline and return a structured result."""
    run_id = uuid4().hex
    run_started_at = utc_now_iso()
    run_start_perf = time.perf_counter()

    council = build_council_graph()
    final_state = council.invoke({
        "run_id": run_id,
        "prospect": prospect,
        "source_company": source_company,
        "skill_prompt": skill_prompt,
        "user_prompt_template": user_prompt_template,
        "steps": [],
    })

    steps = [AgentStepResult.model_validate(s) for s in final_state.get("steps", [])]
    total_cost = sum(s.cost_usd or 0 for s in steps)
    html = final_state.get("final_html", "")
    status = "completed" if html else "failed"

    return CouncilRunResult(
        run_id=run_id,
        prospect=prospect,
        source_company=source_company,
        status=status,
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
