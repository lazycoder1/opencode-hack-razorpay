from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, TypedDict
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
MICROSITES_PATH = DATA_DIR / "microsites.json"
RUNS_PATH = DATA_DIR / "generation_runs.json"
REQUESTS_PATH = DATA_DIR / "api_requests.json"
PROMPTS_PATH = DATA_DIR / "prompts.json"

load_dotenv(BASE_DIR / ".env.local")
load_dotenv(BASE_DIR / ".env.prod")

logger = logging.getLogger("website_creator")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


class GenerateMicrositesRequest(BaseModel):
    prospects: list[str] = Field(default_factory=list)


class PromptLibraryItem(BaseModel):
    id: str
    name: str
    slug: str
    stage: str
    description: str = ""
    content: str
    is_active: bool = False
    created_at: str
    updated_at: str


class PromptLibraryCreateRequest(BaseModel):
    name: str
    stage: str
    description: str = ""
    content: str


class PromptLibraryUpdateRequest(BaseModel):
    name: str
    stage: str
    description: str = ""
    content: str


class PromptActivationResponse(BaseModel):
    prompt: PromptLibraryItem
    stage: str


class MicrositeTheme(BaseModel):
    background: str
    surface: str
    accent: str
    accent_soft: str
    text: str
    muted: str


class MicrositeSection(BaseModel):
    title: str
    body: str


class GeneratedMicrositeContent(BaseModel):
    tagline: str
    headline: str
    summary: str
    cta_label: str
    visual_direction: str
    stats: list[str] = Field(min_length=3, max_length=3)
    sections: list[MicrositeSection] = Field(min_length=3, max_length=4)


class MicrositeRecord(BaseModel):
    id: str
    company_name: str
    slug: str
    tagline: str
    headline: str
    summary: str
    cta_label: str
    visual_direction: str = ""
    generated_at: str
    generation_run_id: str | None = None
    model_name: str | None = None
    theme: MicrositeTheme
    stats: list[str]
    sections: list[MicrositeSection]


class GenerateMicrositesResponse(BaseModel):
    created: list[MicrositeRecord]
    total_count: int
    failed: list[str] = Field(default_factory=list)


class RunStep(BaseModel):
    name: str
    status: str
    started_at: str
    ended_at: str
    duration_ms: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class GenerationRunRecord(BaseModel):
    id: str
    company_name: str
    status: str
    started_at: str
    completed_at: str | None = None
    total_duration_ms: float | None = None
    model_name: str | None = None
    prompt_preview: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    llm_duration_ms: float | None = None
    microsite_slug: str | None = None
    error: str | None = None
    steps: list[RunStep] = Field(default_factory=list)


class ApiRequestEvent(BaseModel):
    id: str
    path: str
    method: str
    status_code: int
    duration_ms: float
    occurred_at: str


class GenerationState(TypedDict, total=False):
    run_id: str
    company_name: str
    mcp_context: str
    mcp_server_names: list[str]
    prompt: str
    prompt_preview: str
    steps: list[dict[str, Any]]
    generated_content: dict[str, Any]
    usage: dict[str, int | None]
    model_name: str
    llm_duration_ms: float
    microsite: dict[str, Any]
    prompt_library_item_id: str
    prompt_library_item_name: str
    mcp_prompt_library_item_id: str
    mcp_prompt_library_item_name: str
    error: str


PROMPT_STAGES = {"mcp_research", "microsite_generation"}

DEFAULT_PROMPTS = [
    {
        "name": "Default MCP Research",
        "slug": "default-mcp-research",
        "stage": "mcp_research",
        "description": "Default web research brief for collecting safe public context.",
        "content": (
            "You are gathering concise external context for a first-touch outbound microsite. "
            "Use the available MCP tools to research the prospect company and return only grounded, publicly supportable details. "
            "The prospect company is: {{company_name}}. "
            "Return a short plain-text brief with: company summary, notable public signals, credible themes for personalization, "
            "and unknowns that should not be claimed. Do not invent specifics."
        ),
        "is_active": True,
    },
    {
        "name": "Default Microsite Generation",
        "slug": "default-microsite-generation",
        "stage": "microsite_generation",
        "description": "Default generation prompt for first-touch graphical microsites.",
        "content": (
            "You are generating a lightweight but visually distinctive outbound sales microsite. "
            "Create clean first-touch copy for a single prospect company. "
            "Do not invent private facts, internal initiatives, or unverified stakeholder pain. "
            "Keep the copy credible, discovery-oriented, and ready to be upgraded by a future research layer. "
            "The prospect company is: {{company_name}}. "
            "Return a visually memorable microsite package with a strong headline, concise summary, CTA, 3 stats, "
            "a visual direction sentence, and 3 to 4 short sections."
            "{{mcp_context_block}}"
        ),
        "is_active": True,
    },
]


PALETTES = [
    {
        "background": "#f7f2ea",
        "surface": "#fffaf4",
        "accent": "#d96c4d",
        "accent_soft": "#f7d8cf",
        "text": "#1f2230",
        "muted": "#5f6371",
    },
    {
        "background": "#eef6ff",
        "surface": "#f8fbff",
        "accent": "#2563eb",
        "accent_soft": "#d8e7ff",
        "text": "#172033",
        "muted": "#5a6780",
    },
    {
        "background": "#f4f2ff",
        "surface": "#fbfaff",
        "accent": "#7254d9",
        "accent_soft": "#e4dcff",
        "text": "#201f34",
        "muted": "#615f79",
    },
    {
        "background": "#edf8f2",
        "surface": "#f8fdf9",
        "accent": "#1d8f61",
        "accent_soft": "#d8f3e4",
        "text": "#15251d",
        "muted": "#587065",
    },
]


app = FastAPI(title="website-creator-api")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_storage() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for path in (MICROSITES_PATH, RUNS_PATH, REQUESTS_PATH, PROMPTS_PATH):
        if not path.exists():
            path.write_text("[]", encoding="utf-8")


def load_json_list(path: Path) -> list[dict[str, Any]]:
    ensure_storage()
    return json.loads(path.read_text(encoding="utf-8"))


def save_json_list(path: Path, values: list[dict[str, Any]]) -> None:
    ensure_storage()
    path.write_text(json.dumps(values, indent=2), encoding="utf-8")


def load_microsites() -> list[MicrositeRecord]:
    return [MicrositeRecord.model_validate(item) for item in load_json_list(MICROSITES_PATH)]


def save_microsites(records: list[MicrositeRecord]) -> None:
    save_json_list(MICROSITES_PATH, [record.model_dump() for record in records])


def load_runs() -> list[GenerationRunRecord]:
    return [GenerationRunRecord.model_validate(item) for item in load_json_list(RUNS_PATH)]


def save_runs(records: list[GenerationRunRecord]) -> None:
    save_json_list(RUNS_PATH, [record.model_dump() for record in records])


def load_request_events() -> list[ApiRequestEvent]:
    return [ApiRequestEvent.model_validate(item) for item in load_json_list(REQUESTS_PATH)]


def load_prompts() -> list[PromptLibraryItem]:
    return [PromptLibraryItem.model_validate(item) for item in load_json_list(PROMPTS_PATH)]


def save_prompts(records: list[PromptLibraryItem]) -> None:
    save_json_list(PROMPTS_PATH, [record.model_dump() for record in records])


def save_request_events(records: list[ApiRequestEvent]) -> None:
    save_json_list(REQUESTS_PATH, [record.model_dump() for record in records])


def append_request_event(event: ApiRequestEvent) -> None:
    events = load_request_events()
    events = [event, *events][:250]
    save_request_events(events)


def ensure_default_prompts() -> None:
    prompts = load_prompts()
    if prompts:
        return

    now = utc_now_iso()
    seeded = [
        PromptLibraryItem(
            id=uuid4().hex,
            name=item["name"],
            slug=item["slug"],
            stage=item["stage"],
            description=item["description"],
            content=item["content"],
            is_active=item["is_active"],
            created_at=now,
            updated_at=now,
        )
        for item in DEFAULT_PROMPTS
    ]
    save_prompts(seeded)


def normalize_prompt_stage(stage: str) -> str:
    normalized = stage.strip().lower().replace(" ", "_")
    if normalized not in PROMPT_STAGES:
        raise HTTPException(status_code=400, detail=f"Unsupported prompt stage '{stage}'")
    return normalized


def set_active_prompt_for_stage(stage: str, prompt_id: str) -> PromptLibraryItem:
    prompts = load_prompts()
    activated: PromptLibraryItem | None = None
    updated: list[PromptLibraryItem] = []

    for prompt in prompts:
        should_activate = prompt.id == prompt_id and prompt.stage == stage
        next_prompt = prompt.model_copy(
            update={
                "is_active": should_activate if prompt.stage == stage else prompt.is_active,
                "updated_at": utc_now_iso() if should_activate or (prompt.stage == stage and prompt.is_active) else prompt.updated_at,
            }
        )
        updated.append(next_prompt)
        if should_activate:
            activated = next_prompt

    if activated is None:
        raise HTTPException(status_code=404, detail=f"Prompt '{prompt_id}' was not found for stage '{stage}'")

    save_prompts(updated)
    return activated


def get_active_prompt(stage: str) -> PromptLibraryItem:
    prompts = load_prompts()
    for prompt in prompts:
        if prompt.stage == stage and prompt.is_active:
            return prompt

    for item in DEFAULT_PROMPTS:
        if item["stage"] == stage:
            now = utc_now_iso()
            fallback = PromptLibraryItem(
                id=uuid4().hex,
                name=item["name"],
                slug=item["slug"],
                stage=item["stage"],
                description=item["description"],
                content=item["content"],
                is_active=True,
                created_at=now,
                updated_at=now,
            )
            prompts.append(fallback)
            save_prompts(prompts)
            return fallback

    raise HTTPException(status_code=404, detail=f"No active prompt configured for stage '{stage}'")


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "company"


def cleaned_prospects(values: list[str]) -> list[str]:
    seen: set[str] = set()
    cleaned: list[str] = []
    for value in values:
        prospect = value.strip()
        key = prospect.casefold()
        if not prospect or key in seen:
            continue
        seen.add(key)
        cleaned.append(prospect)
    return cleaned


def pick_palette(company_name: str) -> dict[str, str]:
    digest = hashlib.sha256(company_name.encode("utf-8")).hexdigest()
    return PALETTES[int(digest[:2], 16) % len(PALETTES)]


def make_step(name: str, started_at: str, start_perf: float, status: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "started_at": started_at,
        "ended_at": utc_now_iso(),
        "duration_ms": round((time.perf_counter() - start_perf) * 1000, 2),
        "metadata": metadata or {},
    }


def get_openai_model_name() -> str:
    return os.getenv("OPENAI_MODEL", "gpt-4.1-mini")


def render_prompt_template(template: str, values: dict[str, str]) -> str:
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", value)
    return rendered


@lru_cache(maxsize=1)
def get_mcp_servers_config() -> dict[str, dict[str, Any]]:
    raw = os.getenv("MICROSITE_MCP_SERVERS_JSON", "").strip()
    if not raw:
        return {}

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("MICROSITE_MCP_SERVERS_JSON is not valid JSON") from exc

    if not isinstance(parsed, dict):
        raise RuntimeError("MICROSITE_MCP_SERVERS_JSON must decode to an object")

    server_map = parsed.get("mcpServers", parsed)
    if not isinstance(server_map, dict):
        raise RuntimeError("MICROSITE_MCP_SERVERS_JSON must contain an object of MCP servers")

    normalized: dict[str, dict[str, Any]] = {}
    for server_name, config in server_map.items():
        if not isinstance(config, dict):
            raise RuntimeError(f"MCP server '{server_name}' must be configured as an object")

        transport = str(config.get("transport", "")).strip().lower()
        if not transport:
            raise RuntimeError(f"MCP server '{server_name}' is missing a transport")

        if transport == "streamable_http":
            transport = "http"

        if transport not in {"http", "sse", "stdio"}:
            raise RuntimeError(f"MCP server '{server_name}' has unsupported transport '{transport}'")

        normalized[server_name] = {**config, "transport": transport}

    return normalized


@lru_cache(maxsize=1)
def get_llm() -> ChatOpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured for microsite generation")
    return ChatOpenAI(model=get_openai_model_name(), api_key=api_key, temperature=0.9)


def build_prompt(company_name: str, mcp_context: str = "") -> tuple[str, PromptLibraryItem]:
    prompt_item = get_active_prompt("microsite_generation")
    context_block = ""
    if mcp_context.strip():
        context_block = (
            " Use the external context below only when it is relevant and clearly supported by public evidence. "
            "If the context is incomplete or inconclusive, stay general instead of overstating certainty.\n\n"
            "External context:\n"
            f"{mcp_context.strip()}"
        )

    prompt = render_prompt_template(
        prompt_item.content,
        {
            "company_name": company_name,
            "mcp_context": mcp_context.strip(),
            "mcp_context_block": context_block,
        },
    )
    return prompt, prompt_item


def build_mcp_research_prompt(company_name: str) -> tuple[str, PromptLibraryItem]:
    prompt_item = get_active_prompt("mcp_research")
    prompt = render_prompt_template(prompt_item.content, {"company_name": company_name})
    return prompt, prompt_item


def stringify_message_content(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str) and item.strip():
                parts.append(item.strip())
                continue
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(text.strip())
        return "\n".join(parts)

    return ""


def extract_agent_text(result: Any) -> str:
    messages = result.get("messages") if isinstance(result, dict) else None
    if isinstance(messages, list):
        for message in reversed(messages):
            text = stringify_message_content(getattr(message, "content", None))
            if text:
                return text
            if isinstance(message, dict):
                text = stringify_message_content(message.get("content"))
                if text:
                    return text

    return str(result).strip()


async def collect_mcp_context(company_name: str) -> dict[str, Any]:
    server_config = get_mcp_servers_config()
    if not server_config:
        return {"context": "", "server_names": [], "tool_names": []}

    client = MultiServerMCPClient(server_config)
    tools = await client.get_tools()
    if not tools:
        return {
            "context": "",
            "server_names": list(server_config.keys()),
            "tool_names": [],
        }

    prompt, prompt_item = build_mcp_research_prompt(company_name)
    agent = create_agent(f"openai:{get_openai_model_name()}", tools)
    result = await agent.ainvoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                }
            ]
        }
    )
    return {
        "context": extract_agent_text(result),
        "server_names": list(server_config.keys()),
        "tool_names": [getattr(tool, "name", "unknown") for tool in tools],
        "prompt_item_id": prompt_item.id,
        "prompt_item_name": prompt_item.name,
    }


def run_async_task(coroutine: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coroutine)
    raise RuntimeError("Cannot run MCP tool collection from an active event loop")


def normalize_usage(raw_message: Any) -> dict[str, int | None]:
    usage_metadata = getattr(raw_message, "usage_metadata", None) or {}
    response_usage = getattr(raw_message, "response_metadata", {}).get("token_usage", {})
    return {
        "input_tokens": usage_metadata.get("input_tokens") or response_usage.get("prompt_tokens"),
        "output_tokens": usage_metadata.get("output_tokens") or response_usage.get("completion_tokens"),
        "total_tokens": usage_metadata.get("total_tokens") or response_usage.get("total_tokens"),
    }


def collect_mcp_context_node(state: GenerationState) -> GenerationState:
    started_at = utc_now_iso()
    start_perf = time.perf_counter()
    steps = [*state.get("steps", [])]

    try:
        context_payload = run_async_task(collect_mcp_context(state["company_name"]))
        step_status = "completed" if context_payload["context"] else "skipped"
        steps.append(
            make_step(
                "collect_mcp_context",
                started_at,
                start_perf,
                step_status,
                {
                    "server_names": context_payload["server_names"],
                    "tool_names": context_payload["tool_names"],
                    "context_chars": len(context_payload["context"]),
                    "prompt_item_name": context_payload.get("prompt_item_name"),
                },
            )
        )
        return {
            "mcp_context": context_payload["context"],
            "mcp_server_names": context_payload["server_names"],
            "mcp_prompt_library_item_id": context_payload.get("prompt_item_id"),
            "mcp_prompt_library_item_name": context_payload.get("prompt_item_name"),
            "steps": steps,
        }
    except Exception as exc:
        logger.exception("MCP context collection failed for %s", state["company_name"])
        steps.append(make_step("collect_mcp_context", started_at, start_perf, "failed", {"error": str(exc)}))
        return {
            "mcp_context": "",
            "mcp_server_names": [],
            "steps": steps,
        }


def prepare_prompt_node(state: GenerationState) -> GenerationState:
    started_at = utc_now_iso()
    start_perf = time.perf_counter()
    prompt, prompt_item = build_prompt(state["company_name"], state.get("mcp_context", ""))
    step = make_step(
        "prepare_prompt",
        started_at,
        start_perf,
        "completed",
        {
            "company_name": state["company_name"],
            "uses_mcp_context": bool(state.get("mcp_context", "").strip()),
            "mcp_server_names": state.get("mcp_server_names", []),
            "prompt_item_name": prompt_item.name,
        },
    )
    return {
        "prompt": prompt,
        "prompt_preview": prompt[:240],
        "prompt_library_item_id": prompt_item.id,
        "prompt_library_item_name": prompt_item.name,
        "steps": [*state.get("steps", []), step],
    }


def generate_content_node(state: GenerationState) -> GenerationState:
    started_at = utc_now_iso()
    start_perf = time.perf_counter()
    steps = [*state.get("steps", [])]

    try:
        structured_llm = get_llm().with_structured_output(GeneratedMicrositeContent, include_raw=True)
        result = structured_llm.invoke(state["prompt"])
        parsing_error = result.get("parsing_error")
        if parsing_error:
            raise parsing_error

        parsed: GeneratedMicrositeContent = result["parsed"]
        raw_message = result["raw"]
        usage = normalize_usage(raw_message)
        model_name = getattr(raw_message, "response_metadata", {}).get("model_name", get_openai_model_name())
        duration_ms = round((time.perf_counter() - start_perf) * 1000, 2)

        steps.append(
            {
                "name": "generate_content",
                "status": "completed",
                "started_at": started_at,
                "ended_at": utc_now_iso(),
                "duration_ms": duration_ms,
                "metadata": {
                    "model_name": model_name,
                    **usage,
                },
            }
        )

        return {
            "generated_content": parsed.model_dump(),
            "usage": usage,
            "model_name": model_name,
            "llm_duration_ms": duration_ms,
            "steps": steps,
        }
    except Exception as exc:
        error_text = str(exc)
        steps.append(make_step("generate_content", started_at, start_perf, "failed", {"error": error_text}))
        logger.exception("Microsite generation failed for %s", state["company_name"])
        return {
            "error": error_text,
            "model_name": get_openai_model_name(),
            "steps": steps,
        }


def finalize_microsite_node(state: GenerationState) -> GenerationState:
    if state.get("error"):
        return {"steps": state.get("steps", [])}

    started_at = utc_now_iso()
    start_perf = time.perf_counter()
    content = GeneratedMicrositeContent.model_validate(state["generated_content"])
    company_name = state["company_name"]
    microsite = MicrositeRecord(
        id=uuid4().hex,
        company_name=company_name,
        slug=f"{slugify(company_name)}-{uuid4().hex[:6]}",
        tagline=content.tagline,
        headline=content.headline,
        summary=content.summary,
        cta_label=content.cta_label,
        visual_direction=content.visual_direction,
        generated_at=utc_now_iso(),
        generation_run_id=state["run_id"],
        model_name=state.get("model_name"),
        theme=MicrositeTheme(**pick_palette(company_name)),
        stats=content.stats,
        sections=content.sections,
    )
    step = make_step(
        "finalize_microsite",
        started_at,
        start_perf,
        "completed",
        {"slug": microsite.slug},
    )
    return {
        "microsite": microsite.model_dump(),
        "steps": [*state.get("steps", []), step],
    }


@lru_cache(maxsize=1)
def get_generation_graph() -> Any:
    graph = StateGraph(GenerationState)
    graph.add_node("collect_mcp_context", collect_mcp_context_node)
    graph.add_node("prepare_prompt", prepare_prompt_node)
    graph.add_node("generate_content", generate_content_node)
    graph.add_node("finalize_microsite", finalize_microsite_node)
    graph.add_edge(START, "collect_mcp_context")
    graph.add_edge("collect_mcp_context", "prepare_prompt")
    graph.add_edge("prepare_prompt", "generate_content")
    graph.add_edge("generate_content", "finalize_microsite")
    graph.add_edge("finalize_microsite", END)
    return graph.compile()


def save_generation_run(record: GenerationRunRecord) -> None:
    runs = load_runs()
    runs = [record, *runs]
    save_runs(runs[:250])


def run_generation(company_name: str) -> tuple[MicrositeRecord | None, GenerationRunRecord]:
    started_at = utc_now_iso()
    start_perf = time.perf_counter()
    run_id = uuid4().hex
    state = get_generation_graph().invoke(
        {
            "run_id": run_id,
            "company_name": company_name,
            "steps": [],
        }
    )

    microsite_payload = state.get("microsite")
    microsite = MicrositeRecord.model_validate(microsite_payload) if microsite_payload else None
    run_record = GenerationRunRecord(
        id=run_id,
        company_name=company_name,
        status="completed" if microsite else "failed",
        started_at=started_at,
        completed_at=utc_now_iso(),
        total_duration_ms=round((time.perf_counter() - start_perf) * 1000, 2),
        model_name=state.get("model_name"),
        prompt_preview=state.get("prompt_preview"),
        input_tokens=(state.get("usage") or {}).get("input_tokens"),
        output_tokens=(state.get("usage") or {}).get("output_tokens"),
        total_tokens=(state.get("usage") or {}).get("total_tokens"),
        llm_duration_ms=state.get("llm_duration_ms"),
        microsite_slug=microsite.slug if microsite else None,
        error=state.get("error"),
        steps=[RunStep.model_validate(step) for step in state.get("steps", [])],
    )
    save_generation_run(run_record)
    return microsite, run_record


@app.middleware("http")
async def log_request_latency(request: Request, call_next):
    started_at = utc_now_iso()
    start_perf = time.perf_counter()
    status_code = 500

    try:
        response = await call_next(request)
        status_code = response.status_code
        response.headers["X-Process-Time-Ms"] = str(round((time.perf_counter() - start_perf) * 1000, 2))
        return response
    finally:
        event = ApiRequestEvent(
            id=uuid4().hex,
            path=request.url.path,
            method=request.method,
            status_code=status_code,
            duration_ms=round((time.perf_counter() - start_perf) * 1000, 2),
            occurred_at=started_at,
        )
        append_request_event(event)


@app.on_event("startup")
def on_startup() -> None:
    ensure_storage()
    ensure_default_prompts()


@app.get("/api/health")
def health() -> dict[str, Any]:
    try:
        mcp_servers = list(get_mcp_servers_config().keys())
        mcp_config_error = None
    except RuntimeError as exc:
        mcp_servers = []
        mcp_config_error = str(exc)

    return {
        "status": "ok",
        "microsites": len(load_microsites()),
        "runs": len(load_runs()),
        "prompts": len(load_prompts()),
        "model": get_openai_model_name(),
        "langsmith_tracing": os.getenv("LANGSMITH_TRACING", "false"),
        "mcp_enabled": bool(mcp_servers),
        "mcp_servers": mcp_servers,
        "mcp_config_error": mcp_config_error,
    }


@app.get("/api/mcp/status")
def mcp_status() -> dict[str, Any]:
    try:
        server_config = get_mcp_servers_config()
        return {
            "enabled": bool(server_config),
            "servers": list(server_config.keys()),
            "config_error": None,
        }
    except RuntimeError as exc:
        return {
            "enabled": False,
            "servers": [],
            "config_error": str(exc),
        }


@app.get("/api/prompts", response_model=list[PromptLibraryItem])
def list_prompts() -> list[PromptLibraryItem]:
    return load_prompts()


@app.post("/api/prompts", response_model=PromptLibraryItem, status_code=201)
def create_prompt(request: PromptLibraryCreateRequest) -> PromptLibraryItem:
    stage = normalize_prompt_stage(request.stage)
    prompts = load_prompts()
    now = utc_now_iso()
    prompt = PromptLibraryItem(
        id=uuid4().hex,
        name=request.name.strip(),
        slug=f"{slugify(request.name)}-{uuid4().hex[:6]}",
        stage=stage,
        description=request.description.strip(),
        content=request.content,
        is_active=False,
        created_at=now,
        updated_at=now,
    )
    prompts = [prompt, *prompts]
    save_prompts(prompts)
    return prompt


@app.put("/api/prompts/{prompt_id}", response_model=PromptLibraryItem)
def update_prompt(prompt_id: str, request: PromptLibraryUpdateRequest) -> PromptLibraryItem:
    stage = normalize_prompt_stage(request.stage)
    prompts = load_prompts()
    updated: PromptLibraryItem | None = None
    next_prompts: list[PromptLibraryItem] = []

    for prompt in prompts:
        if prompt.id != prompt_id:
            next_prompts.append(prompt)
            continue

        updated = prompt.model_copy(
            update={
                "name": request.name.strip(),
                "stage": stage,
                "description": request.description.strip(),
                "content": request.content,
                "updated_at": utc_now_iso(),
            }
        )
        next_prompts.append(updated)

    if updated is None:
        raise HTTPException(status_code=404, detail=f"Prompt '{prompt_id}' was not found")

    save_prompts(next_prompts)
    return updated


@app.post("/api/prompts/{prompt_id}/activate", response_model=PromptActivationResponse)
def activate_prompt(prompt_id: str) -> PromptActivationResponse:
    prompts = load_prompts()
    target = next((prompt for prompt in prompts if prompt.id == prompt_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail=f"Prompt '{prompt_id}' was not found")

    activated = set_active_prompt_for_stage(target.stage, target.id)
    return PromptActivationResponse(prompt=activated, stage=activated.stage)


@app.delete("/api/prompts/{prompt_id}", status_code=204)
def delete_prompt(prompt_id: str) -> None:
    prompts = load_prompts()
    target = next((prompt for prompt in prompts if prompt.id == prompt_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail=f"Prompt '{prompt_id}' was not found")
    if target.is_active:
        raise HTTPException(status_code=400, detail="Active prompts cannot be deleted")

    save_prompts([prompt for prompt in prompts if prompt.id != prompt_id])


@app.post("/api/microsites/generate-batch", response_model=GenerateMicrositesResponse)
def generate_batch(request: GenerateMicrositesRequest) -> GenerateMicrositesResponse:
    prospects = cleaned_prospects(request.prospects)
    if not prospects:
        raise HTTPException(status_code=400, detail="At least one prospect is required")

    records = load_microsites()
    created: list[MicrositeRecord] = []
    failed: list[str] = []

    for prospect in prospects:
        microsite, run = run_generation(prospect)
        if microsite is None:
            failed.append(f"{prospect}: {run.error or 'generation failed'}")
            continue
        created.append(microsite)

    all_records = created + records
    save_microsites(all_records)
    return GenerateMicrositesResponse(created=created, total_count=len(all_records), failed=failed)


@app.get("/api/microsites", response_model=list[MicrositeRecord])
def list_microsites() -> list[MicrositeRecord]:
    return load_microsites()


@app.get("/api/microsites/by-slug/{slug}", response_model=MicrositeRecord)
def get_microsite_by_slug(slug: str) -> MicrositeRecord:
    for record in load_microsites():
        if record.slug == slug:
            return record
    raise HTTPException(status_code=404, detail=f"Microsite '{slug}' was not found")


@app.get("/api/observability/runs", response_model=list[GenerationRunRecord])
def list_generation_runs() -> list[GenerationRunRecord]:
    return load_runs()


@app.get("/api/observability/runs/{run_id}", response_model=GenerationRunRecord)
def get_generation_run(run_id: str) -> GenerationRunRecord:
    for run in load_runs():
        if run.id == run_id:
            return run
    raise HTTPException(status_code=404, detail=f"Run '{run_id}' was not found")


@app.get("/api/observability/requests", response_model=list[ApiRequestEvent])
def list_api_requests(limit: int = 50) -> list[ApiRequestEvent]:
    return load_request_events()[:limit]
