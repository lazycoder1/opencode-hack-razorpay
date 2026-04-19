"""Council of agents for microsite generation.

Architecture:
    manager_plan
      -> [seller_research + prospect_research]    # parallel, with Tavily + conditional MCP
      -> manager_review                           # manager/editor, may loop back
      -> generate_microsite                       # structured MicrositeContent + HTML

Preserved from the prior module:
    - Per-stage editable prompts via DEFAULT_PROMPTS + StagePrompts + state["prompts"]
    - `run_single_stage` for sandbox debugging

Added:
    - Skill files at skills/<name>/SKILL.md drive DEFAULT system prompts when present.
    - prospect_research_node fans out Tavily searches + homepage extract and injects
      the cleaned web context into the prompt as {{tavily_web_data}}.
    - seller_research_node injects {{tavily_seller_data}}, {{seller_brand}},
      {{seller_skills}}, and {{mcp_kb_result}} (latter only when seller slug == 'enmovil').
    - manager_review emits a structured NarrativeBrief alongside the free-text notes
      and can loop back to researchers with concrete follow-up queries up to
      MAX_ITERATIONS rounds.
    - generate_microsite emits a structured MicrositeContent (for the Next.js route)
      in addition to the raw HTML document (for /m/{slug}).
"""

from __future__ import annotations

import asyncio
import json as _json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, TypedDict
from uuid import uuid4


def _merge_lists(left: list, right: list) -> list:
    """Reducer for LangGraph: merge step lists from parallel nodes."""
    return [*left, *right]

from langchain.agents import create_agent
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

logger = logging.getLogger("council")

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
SKILLS_DIR = PROJECT_ROOT / "skills"
COMPANY_PROFILES_DIR = PROJECT_ROOT / "company-profiles"

MAX_ITERATIONS = 2  # manager_review can request at most one re-research round
ENMOVIL_SELLER_SLUG = "enmovil"
ENMOVIL_MCP_SERVER_NAME = os.getenv("ENMOVIL_MCP_SERVER_NAME", "kb-mcp-enmovil")


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-") or "company"


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
        "gpt-4o-mini": (0.00015, 0.0006),
        "gpt-4o": (0.0025, 0.01),
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


def _invoke_structured(system: str, user: str, output_model: type[BaseModel], temperature: float = 0.4) -> tuple[BaseModel, str, dict[str, int | None], float, float]:
    """LLM call with structured output. Returns (parsed_model, model_name, usage, duration_ms, cost)."""
    llm = get_llm(temperature=temperature)
    start = time.perf_counter()
    structured = llm.with_structured_output(output_model, include_raw=True)
    result = structured.invoke([{"role": "system", "content": system}, {"role": "user", "content": user}])
    duration_ms = round((time.perf_counter() - start) * 1000, 2)
    if result.get("parsing_error"):
        raise result["parsing_error"]
    parsed = result["parsed"]
    raw = result["raw"]
    usage = normalize_usage(raw)
    model = getattr(raw, "response_metadata", {}).get("model_name", get_model_name())
    cost = estimate_cost(model, usage.get("input_tokens") or 0, usage.get("output_tokens") or 0)
    return parsed, model, usage, duration_ms, cost


def _run_async(coro: Any) -> Any:
    """Run a coroutine from sync code, even inside a running event loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


# ---------------------------------------------------------------------------
# Skill loading (skills/<name>/SKILL.md body becomes the system prompt default)
# ---------------------------------------------------------------------------

_SKILL_FRONTMATTER_RE = re.compile(r"^---\n.*?\n---\n", re.DOTALL)


@lru_cache(maxsize=16)
def load_skill_body(name: str) -> str:
    path = SKILLS_DIR / name / "SKILL.md"
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8")
    return _SKILL_FRONTMATTER_RE.sub("", text, count=1).strip()


@lru_cache(maxsize=8)
def load_company_profile_text(seller_slug: str) -> tuple[str, str]:
    brand_path = COMPANY_PROFILES_DIR / seller_slug / "brand.md"
    skills_path = COMPANY_PROFILES_DIR / seller_slug / "skills.md"
    brand = brand_path.read_text(encoding="utf-8") if brand_path.exists() else ""
    skills = skills_path.read_text(encoding="utf-8") if skills_path.exists() else ""
    return brand, skills


# ---------------------------------------------------------------------------
# Tavily web research
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def get_tavily_client() -> Any:
    try:
        from tavily import TavilyClient
    except ImportError as exc:
        raise RuntimeError("tavily-python is not installed") from exc
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        raise RuntimeError("TAVILY_API_KEY is not configured")
    return TavilyClient(api_key=api_key)


def tavily_search(query: str, max_results: int = 4) -> list[dict[str, Any]]:
    try:
        client = get_tavily_client()
        response = client.search(query=query, max_results=max_results, search_depth="basic")
        return response.get("results", []) or []
    except Exception:
        logger.exception("Tavily search failed: %s", query)
        return []


def tavily_extract(urls: list[str]) -> list[dict[str, Any]]:
    if not urls:
        return []
    try:
        client = get_tavily_client()
        response = client.extract(urls=urls)
        return response.get("results", []) or []
    except Exception:
        logger.exception("Tavily extract failed: %s", urls)
        return []


def run_parallel_searches(queries: list[str], per_query_results: int = 4) -> dict[str, list[dict[str, Any]]]:
    if not queries:
        return {}
    out: dict[str, list[dict[str, Any]]] = {}
    with ThreadPoolExecutor(max_workers=min(6, len(queries))) as pool:
        futures = {pool.submit(tavily_search, q, per_query_results): q for q in queries}
        for future, query in futures.items():
            try:
                out[query] = future.result(timeout=30)
            except Exception:
                logger.exception("parallel search failed: %s", query)
                out[query] = []
    return out


def format_tavily_context(extract_results: list[dict[str, Any]], search_results: dict[str, list[dict[str, Any]]], max_chars_per_extract: int = 2000) -> str:
    """Turn Tavily results into a source-rich text block suitable for a user prompt."""
    blocks: list[str] = []
    for item in extract_results:
        url = item.get("url", "")
        raw = (item.get("raw_content") or item.get("content") or "")[:max_chars_per_extract]
        if raw:
            blocks.append(f"[HOMEPAGE EXTRACT — {url}]\n{raw}")
    for query, results in search_results.items():
        for r in results:
            title = r.get("title", "")
            url = r.get("url", "")
            content = r.get("content", "")
            date = r.get("published_date", "")
            blocks.append(f"[SEARCH — {query}]\n{title} ({url} — {date})\n{content}")
    return "\n\n---\n\n".join(blocks) if blocks else "(no sources returned)"


# ---------------------------------------------------------------------------
# Enmovil-gated MCP
# ---------------------------------------------------------------------------

def _parse_mcp_servers_config() -> dict[str, dict[str, Any]]:
    raw = os.getenv("MICROSITE_MCP_SERVERS_JSON", "").strip()
    if not raw:
        return {}
    try:
        parsed = _json.loads(raw)
    except Exception:
        logger.exception("MICROSITE_MCP_SERVERS_JSON parse error")
        return {}
    server_map = parsed.get("mcpServers", parsed) if isinstance(parsed, dict) else {}
    return server_map if isinstance(server_map, dict) else {}


async def _call_enmovil_mcp(query: str) -> dict[str, Any]:
    server_map = _parse_mcp_servers_config()
    enmovil_cfg = server_map.get(ENMOVIL_MCP_SERVER_NAME)
    if not enmovil_cfg:
        return {"context": "", "tool_names": [], "error": f"MCP '{ENMOVIL_MCP_SERVER_NAME}' not configured"}
    client = MultiServerMCPClient({ENMOVIL_MCP_SERVER_NAME: enmovil_cfg})
    try:
        tools = await client.get_tools()
    except Exception as exc:
        logger.exception("MCP get_tools failed")
        return {"context": "", "tool_names": [], "error": f"MCP get_tools failed: {exc}"}
    if not tools:
        return {"context": "", "tool_names": [], "error": "MCP returned no tools"}
    agent = create_agent(f"openai:{get_model_name()}", tools)
    instruction = (
        "You are retrieving matching case studies from the Enmovil knowledge base. "
        "Use the available tools to search for case studies or customer stories that match this query. "
        "Return a short plain-text brief listing up to 3 matching case studies, each with: customer, problem, outcome, metric, source. "
        "If nothing matches, say 'no match' explicitly.\n\n"
        f"Query: {query}"
    )
    try:
        result = await agent.ainvoke({"messages": [{"role": "user", "content": instruction}]})
    except Exception as exc:
        logger.exception("MCP agent invocation failed")
        return {"context": "", "tool_names": [getattr(t, "name", "unknown") for t in tools], "error": str(exc)}
    text = ""
    messages = result.get("messages") if isinstance(result, dict) else None
    if isinstance(messages, list):
        for message in reversed(messages):
            candidate = stringify_content(getattr(message, "content", None))
            if candidate:
                text = candidate
                break
    return {
        "context": text,
        "tool_names": [getattr(t, "name", "unknown") for t in tools],
        "error": None,
    }


def call_enmovil_mcp(query: str) -> dict[str, Any]:
    return _run_async(_call_enmovil_mcp(query))


# ---------------------------------------------------------------------------
# Default prompts (SKILL.md body overrides the 'system' default when present)
# ---------------------------------------------------------------------------

def _skill_or_inline(skill_name: str, inline: str) -> str:
    body = load_skill_body(skill_name)
    return body if body else inline


DEFAULT_PROMPTS: dict[str, dict[str, str]] = {
    "manager_plan": {
        "system": (
            "You are the Manager agent in a council of AI agents building a sales microsite. "
            "Your job is to create a concise research plan for two specialist agents: Seller Researcher and Prospect Researcher. "
            "Be specific about what each should find. End with one sentence on the microsite angle."
        ),
        "user": (
            "Seller: {{source_company}}\n"
            "Prospect: {{prospect}}\n\n"
            "Create a tight research plan. What should each researcher find? What angle should the microsite take?"
        ),
    },
    "seller_research": {
        "system": _skill_or_inline("seller-researcher",
            "You are the Seller Research Agent. Use ONLY the provided context to emit a grounded brief."
        ),
        "user": (
            "Research this company as the SELLER in a B2B pitch. Use ONLY the context below — do not invent case studies, stats, or customers.\n\n"
            "Seller: {{source_company}} (slug: {{seller_slug}})\n"
            "Prospect (for relevance steering): {{prospect}}\n"
            "Manager's plan:\n{{generation_plan}}\n\n"
            "----- SELLER BRAND -----\n{{seller_brand}}\n\n"
            "----- SELLER SKILLS CONTEXT -----\n{{seller_skills}}\n\n"
            "----- WEB CONTEXT (Tavily) -----\n{{tavily_seller_data}}\n\n"
            "----- ENMOVIL KB (MCP) — only populated when seller is Enmovil -----\n{{mcp_kb_result}}\n\n"
            "Organize the output with headers: Products, Value Props, Differentiators, Case Studies (with customer/problem/outcome/metric/source), Credibility signals, Integration capabilities, Gaps. "
            "Reference sources inline with their URL."
        ),
    },
    "prospect_research": {
        "system": _skill_or_inline("prospect-researcher",
            "You are the Prospect Research Agent. Use ONLY the provided web context to emit a grounded brief."
        ),
        "user": (
            "Research this company as the PROSPECT being pitched to. Use ONLY the web context below. Every claim must trace to a source URL.\n\n"
            "Prospect: {{prospect}}\n"
            "Being pitched by: {{source_company}}\n"
            "Manager's plan:\n{{generation_plan}}\n\n"
            "----- WEB CONTEXT (Tavily homepage extract + parallel searches) -----\n{{tavily_web_data}}\n\n"
            "Organize with headers: Summary, Industry, Pain Points By Segment/Scale (each with source_url), General Trends In Solving These Pains, Recent Signals (with source + date), Leadership Priorities, Funding Stage, Tech Signals, Relevant Triggers, CIO Considerations, CFO Considerations, Champion Considerations, Gaps Detected, Unverified Enrichment (clearly labeled). "
            "Drop any claim you cannot cite — do not paper over with generalities."
        ),
    },
    "prospect_seller_fit": {
        "system": _skill_or_inline("prospect-seller-fit",
            "You are the Fit Analyst. Given grounded prospect research and seller research, "
            "emit a SellerFitBrief that maps prospect pains to seller wedges. No new facts."
        ),
        "user": (
            "Seller: {{source_company}} (slug: {{seller_slug}})\n"
            "Prospect: {{prospect}} (slug: {{prospect_slug}})\n\n"
            "Match prospect pains to seller wedges. Every claim must trace back to one of the two research blobs below. "
            "Do not invent facts. If no wedge fits a pain, put it in non_addressable_pains.\n\n"
            "----- SELLER RESEARCH -----\n{{seller_research}}\n\n"
            "----- PROSPECT RESEARCH -----\n{{prospect_research}}\n\n"
            "Pick ONE recommended_angle (verbatim from a seller wedge). Cap fit_score honestly."
        ),
    },
    "manager_review": {
        "system": _skill_or_inline("narrative-synthesizer",
            "You are the Manager agent reviewing research from your specialist agents. "
            "Evaluate the quality and completeness of both research outputs. "
            "Decide whether the research is sufficient to generate a compelling microsite."
        ),
        "user": (
            "Seller: {{source_company}} (slug: {{seller_slug}})\n"
            "Prospect: {{prospect}}\n"
            "Iteration: {{iteration_count}} (ceiling: {{max_iterations}})\n\n"
            "Original plan:\n{{generation_plan}}\n\n"
            "Fit brief (primary — pain/angle already mapped):\n{{prospect_seller_fit_json}}\n\n"
            "Seller research (tone/proof context):\n{{seller_research}}\n\n"
            "Prospect research (read-only context; do not re-derive fit):\n{{prospect_research}}\n\n"
            "Write a concise editorial review. Anchor on the fit brief — its addressable_pains, recommended_angle, and fit_score are your inputs, not raw pains. "
            "Note specific strengths and gaps. "
            "End with EXACTLY one line: 'VERDICT: APPROVED' or 'VERDICT: NEEDS_MORE_RESEARCH'. "
            "If iteration_count has reached the ceiling, you MUST emit APPROVED."
        ),
    },
    "generate_microsite": {
        "system": _skill_or_inline("site-generator",
            "You are a world-class frontend designer. Create a distinctive, production-grade HTML microsite. "
            "Return ONLY a single, complete, self-contained HTML document. No markdown fences, no explanation. "
            "Use distinctive typography (never Inter/Roboto/Arial alone). Load Tailwind CDN and Google Fonts. "
            "Feel like a real designer made it."
        ),
        "user": (
            "Create a sales microsite for {{source_company}} selling to {{company_name}}.\n\n"
            "Include a hero with the 5-line narrative hook verbatim, 3 stats, 3-4 editorial sections, role-specific discovery sections for CIO/CFO/Champion, a CTA, and a footer.\n"
            "Make it feel premium and brand-appropriate (see seller brand context).\n\n"
            "--- SELLER BRAND ---\n{{seller_brand}}\n\n"
            "--- SELLER SKILLS ---\n{{seller_skills}}\n\n"
            "--- NARRATIVE BRIEF (structured, from the editor) ---\n{{narrative_brief_json}}\n\n"
            "--- SELLER RESEARCH ---\n{{seller_research}}\n\n"
            "--- PROSPECT RESEARCH ---\n{{prospect_research}}\n\n"
            "--- INDUSTRY RESEARCH ---\n{{industry_research}}\n\n"
            "--- MANAGER REVIEW NOTES ---\n{{review_notes}}\n\n"
            "Also create role-specific discovery content for CIO, CFO, and Champion stakeholders inside the structured output."
            "Do NOT invent facts not in the research or brief. "
            "The prospect name '{{prospect}}' must appear at least 3 times on the page. "
            "Return ONLY the raw HTML — no markdown fences."
        ),
    },
}


# ---------------------------------------------------------------------------
# Pydantic output models
# ---------------------------------------------------------------------------

class _OrgRef(BaseModel):
    name: str
    slug: str
    website: str | None = None


class _Evidence(BaseModel):
    text: str
    source_url: str | None = None
    confidence: str | None = None


class _Signal(BaseModel):
    headline: str
    url: str | None = None
    date: str | None = None
    category: str | None = None


class _CaseStudy(BaseModel):
    customer_name: str
    problem: str
    outcome: str
    metric: str | None = None
    source_ref: str | None = None


class _AddressablePain(BaseModel):
    pain_text: str
    pain_source_url: str | None = None
    matched_wedge: str
    why: str
    confidence: str = "medium"  # high | medium | low


class _NonAddressablePain(BaseModel):
    pain_text: str
    reason: str


class _FitTrigger(BaseModel):
    headline: str
    url: str | None = None
    date: str | None = None
    why_it_matters_to_seller: str


class _ICPMatch(BaseModel):
    inside_icp: bool = False
    matched_signals: list[str] = Field(default_factory=list)
    notes: str | None = None


class _RecommendedAngle(BaseModel):
    wedge: str
    why_this_wedge: str
    supporting_pain_refs: list[str] = Field(default_factory=list)
    supporting_trigger_refs: list[str] = Field(default_factory=list)


class SellerFitBrief(BaseModel):
    prospect_slug: str = ""
    seller_slug: str = ""
    addressable_pains: list[_AddressablePain] = Field(default_factory=list)
    non_addressable_pains: list[_NonAddressablePain] = Field(default_factory=list)
    strongest_triggers_for_seller: list[_FitTrigger] = Field(default_factory=list)
    icp_match: _ICPMatch = Field(default_factory=_ICPMatch)
    mismatch_flags: list[str] = Field(default_factory=list)
    recommended_angle: _RecommendedAngle | None = None
    fit_hypothesis: str = ""
    fit_score: float = 0.0


class NarrativeBrief(BaseModel):
    hook: list[str] = Field(min_length=5, max_length=5, description="Exactly 5 short lines, ≤14 words each")
    problem_statement: str
    seller_fit: str
    relevant_case_studies: list[_CaseStudy] = Field(default_factory=list)
    cta: str
    tone_directives: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    verdict: str = Field(description="PROCEED or NEEDS_MORE_RESEARCH")
    followups: list[str] = Field(default_factory=list, description="Raw Tavily queries for a re-research pass, empty on PROCEED")
    followup_target: str | None = Field(default=None, description="prospect_research | seller_research | both")


class _MicrositeTheme(BaseModel):
    background: str
    surface: str
    accent: str
    accent_soft: str
    text: str
    muted: str


class _MicrositeSection(BaseModel):
    title: str
    body: str


class MicrositeContent(BaseModel):
    tagline: str
    headline: str
    summary: str
    narrative_hook: list[str] = Field(min_length=5, max_length=5)
    cta_label: str
    visual_direction: str
    stats: list[str] = Field(min_length=3, max_length=3)
    sections: list[_MicrositeSection] = Field(min_length=3, max_length=4)
    theme: _MicrositeTheme
    role_pages: RolePages


class RolePage(BaseModel):
    title: str
    summary: str
    priorities: list[str] = Field(min_length=3, max_length=5)
    sections: list[_MicrositeSection] = Field(min_length=2, max_length=4)
    cta: str


class RolePages(BaseModel):
    cio: RolePage
    cfo: RolePage
    champion: RolePage


# ---------------------------------------------------------------------------
# Observability models
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
    industry_research: str = ""
    generation_plan: str
    review_notes: str
    final_html: str
    # New structured artifacts (optional for backward compatibility)
    prospect_seller_fit: dict[str, Any] | None = None
    narrative_brief: dict[str, Any] | None = None
    microsite_content: dict[str, Any] | None = None
    role_pages: dict[str, Any] | None = None
    iterations: int = 1
    used_mcp: bool = False


class StagePrompts(BaseModel):
    """Per-stage prompt overrides. If empty, DEFAULT_PROMPTS apply."""
    manager_plan_system: str = ""
    manager_plan_user: str = ""
    seller_research_system: str = ""
    seller_research_user: str = ""
    prospect_research_system: str = ""
    prospect_research_user: str = ""
    industry_research_system: str = ""
    industry_research_user: str = ""
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
    prospect_slug: str
    seller_slug: str
    prospect_website: str | None
    seller_website: str | None

    # Per-stage prompt overrides
    prompts: dict[str, dict[str, str]]

    # Cache control
    force_seller_refresh: bool

    # Injected tool context (prompts reference these via placeholders)
    tavily_web_data: str
    tavily_seller_data: str
    mcp_kb_result: str
    seller_brand: str
    seller_skills: str

    # Stage outputs
    generation_plan: str
    seller_research: str
    prospect_research: str
    industry_research: str
    review_notes: str
    approved: bool
    verdict: str
    final_html: str

    # Structured artifacts
    prospect_seller_fit: dict[str, Any]
    narrative_brief: dict[str, Any]
    microsite_content: dict[str, Any]
    role_pages: dict[str, Any]

    # Dynamic looping
    iteration_count: int
    pending_followups: list[str]
    followup_target: str
    used_mcp: bool

    # Observability — Annotated so parallel nodes can both append
    steps: Annotated[list[dict[str, Any]], _merge_lists]
    error: str


# ---------------------------------------------------------------------------
# Prompt resolution
# ---------------------------------------------------------------------------

def _get_prompt(state: CouncilState, stage: str, key: str) -> str:
    custom = (state.get("prompts") or {}).get(stage, {}).get(key, "")
    if custom and custom.strip():
        return custom
    try:
        from . import db as pgdb
    except ImportError:
        import db as pgdb
    record = pgdb.get_active_council_prompt(state.get("source_company", ""), stage)
    if record:
        prompt_value = record.get("system_prompt", "") if key == "system" else record.get("user_prompt", "")
        if isinstance(prompt_value, str) and prompt_value.strip():
            return prompt_value
    return DEFAULT_PROMPTS.get(stage, {}).get(key, "")


def _render(template: str, state: CouncilState) -> str:
    return (
        template
        .replace("{{prospect}}", state.get("prospect", ""))
        .replace("{{company_name}}", state.get("prospect", ""))
        .replace("{{source_company}}", state.get("source_company", ""))
        .replace("{{seller_slug}}", state.get("seller_slug", ""))
        .replace("{{prospect_slug}}", state.get("prospect_slug", ""))
        .replace("{{iteration_count}}", str(state.get("iteration_count", 0)))
        .replace("{{max_iterations}}", str(MAX_ITERATIONS))
        .replace("{{generation_plan}}", state.get("generation_plan", "No plan provided."))
        .replace("{{seller_research}}", state.get("seller_research", "No seller research available."))
        .replace("{{prospect_research}}", state.get("prospect_research", "No prospect research available."))
        .replace("{{industry_research}}", state.get("industry_research", "No industry research available."))
        .replace("{{review_notes}}", state.get("review_notes", "No review notes."))
        .replace("{{tavily_web_data}}", state.get("tavily_web_data", "(no web data)"))
        .replace("{{tavily_seller_data}}", state.get("tavily_seller_data", "(no web data)"))
        .replace("{{mcp_kb_result}}", state.get("mcp_kb_result", "(not used)"))
        .replace("{{seller_brand}}", state.get("seller_brand", ""))
        .replace("{{seller_skills}}", state.get("seller_skills", ""))
        .replace("{{narrative_brief_json}}", _json.dumps(state.get("narrative_brief") or {}, indent=2))
        .replace("{{prospect_seller_fit_json}}", _json.dumps(state.get("prospect_seller_fit") or {}, indent=2))
    )


# ---------------------------------------------------------------------------
# Node: manager plan
# ---------------------------------------------------------------------------

def _run_llm_node(
    state: CouncilState,
    stage: str,
    agent_role: str,
    temperature: float = 0.5,
    output_key: str | None = None,
    extra_metadata: dict[str, Any] | None = None,
) -> CouncilState:
    started_at = utc_now_iso()
    start_perf = time.perf_counter()
    system = _render(_get_prompt(state, stage, "system"), state)
    user = _render(_get_prompt(state, stage, "user"), state)
    try:
        output, model, usage, duration_ms, cost = _invoke_llm(system, user, temperature)
        step = AgentStepResult(
            step_name=stage,
            agent_role=agent_role,
            status="completed",
            started_at=started_at,
            duration_ms=duration_ms,
            output=output[:500],
            model_name=model,
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
            total_tokens=usage.get("total_tokens"),
            cost_usd=cost,
            metadata={
                "system_prompt_len": len(system),
                "user_prompt_len": len(user),
                "output_chars": len(output),
                **(extra_metadata or {}),
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
            output="", metadata={"error": str(exc), **(extra_metadata or {})},
        )
        updates = {"steps": [*state.get("steps", []), step.model_dump()]}
        if output_key:
            updates[output_key] = ""
        updates["error"] = str(exc)
        return updates


def manager_plan_node(state: CouncilState) -> CouncilState:
    return _run_llm_node(state, "manager_plan", "manager", temperature=0.4, output_key="generation_plan")


# ---------------------------------------------------------------------------
# Node: prospect research (Tavily fan-out + LLM synthesis)
# ---------------------------------------------------------------------------

def _tavily_prospect_context(state: CouncilState) -> tuple[str, dict[str, Any]]:
    prospect_name = state["prospect"]
    prospect_website = state.get("prospect_website")
    iteration = state.get("iteration_count", 0)
    followup_target = state.get("followup_target") or "both"
    is_followup = iteration > 0 and followup_target in {"prospect_research", "both"}
    followups = state.get("pending_followups") or []

    extracts: list[dict[str, Any]] = []
    if prospect_website and not is_followup:
        extracts = tavily_extract([prospect_website])

    if is_followup and followups:
        queries = followups[:5]
    else:
        queries = [
            f'"{prospect_name}" company overview business model',
            f'"{prospect_name}" challenges OR pain points 2026',
            f'"{prospect_name}" funding OR revenue OR growth',
            f'"{prospect_name}" leadership OR CEO OR CTO priorities',
            f'"{prospect_name}" technology stack OR infrastructure',
        ]
    search = run_parallel_searches(queries, per_query_results=4)
    text = format_tavily_context(extracts, search)
    metadata = {
        "pages_extracted": len(extracts),
        "queries_run": len(queries),
        "is_followup": is_followup,
        "followups_used": followups if is_followup else [],
    }
    return text, metadata


def prospect_research_node(state: CouncilState) -> CouncilState:
    tavily_text, meta = _tavily_prospect_context(state)
    # Inject into state so the prompt renderer can pick it up
    state_with_context: CouncilState = {**state, "tavily_web_data": tavily_text}  # local copy
    updates = _run_llm_node(
        state_with_context,
        stage="prospect_research",
        agent_role="prospect_researcher",
        temperature=0.3,
        output_key="prospect_research",
        extra_metadata={"prospect": state["prospect"], **meta},
    )
    updates["tavily_web_data"] = tavily_text
    return updates


def industry_research_node(state: CouncilState) -> CouncilState:
    return _run_llm_node(
        state,
        stage="industry_research",
        agent_role="industry_researcher",
        temperature=0.3,
        output_key="industry_research",
        extra_metadata={"prospect": state["prospect"]},
    )


# ---------------------------------------------------------------------------
# Node: seller research (Tavily + conditional Enmovil MCP + brand profile)
# ---------------------------------------------------------------------------

def _tavily_seller_context(state: CouncilState) -> tuple[str, dict[str, Any]]:
    seller_name = state["source_company"]
    seller_website = state.get("seller_website")
    iteration = state.get("iteration_count", 0)
    followup_target = state.get("followup_target") or "both"
    is_followup = iteration > 0 and followup_target in {"seller_research", "both"}
    followups = state.get("pending_followups") or []

    extracts: list[dict[str, Any]] = []
    if seller_website and not is_followup:
        extracts = tavily_extract([seller_website])

    if is_followup and followups:
        queries = followups[:3]
    else:
        queries = [
            f'"{seller_name}" products solutions',
            f'"{seller_name}" case studies customers',
            f'"{seller_name}" differentiators OR positioning',
        ]
    search = run_parallel_searches(queries, per_query_results=3)
    text = format_tavily_context(extracts, search)
    metadata = {"pages_extracted": len(extracts), "queries_run": len(queries), "is_followup": is_followup}
    return text, metadata


def seller_research_node(state: CouncilState) -> CouncilState:
    """Split-cache seller research.

    Cacheable "base": Tavily + brand + LLM synthesis of seller fundamentals.
                      Keyed by normalized seller name (upstream's _company_key).
                      Cache is bypassed when force_seller_refresh is set OR when the
                      dynamic manager requests a seller follow-up on a later iteration.

    Non-cached "addendum": Enmovil KB MCP case-study match, keyed to the CURRENT
                           prospect. Runs every time the seller is Enmovil; empty
                           otherwise.

    Final `seller_research` = base + (MCP addendum when present).
    """
    try:
        from .db import get_cached_seller_research, save_seller_research_cache
    except ImportError:
        from db import get_cached_seller_research, save_seller_research_cache

    seller_slug = state.get("seller_slug") or slugify(state["source_company"])
    source_company = state["source_company"]
    iteration = state.get("iteration_count", 0)
    followup_target = state.get("followup_target") or "both"
    force_seller_refresh = state.get("force_seller_refresh", False)
    manager_wants_refresh = iteration > 0 and followup_target in {"seller_research", "both"}
    bypass_cache = force_seller_refresh or manager_wants_refresh

    brand_md, skills_md = load_company_profile_text(seller_slug)
    new_steps: list[dict[str, Any]] = []

    # =========================================================================
    # Phase 1 — seller base (CACHEABLE: Tavily + brand + LLM synthesis, NO MCP)
    # =========================================================================
    seller_base = ""
    cache_hit = False
    cache_error: str | None = None

    if not bypass_cache:
        try:
            cached = get_cached_seller_research(source_company)
            if cached and cached.get("research_output", "").strip():
                seller_base = cached["research_output"]
                cache_hit = True
                new_steps.append(AgentStepResult(
                    step_name="seller_research_base",
                    agent_role="seller_researcher",
                    status="cached",
                    started_at=utc_now_iso(),
                    duration_ms=0.0,
                    output=seller_base[:500],
                    model_name=cached.get("model_name"),
                    input_tokens=cached.get("input_tokens"),
                    output_tokens=cached.get("output_tokens"),
                    total_tokens=cached.get("total_tokens"),
                    cost_usd=0.0,
                    metadata={
                        "cache": "hit",
                        "company": source_company,
                        "cached_at": cached.get("updated_at") or cached.get("created_at", ""),
                        "output_chars": len(seller_base),
                        "phase": "base",
                    },
                ).model_dump())
                logger.info("Seller research cache HIT for %s (base only)", source_company)
        except Exception as exc:
            cache_error = str(exc)
            logger.exception("Seller cache lookup failed; falling back to fresh run")

    tavily_text = ""
    tavily_meta: dict[str, Any] = {}

    if not cache_hit:
        # Fresh run: Tavily + brand + LLM synthesis, without MCP
        tavily_text, tavily_meta = _tavily_seller_context(state)

        base_ctx_state: CouncilState = {
            **state,
            "tavily_seller_data": tavily_text,
            "seller_brand": brand_md,
            "seller_skills": skills_md,
            "mcp_kb_result": "(MCP excluded from cacheable base — runs fresh per prospect.)",
        }

        base_started = utc_now_iso()
        base_start_perf = time.perf_counter()
        system = _render(_get_prompt(base_ctx_state, "seller_research", "system"), base_ctx_state)
        user = _render(_get_prompt(base_ctx_state, "seller_research", "user"), base_ctx_state)

        bypass_reason: str | None = (
            "force_seller_refresh" if force_seller_refresh
            else "manager_followup" if manager_wants_refresh
            else ("cache_error" if cache_error else None)
        )

        try:
            output, model, usage, duration_ms, cost = _invoke_llm(system, user, temperature=0.3)
            seller_base = output

            new_steps.append(AgentStepResult(
                step_name="seller_research_base",
                agent_role="seller_researcher",
                status="completed",
                started_at=base_started,
                duration_ms=duration_ms,
                output=output[:500],
                model_name=model,
                input_tokens=usage.get("input_tokens"),
                output_tokens=usage.get("output_tokens"),
                total_tokens=usage.get("total_tokens"),
                cost_usd=cost,
                metadata={
                    "cache": "miss",
                    "company": source_company,
                    "seller_slug": seller_slug,
                    "phase": "base",
                    "bypass_reason": bypass_reason,
                    "iteration": iteration,
                    **tavily_meta,
                },
            ).model_dump())

            # Persist base to cache (upsert on company_key via upstream helper)
            try:
                save_seller_research_cache({
                    "id": uuid4().hex,
                    "company_name": source_company,
                    "research_output": seller_base,
                    "prompt_system": system,
                    "prompt_user": user,
                    "model_name": model,
                    "input_tokens": usage.get("input_tokens"),
                    "output_tokens": usage.get("output_tokens"),
                    "total_tokens": usage.get("total_tokens"),
                    "cost_usd": cost,
                    "duration_ms": duration_ms,
                    "metadata": {
                        "phase": "base",
                        "cached_excludes_mcp": True,
                        "tavily_pages_extracted": tavily_meta.get("pages_extracted"),
                        "tavily_queries_run": tavily_meta.get("queries_run"),
                    },
                })
                logger.info("Seller research cached for %s (base only, excludes MCP)", source_company)
            except Exception:
                logger.exception("Failed to cache seller research for %s", source_company)
        except Exception as exc:
            logger.exception("Seller base synthesis failed")
            new_steps.append(AgentStepResult(
                step_name="seller_research_base",
                agent_role="seller_researcher",
                status="failed",
                started_at=base_started,
                duration_ms=round((time.perf_counter() - base_start_perf) * 1000, 2),
                output="",
                metadata={"error": str(exc), "cache": "miss", "phase": "base"},
            ).model_dump())

    # =========================================================================
    # Phase 2 — MCP addendum (PROSPECT-DEPENDENT, NEVER CACHED)
    # =========================================================================
    mcp_text = ""
    mcp_tool_names: list[str] = []
    mcp_used = False
    mcp_error: str | None = None

    if seller_slug == ENMOVIL_SELLER_SLUG:
        mcp_started = utc_now_iso()
        mcp_start_perf = time.perf_counter()
        query = (
            f"Find Enmovil case studies relevant to a prospect like {state['prospect']}. "
            "Include customer, problem, outcome, metric, source."
        )
        try:
            mcp_result = call_enmovil_mcp(query)
            mcp_text = mcp_result.get("context", "") or ""
            mcp_tool_names = mcp_result.get("tool_names", []) or []
            mcp_used = bool(mcp_text)
            mcp_error = mcp_result.get("error")
        except Exception as exc:
            logger.exception("Enmovil MCP call failed")
            mcp_error = str(exc)

        new_steps.append(AgentStepResult(
            step_name="seller_research_mcp",
            agent_role="seller_researcher",
            status="completed" if mcp_used else ("failed" if mcp_error else "skipped"),
            started_at=mcp_started,
            duration_ms=round((time.perf_counter() - mcp_start_perf) * 1000, 2),
            output=(mcp_text or mcp_error or "(no match)")[:500],
            cost_usd=0.0,
            metadata={
                "seller_slug": seller_slug,
                "prospect": state["prospect"],
                "used_mcp": mcp_used,
                "mcp_tool_names": mcp_tool_names,
                "mcp_error": mcp_error,
                "mcp_chars": len(mcp_text),
                "cacheable": False,
                "phase": "mcp_addendum",
            },
        ).model_dump())

    # =========================================================================
    # Compose: seller_research = base + (MCP addendum if present)
    # =========================================================================
    seller_research_text = seller_base
    if mcp_text:
        seller_research_text += (
            f"\n\n--- CASE STUDY MATCHES (Enmovil KB MCP, prospect: {state['prospect']}) ---\n"
            f"{mcp_text}"
        )

    return {
        "seller_research": seller_research_text,
        "tavily_seller_data": tavily_text or "(cache hit — Tavily not re-run)",
        "mcp_kb_result": mcp_text or (
            "(Enmovil MCP returned nothing for this prospect)"
            if seller_slug == ENMOVIL_SELLER_SLUG
            else "(not used — seller is not Enmovil)"
        ),
        "seller_brand": brand_md,
        "seller_skills": skills_md,
        "used_mcp": state.get("used_mcp", False) or mcp_used,
        "steps": [*state.get("steps", []), *new_steps],
    }


# ---------------------------------------------------------------------------
# Node: prospect ↔ seller fit analysis → structured SellerFitBrief
# ---------------------------------------------------------------------------

def prospect_seller_fit_node(state: CouncilState) -> CouncilState:
    started_at = utc_now_iso()
    start_perf = time.perf_counter()
    stage = "prospect_seller_fit"

    system = _render(_get_prompt(state, stage, "system"), state)
    user = _render(_get_prompt(state, stage, "user"), state)

    try:
        brief, model, usage, duration_ms, cost = _invoke_structured(
            system, user, SellerFitBrief, temperature=0.3
        )
        step = AgentStepResult(
            step_name=stage,
            agent_role="fit_analyst",
            status="completed",
            started_at=started_at,
            duration_ms=duration_ms,
            output=(brief.fit_hypothesis or "")[:500],
            model_name=model,
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
            total_tokens=usage.get("total_tokens"),
            cost_usd=cost,
            metadata={
                "fit_score": brief.fit_score,
                "addressable_pains": len(brief.addressable_pains),
                "non_addressable_pains": len(brief.non_addressable_pains),
                "mismatch_flags": len(brief.mismatch_flags),
                "has_recommended_angle": brief.recommended_angle is not None,
            },
        )
        return {
            "prospect_seller_fit": brief.model_dump(),
            "steps": [*state.get("steps", []), step.model_dump()],
        }
    except Exception as exc:
        logger.exception("prospect_seller_fit synthesis failed; emitting empty brief")
        step = AgentStepResult(
            step_name=stage,
            agent_role="fit_analyst",
            status="failed",
            started_at=started_at,
            duration_ms=round((time.perf_counter() - start_perf) * 1000, 2),
            output=f"fit brief failed: {exc}",
            metadata={"error": str(exc)},
        )
        return {
            "prospect_seller_fit": SellerFitBrief(
                prospect_slug=state.get("prospect_slug", ""),
                seller_slug=state.get("seller_slug", ""),
                mismatch_flags=[f"fit_analyst failed: {exc}"],
            ).model_dump(),
            "steps": [*state.get("steps", []), step.model_dump()],
            "error": str(exc),
        }


# ---------------------------------------------------------------------------
# Node: manager review → structured NarrativeBrief + loop-back decision
# ---------------------------------------------------------------------------

def manager_review_node(state: CouncilState) -> CouncilState:
    started_at = utc_now_iso()
    start_perf = time.perf_counter()
    iteration = state.get("iteration_count", 0)

    # Phase 1: free-text review (kept for backward-compat UI surfaces and sandbox)
    text_review = _run_llm_node(
        state, stage="manager_review", agent_role="manager",
        temperature=0.3, output_key="review_notes",
        extra_metadata={"iteration": iteration, "phase": "free_text_review"},
    )
    review_text = text_review.get("review_notes", "") or ""
    approved_flag = "VERDICT: APPROVED" in review_text.upper() if review_text else True

    # Phase 2: structured NarrativeBrief (includes verdict + followups)
    system = _skill_or_inline("narrative-synthesizer", DEFAULT_PROMPTS["manager_review"]["system"])
    user = (
        f"Seller: {state['source_company']} (slug: {state.get('seller_slug')})\n"
        f"Prospect: {state['prospect']}\n"
        f"Iteration: {iteration} (ceiling: {MAX_ITERATIONS}).\n\n"
        "Return a NarrativeBrief. If iteration has reached the ceiling, you MUST set verdict='PROCEED' "
        "and record gaps in 'caveats' instead of requesting more research.\n\n"
        f"----- FREE-TEXT REVIEW (phase 1) -----\n{review_text}\n\n"
        f"----- FIT BRIEF (primary — pain/angle already mapped) -----\n{_json.dumps(state.get('prospect_seller_fit') or {}, indent=2)}\n\n"
        f"----- SELLER RESEARCH (tone/proof context) -----\n{state.get('seller_research', '')}\n\n"
        f"----- PROSPECT RESEARCH (read-only; do not re-derive fit) -----\n{state.get('prospect_research', '')}\n\n"
        "Rules:\n"
        "- Anchor the brief on the fit brief's addressable_pains and recommended_angle. Do not smuggle raw prospect pains the fit_analyst excluded.\n"
        "- 'hook' must be EXACTLY 5 short lines, each ≤14 words. Line 1 names a specific prospect signal from the fit brief.\n"
        "- 'seller_fit' leads with recommended_angle.wedge verbatim.\n"
        "- 'relevant_case_studies' — cite from seller_research only. Never invent customers.\n"
        "- 'cta' is one line, ≤10 words, specific.\n"
        "- If fit_score < 0.3 and iteration is below ceiling, set verdict='NEEDS_MORE_RESEARCH' with targeted followups.\n"
        "- 'followups' is empty when verdict is PROCEED; when NEEDS_MORE_RESEARCH, list 2-4 raw Tavily query strings.\n"
    )

    try:
        brief, model, usage, duration_ms, cost = _invoke_structured(system, user, NarrativeBrief, temperature=0.4)
    except Exception as exc:
        logger.exception("Narrative brief synthesis failed; falling back to free-text verdict")
        step = AgentStepResult(
            step_name="narrative_brief",
            agent_role="manager",
            status="failed",
            started_at=started_at,
            duration_ms=round((time.perf_counter() - start_perf) * 1000, 2),
            output=f"structured brief failed: {exc}",
            metadata={"error": str(exc), "iteration": iteration},
        )
        text_review["approved"] = approved_flag
        text_review["verdict"] = "PROCEED" if approved_flag else "NEEDS_MORE_RESEARCH"
        text_review["iteration_count"] = iteration + (0 if approved_flag else 1)
        text_review["steps"] = [*text_review.get("steps", []), step.model_dump()]
        return text_review

    # Enforce iteration ceiling
    verdict = (brief.verdict or "PROCEED").upper()
    if verdict == "NEEDS_MORE_RESEARCH" and iteration >= MAX_ITERATIONS - 1:
        logger.info("Iteration ceiling reached; forcing PROCEED")
        brief.verdict = "PROCEED"
        brief.followups = []
        brief.caveats = list(brief.caveats) + [
            f"Iteration ceiling reached at {iteration}; proceeded with available research."
        ]
        verdict = "PROCEED"

    step = AgentStepResult(
        step_name="narrative_brief",
        agent_role="manager",
        status="completed",
        started_at=started_at,
        duration_ms=duration_ms,
        output=" | ".join(brief.hook),
        model_name=model,
        input_tokens=usage.get("input_tokens"),
        output_tokens=usage.get("output_tokens"),
        total_tokens=usage.get("total_tokens"),
        cost_usd=cost,
        metadata={
            "iteration": iteration,
            "verdict": verdict,
            "hook_lines": len(brief.hook),
            "case_studies_used": len(brief.relevant_case_studies),
            "followups": brief.followups,
            "followup_target": brief.followup_target,
        },
    )

    updates: dict[str, Any] = text_review
    updates["narrative_brief"] = brief.model_dump()
    updates["verdict"] = verdict
    updates["approved"] = verdict == "PROCEED"
    updates["pending_followups"] = brief.followups if verdict == "NEEDS_MORE_RESEARCH" else []
    updates["followup_target"] = brief.followup_target or "both"
    updates["iteration_count"] = iteration + (0 if verdict == "PROCEED" else 1)
    updates["steps"] = [*updates.get("steps", []), step.model_dump()]
    return updates


# ---------------------------------------------------------------------------
# Node: site generation (Agent 4) — structured content + HTML
# ---------------------------------------------------------------------------

def _strip_html_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```html"):
        text = text[len("```html"):].lstrip("\n")
    elif text.startswith("```"):
        text = text[3:].lstrip("\n")
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


def generate_microsite_node(state: CouncilState) -> CouncilState:
    started_at = utc_now_iso()
    start_perf = time.perf_counter()
    seller_slug = state.get("seller_slug") or slugify(state["source_company"])
    brand_md, skills_md = load_company_profile_text(seller_slug)

    # Pass 1: structured MicrositeContent
    system_struct = _skill_or_inline("site-generator", DEFAULT_PROMPTS["generate_microsite"]["system"])
    user_struct = (
        f"Seller: {state['source_company']} (slug: {seller_slug})\n"
        f"Prospect: {state['prospect']}\n\n"
        "Produce MicrositeContent with all fields. narrative_hook MUST be the 5 hook lines verbatim from the brief. "
        "stats must trace to the brief or research. Never fabricate percentages. "
        "role_pages must contain tailored sections for CIO, CFO, and Champion stakeholders within the SAME microsite. "
        "CIO should emphasize compliance, security, architecture, risk, and implementation fit. CFO should emphasize ROI framing, cost control, payback logic, and measurable outcomes. Champion should emphasize workflow pain, speed-to-win, adoption, and internal buy-in.\n\n"
        f"----- NARRATIVE BRIEF -----\n{_json.dumps(state.get('narrative_brief') or {}, indent=2)}\n\n"
        f"----- SELLER BRAND -----\n{brand_md or '(none)'}\n\n"
        f"----- SELLER SKILLS -----\n{skills_md or '(none)'}\n\n"
        f"----- PROSPECT RESEARCH -----\n{state.get('prospect_research', '')}\n\n"
        f"----- INDUSTRY RESEARCH -----\n{state.get('industry_research', '')}\n\n"
        f"----- SELLER RESEARCH -----\n{state.get('seller_research', '')}"
    )
    structured_content: MicrositeContent | None = None
    struct_meta: dict[str, Any] = {}
    try:
        content, s_model, s_usage, s_ms, s_cost = _invoke_structured(system_struct, user_struct, MicrositeContent, temperature=0.6)
        structured_content = content
        struct_meta = {
            "model": s_model,
            "input_tokens": s_usage.get("input_tokens"),
            "output_tokens": s_usage.get("output_tokens"),
            "total_tokens": s_usage.get("total_tokens"),
            "duration_ms": s_ms,
            "cost_usd": s_cost,
        }
    except Exception as exc:
        logger.exception("MicrositeContent (structured) generation failed; HTML pass will proceed independently")
        struct_meta = {"error": str(exc)}

    # Pass 2: raw HTML
    system_html = _render(_get_prompt(state, "generate_microsite", "system"), state)
    user_html = _render(_get_prompt(state, "generate_microsite", "user"), state)
    html = ""
    html_meta: dict[str, Any] = {}
    try:
        html_out, h_model, h_usage, h_ms, h_cost = _invoke_llm(system_html, user_html, temperature=0.9)
        html = _strip_html_fences(html_out)
        html_meta = {
            "model": h_model,
            "input_tokens": h_usage.get("input_tokens"),
            "output_tokens": h_usage.get("output_tokens"),
            "total_tokens": h_usage.get("total_tokens"),
            "duration_ms": h_ms,
            "cost_usd": h_cost,
            "html_chars": len(html),
        }
    except Exception as exc:
        logger.exception("HTML generation failed")
        html_meta = {"error": str(exc)}

    duration_ms = round((time.perf_counter() - start_perf) * 1000, 2)
    total_input = (struct_meta.get("input_tokens") or 0) + (html_meta.get("input_tokens") or 0)
    total_output = (struct_meta.get("output_tokens") or 0) + (html_meta.get("output_tokens") or 0)
    total_cost = (struct_meta.get("cost_usd") or 0) + (html_meta.get("cost_usd") or 0)

    status = "completed" if html or structured_content else "failed"
    step = AgentStepResult(
        step_name="generate_microsite",
        agent_role="generator",
        status=status,
        started_at=started_at,
        duration_ms=duration_ms,
        output=f"HTML={len(html)} chars, content={'yes' if structured_content else 'no'}",
        model_name=struct_meta.get("model") or html_meta.get("model"),
        input_tokens=total_input,
        output_tokens=total_output,
        total_tokens=total_input + total_output,
        cost_usd=round(total_cost, 6),
        metadata={
            "html_chars": len(html),
            "structured_emitted": bool(structured_content),
            "struct_duration_ms": struct_meta.get("duration_ms"),
            "html_duration_ms": html_meta.get("duration_ms"),
            "struct_error": struct_meta.get("error"),
            "html_error": html_meta.get("error"),
        },
    )
    updates: dict[str, Any] = {
        "final_html": html,
        "microsite_content": structured_content.model_dump() if structured_content else None,
        "role_pages": structured_content.role_pages.model_dump() if structured_content else None,
        "steps": [*state.get("steps", []), step.model_dump()],
    }
    if not html and not structured_content:
        updates["error"] = html_meta.get("error") or struct_meta.get("error") or "generation failed"
    return updates


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------

def _route_after_review(state: CouncilState) -> str:
    verdict = (state.get("verdict") or ("PROCEED" if state.get("approved", True) else "NEEDS_MORE_RESEARCH")).upper()
    if verdict == "NEEDS_MORE_RESEARCH":
        return "loop_back"
    return "generate_microsite"


@lru_cache(maxsize=1)
def build_council_graph() -> Any:
    graph = StateGraph(CouncilState)
    graph.add_node("manager_plan", manager_plan_node)
    graph.add_node("seller_research", seller_research_node)
    graph.add_node("prospect_research", prospect_research_node)
    graph.add_node("prospect_seller_fit", prospect_seller_fit_node)
    graph.add_node("manager_review", manager_review_node)
    graph.add_node("generate_microsite", generate_microsite_node)

    graph.add_edge(START, "manager_plan")
    graph.add_edge("manager_plan", "seller_research")
    graph.add_edge("manager_plan", "prospect_research")
    graph.add_edge("seller_research", "prospect_seller_fit")
    graph.add_edge("prospect_research", "prospect_seller_fit")
    graph.add_edge("prospect_seller_fit", "manager_review")

    # Dynamic loop-back: manager_review → seller_research (fan-out will replay both researchers)
    graph.add_conditional_edges(
        "manager_review",
        _route_after_review,
        {"loop_back": "seller_research", "generate_microsite": "generate_microsite"},
    )
    # Parallel loop-back edge to prospect_research
    graph.add_conditional_edges(
        "manager_review",
        lambda s: "prospect_research" if _route_after_review(s) == "loop_back" else END,
        {"prospect_research": "prospect_research", END: END},
    )

    graph.add_edge("generate_microsite", END)
    return graph.compile()


# ---------------------------------------------------------------------------
# Single-stage runner (for sandbox debugging)
# ---------------------------------------------------------------------------

def run_single_stage(
    stage: str,
    prospect: str,
    source_company: str,
    prompts: dict[str, dict[str, str]],
    context: dict[str, str] | None = None,
) -> AgentStepResult:
    state: CouncilState = {
        "run_id": uuid4().hex,
        "prospect": prospect,
        "source_company": source_company,
        "prospect_slug": slugify(prospect),
        "seller_slug": slugify(source_company),
        "prompts": prompts,
        "steps": [],
        "iteration_count": 0,
        "pending_followups": [],
        "followup_target": "both",
        "used_mcp": False,
        "generation_plan": (context or {}).get("generation_plan", ""),
        "seller_research": (context or {}).get("seller_research", ""),
        "prospect_research": (context or {}).get("prospect_research", ""),
        "review_notes": (context or {}).get("review_notes", ""),
    }

    node_map = {
        "manager_plan": manager_plan_node,
        "seller_research": seller_research_node,
        "prospect_research": prospect_research_node,
        "prospect_seller_fit": prospect_seller_fit_node,
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
    prospect_website: str | None = None,
    seller_website: str | None = None,
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
        if sp.industry_research_system or sp.industry_research_user:
            prompts["industry_research"] = {"system": sp.industry_research_system, "user": sp.industry_research_user}
        if sp.manager_review_system or sp.manager_review_user:
            prompts["manager_review"] = {"system": sp.manager_review_system, "user": sp.manager_review_user}
        if sp.generator_system or sp.generator_user:
            prompts["generate_microsite"] = {"system": sp.generator_system, "user": sp.generator_user}

    # Legacy: skill_prompt + user_prompt_template map onto the generator stage
    if not prompts.get("generate_microsite"):
        if skill_prompt.strip() or user_prompt_template.strip():
            prompts["generate_microsite"] = {"system": skill_prompt, "user": user_prompt_template}

    initial_state: CouncilState = {
        "run_id": run_id,
        "prospect": prospect,
        "source_company": source_company,
        "prospect_slug": slugify(prospect),
        "seller_slug": slugify(source_company),
        "prospect_website": prospect_website,
        "seller_website": seller_website,
        "prompts": prompts,
        "force_seller_refresh": force_seller_refresh,
        "steps": [],
        "iteration_count": 0,
        "pending_followups": [],
        "followup_target": "both",
        "used_mcp": False,
    }

    council = build_council_graph()
    try:
        final_state = council.invoke(initial_state, config={"recursion_limit": 25})
    except Exception as exc:
        logger.exception("Council graph invocation failed")
        final_state = {**initial_state, "error": str(exc)}

    steps = [AgentStepResult.model_validate(s) for s in final_state.get("steps", [])]
    total_cost = sum(s.cost_usd or 0 for s in steps)
    html = final_state.get("final_html", "") or ""
    content = final_state.get("microsite_content")
    status = "completed" if (html or content) else "failed"

    return CouncilRunResult(
        run_id=run_id,
        prospect=prospect,
        source_company=source_company,
        status=status,
        started_at=run_started_at,
        completed_at=utc_now_iso(),
        total_duration_ms=round((time.perf_counter() - run_start_perf) * 1000, 2),
        total_cost_usd=round(total_cost, 6),
        steps=steps,
        seller_research=final_state.get("seller_research", "") or "",
        prospect_research=final_state.get("prospect_research", "") or "",
        generation_plan=final_state.get("generation_plan", "") or "",
        review_notes=final_state.get("review_notes", "") or "",
        final_html=html,
        prospect_seller_fit=final_state.get("prospect_seller_fit"),
        narrative_brief=final_state.get("narrative_brief"),
        microsite_content=content,
        iterations=(final_state.get("iteration_count", 0) or 0) + 1,
        used_mcp=bool(final_state.get("used_mcp")),
    )
