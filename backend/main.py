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

load_dotenv(BASE_DIR / ".env.local")
load_dotenv(BASE_DIR / ".env.prod")

logger = logging.getLogger("website_creator")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


class GenerateMicrositesRequest(BaseModel):
    prospects: list[str] = Field(default_factory=list)


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
    error: str


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
    for path in (MICROSITES_PATH, RUNS_PATH, REQUESTS_PATH):
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


def save_request_events(records: list[ApiRequestEvent]) -> None:
    save_json_list(REQUESTS_PATH, [record.model_dump() for record in records])


def append_request_event(event: ApiRequestEvent) -> None:
    events = load_request_events()
    events = [event, *events][:250]
    save_request_events(events)


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


def build_prompt(company_name: str, mcp_context: str = "") -> str:
    prompt = (
        "You are generating a lightweight but visually distinctive outbound sales microsite. "
        "Create clean first-touch copy for a single prospect company. "
        "Do not invent private facts, internal initiatives, or unverified stakeholder pain. "
        "Keep the copy credible, discovery-oriented, and ready to be upgraded by a future research layer. "
        f"The prospect company is: {company_name}. "
        "Return a visually memorable microsite package with a strong headline, concise summary, CTA, 3 stats, "
        "a visual direction sentence, and 3 to 4 short sections."
    )

    if not mcp_context.strip():
        return prompt

    return (
        f"{prompt} "
        "Use the external context below only when it is relevant and clearly supported by public evidence. "
        "If the context is incomplete or inconclusive, stay general instead of overstating certainty.\n\n"
        "External context:\n"
        f"{mcp_context.strip()}"
    )


def build_mcp_research_prompt(company_name: str) -> str:
    return (
        "You are gathering concise external context for a first-touch outbound microsite. "
        "Use the available MCP tools to research the prospect company and return only grounded, publicly supportable details. "
        f"The prospect company is: {company_name}. "
        "Return a short plain-text brief with: company summary, notable public signals, credible themes for personalization, "
        "and unknowns that should not be claimed. Do not invent specifics."
    )


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

    agent = create_agent(f"openai:{get_openai_model_name()}", tools)
    result = await agent.ainvoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": build_mcp_research_prompt(company_name),
                }
            ]
        }
    )
    return {
        "context": extract_agent_text(result),
        "server_names": list(server_config.keys()),
        "tool_names": [getattr(tool, "name", "unknown") for tool in tools],
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
                },
            )
        )
        return {
            "mcp_context": context_payload["context"],
            "mcp_server_names": context_payload["server_names"],
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
    prompt = build_prompt(state["company_name"], state.get("mcp_context", ""))
    step = make_step(
        "prepare_prompt",
        started_at,
        start_perf,
        "completed",
        {
            "company_name": state["company_name"],
            "uses_mcp_context": bool(state.get("mcp_context", "").strip()),
            "mcp_server_names": state.get("mcp_server_names", []),
        },
    )
    return {
        "prompt": prompt,
        "prompt_preview": prompt[:240],
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
