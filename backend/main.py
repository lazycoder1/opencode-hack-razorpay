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
import psycopg
from psycopg.types.json import Jsonb


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
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
    company_profile_id: str = "enmovil"


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
    source_company_id: str = "enmovil"
    source_company_name: str = "Enmovil"
    source_company_website: str = "https://enmovil.ai"
    source_company_logo_path: str = "/company-assets/enmovil-mark.svg"
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


class CompanyProfileRecord(BaseModel):
    id: str
    name: str
    website_url: str
    logo_path: str
    wordmark: str
    summary: str
    skills: list[str]
    brand_markdown_path: str
    skills_markdown_path: str
    brand_markdown: str
    skills_markdown: str
    theme: MicrositeTheme


class GenerationState(TypedDict, total=False):
    run_id: str
    company_name: str
    source_company_profile_id: str
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

COMPANY_PROFILE_CONFIG = {
    "enmovil": {
        "name": "Enmovil",
        "website_url": "https://enmovil.ai",
        "logo_path": "/company-assets/enmovil-mark.svg",
        "wordmark": "enmovil.ai",
        "summary": "Operational AI design language for logistics, field teams, and execution workflows.",
        "skills": ["operations storytelling", "ABX microsites", "workflow visibility", "field coordination"],
        "brand_markdown_path": "company-profiles/enmovil/brand.md",
        "skills_markdown_path": "company-profiles/enmovil/skills.md",
        "theme": {
            "background": "#0B1018",
            "surface": "#121A24",
            "accent": "#4DD6BE",
            "accent_soft": "#173F3A",
            "text": "#EFF7F4",
            "muted": "#9FB8B2",
        },
    },
    "razorpay": {
        "name": "Razorpay",
        "website_url": "https://razorpay.com",
        "logo_path": "/company-assets/razorpay-mark.svg",
        "wordmark": "Razorpay",
        "summary": "Payments-infrastructure design language with clean blue product surfaces and fintech clarity.",
        "skills": ["payments positioning", "fintech storytelling", "merchant UX", "trust and conversion"],
        "brand_markdown_path": "company-profiles/razorpay/brand.md",
        "skills_markdown_path": "company-profiles/razorpay/skills.md",
        "theme": {
            "background": "#EEF5FF",
            "surface": "#F8FBFF",
            "accent": "#2B6EF5",
            "accent_soft": "#DCE8FF",
            "text": "#13203D",
            "muted": "#5A6B8F",
        },
    },
}


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


@lru_cache(maxsize=1)
def get_database_url() -> str:
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL is not configured")
    return database_url


def get_db_connection() -> psycopg.Connection:
    return psycopg.connect(get_database_url(), autocommit=True)


def parse_iso_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)


def normalize_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        return json.loads(value)
    raise TypeError(f"Unsupported payload type: {type(value)!r}")


def ensure_database_tables() -> None:
    with get_db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS prompt_library (
                id TEXT PRIMARY KEY,
                slug TEXT NOT NULL,
                stage TEXT NOT NULL,
                is_active BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMPTZ NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL,
                payload JSONB NOT NULL
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS microsites (
                id TEXT PRIMARY KEY,
                slug TEXT NOT NULL UNIQUE,
                company_name TEXT NOT NULL,
                generated_at TIMESTAMPTZ NOT NULL,
                payload JSONB NOT NULL
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS generation_runs (
                id TEXT PRIMARY KEY,
                company_name TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at TIMESTAMPTZ NOT NULL,
                microsite_slug TEXT,
                payload JSONB NOT NULL
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS api_request_events (
                id TEXT PRIMARY KEY,
                path TEXT NOT NULL,
                method TEXT NOT NULL,
                status_code INTEGER NOT NULL,
                occurred_at TIMESTAMPTZ NOT NULL,
                payload JSONB NOT NULL
            )
            """
        )


def table_has_rows(table_name: str) -> bool:
    with get_db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(f"SELECT EXISTS (SELECT 1 FROM {table_name} LIMIT 1)")
        row = cursor.fetchone()
    return bool(row and row[0])


def trim_table(table_name: str, order_column: str, limit: int) -> None:
    with get_db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            f"""
            DELETE FROM {table_name}
            WHERE id IN (
                SELECT id FROM {table_name}
                ORDER BY {order_column} DESC
                OFFSET %s
            )
            """,
            (limit,),
        )


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
    with get_db_connection() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT payload FROM microsites ORDER BY generated_at DESC")
        rows = cursor.fetchall()
    return [MicrositeRecord.model_validate(normalize_payload(row[0])) for row in rows]


def save_microsites(records: list[MicrositeRecord]) -> None:
    with get_db_connection() as connection, connection.cursor() as cursor:
        for record in records:
            cursor.execute(
                """
                INSERT INTO microsites (id, slug, company_name, generated_at, payload)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    slug = EXCLUDED.slug,
                    company_name = EXCLUDED.company_name,
                    generated_at = EXCLUDED.generated_at,
                    payload = EXCLUDED.payload
                """,
                (
                    record.id,
                    record.slug,
                    record.company_name,
                    parse_iso_datetime(record.generated_at),
                    Jsonb(record.model_dump()),
                ),
            )


def load_runs() -> list[GenerationRunRecord]:
    with get_db_connection() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT payload FROM generation_runs ORDER BY started_at DESC")
        rows = cursor.fetchall()
    return [GenerationRunRecord.model_validate(normalize_payload(row[0])) for row in rows]


def save_runs(records: list[GenerationRunRecord]) -> None:
    with get_db_connection() as connection, connection.cursor() as cursor:
        for record in records:
            cursor.execute(
                """
                INSERT INTO generation_runs (id, company_name, status, started_at, microsite_slug, payload)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    company_name = EXCLUDED.company_name,
                    status = EXCLUDED.status,
                    started_at = EXCLUDED.started_at,
                    microsite_slug = EXCLUDED.microsite_slug,
                    payload = EXCLUDED.payload
                """,
                (
                    record.id,
                    record.company_name,
                    record.status,
                    parse_iso_datetime(record.started_at),
                    record.microsite_slug,
                    Jsonb(record.model_dump()),
                ),
            )
    trim_table("generation_runs", "started_at", 250)


def load_request_events() -> list[ApiRequestEvent]:
    with get_db_connection() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT payload FROM api_request_events ORDER BY occurred_at DESC")
        rows = cursor.fetchall()
    return [ApiRequestEvent.model_validate(normalize_payload(row[0])) for row in rows]


def load_prompts() -> list[PromptLibraryItem]:
    with get_db_connection() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT payload FROM prompt_library ORDER BY updated_at DESC")
        rows = cursor.fetchall()
    return [PromptLibraryItem.model_validate(normalize_payload(row[0])) for row in rows]


def save_prompts(records: list[PromptLibraryItem]) -> None:
    with get_db_connection() as connection, connection.cursor() as cursor:
        for record in records:
            cursor.execute(
                """
                INSERT INTO prompt_library (id, slug, stage, is_active, created_at, updated_at, payload)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    slug = EXCLUDED.slug,
                    stage = EXCLUDED.stage,
                    is_active = EXCLUDED.is_active,
                    created_at = EXCLUDED.created_at,
                    updated_at = EXCLUDED.updated_at,
                    payload = EXCLUDED.payload
                """,
                (
                    record.id,
                    record.slug,
                    record.stage,
                    record.is_active,
                    parse_iso_datetime(record.created_at),
                    parse_iso_datetime(record.updated_at),
                    Jsonb(record.model_dump()),
                ),
            )


def save_request_events(records: list[ApiRequestEvent]) -> None:
    with get_db_connection() as connection, connection.cursor() as cursor:
        for record in records:
            cursor.execute(
                """
                INSERT INTO api_request_events (id, path, method, status_code, occurred_at, payload)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    path = EXCLUDED.path,
                    method = EXCLUDED.method,
                    status_code = EXCLUDED.status_code,
                    occurred_at = EXCLUDED.occurred_at,
                    payload = EXCLUDED.payload
                """,
                (
                    record.id,
                    record.path,
                    record.method,
                    record.status_code,
                    parse_iso_datetime(record.occurred_at),
                    Jsonb(record.model_dump()),
                ),
            )
    trim_table("api_request_events", "occurred_at", 250)


def append_request_event(event: ApiRequestEvent) -> None:
    save_request_events([event])


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


def migrate_json_file_to_database() -> None:
    if not table_has_rows("prompt_library"):
        prompt_items = [PromptLibraryItem.model_validate(item) for item in load_json_list(PROMPTS_PATH)]
        if prompt_items:
            save_prompts(prompt_items)

    if not table_has_rows("microsites"):
        microsite_items = [MicrositeRecord.model_validate(item) for item in load_json_list(MICROSITES_PATH)]
        if microsite_items:
            save_microsites(microsite_items)

    if not table_has_rows("generation_runs"):
        run_items = [GenerationRunRecord.model_validate(item) for item in load_json_list(RUNS_PATH)]
        if run_items:
            save_runs(run_items)

    if not table_has_rows("api_request_events"):
        request_items = [ApiRequestEvent.model_validate(item) for item in load_json_list(REQUESTS_PATH)]
        if request_items:
            save_request_events(request_items)


def read_project_markdown(relative_path: str) -> str:
    path = PROJECT_ROOT / relative_path
    return path.read_text(encoding="utf-8")


def list_company_profiles() -> list[CompanyProfileRecord]:
    profiles: list[CompanyProfileRecord] = []
    for profile_id, config in COMPANY_PROFILE_CONFIG.items():
        profiles.append(
            CompanyProfileRecord(
                id=profile_id,
                name=config["name"],
                website_url=config["website_url"],
                logo_path=config["logo_path"],
                wordmark=config["wordmark"],
                summary=config["summary"],
                skills=config["skills"],
                brand_markdown_path=config["brand_markdown_path"],
                skills_markdown_path=config["skills_markdown_path"],
                brand_markdown=read_project_markdown(config["brand_markdown_path"]),
                skills_markdown=read_project_markdown(config["skills_markdown_path"]),
                theme=MicrositeTheme(**config["theme"]),
            )
        )
    return profiles


def get_company_profile(profile_id: str) -> CompanyProfileRecord:
    normalized = profile_id.strip().lower()
    for profile in list_company_profiles():
        if profile.id == normalized:
            return profile
    raise HTTPException(status_code=404, detail=f"Company profile '{profile_id}' was not found")


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


def get_company_prompt_context(company_profile: CompanyProfileRecord) -> str:
    skills = ", ".join(company_profile.skills)
    return (
        f"Selected source company: {company_profile.name} ({company_profile.website_url}).\n"
        f"Brand summary: {company_profile.summary}\n"
        f"Skill emphasis: {skills}\n\n"
        f"Brand guide:\n{company_profile.brand_markdown.strip()}\n\n"
        f"Skills guide:\n{company_profile.skills_markdown.strip()}"
    )


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


def build_prompt(
    company_name: str,
    source_company_profile: CompanyProfileRecord,
    mcp_context: str = "",
) -> tuple[str, PromptLibraryItem]:
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
            "source_company_name": source_company_profile.name,
            "source_company_website": source_company_profile.website_url,
            "source_company_context": get_company_prompt_context(source_company_profile),
        },
    )
    prompt = (
        f"{prompt}\n\n"
        "Source company context:\n"
        f"{get_company_prompt_context(source_company_profile)}"
    )
    return prompt, prompt_item


def build_mcp_research_prompt(
    company_name: str,
    source_company_profile: CompanyProfileRecord,
) -> tuple[str, PromptLibraryItem]:
    prompt_item = get_active_prompt("mcp_research")
    prompt = render_prompt_template(
        prompt_item.content,
        {
            "company_name": company_name,
            "source_company_name": source_company_profile.name,
            "source_company_website": source_company_profile.website_url,
            "source_company_context": get_company_prompt_context(source_company_profile),
        },
    )
    prompt = (
        f"{prompt}\n\n"
        "Source company context:\n"
        f"{get_company_prompt_context(source_company_profile)}"
    )
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


async def collect_mcp_context(company_name: str, source_company_profile: CompanyProfileRecord) -> dict[str, Any]:
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

    prompt, prompt_item = build_mcp_research_prompt(company_name, source_company_profile)
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
        source_company_profile = get_company_profile(state["source_company_profile_id"])
        context_payload = run_async_task(collect_mcp_context(state["company_name"], source_company_profile))
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
                    "source_company": source_company_profile.name,
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
    source_company_profile = get_company_profile(state["source_company_profile_id"])
    prompt, prompt_item = build_prompt(
        state["company_name"],
        source_company_profile,
        state.get("mcp_context", ""),
    )
    step = make_step(
        "prepare_prompt",
        started_at,
        start_perf,
        "completed",
        {
            "company_name": state["company_name"],
            "source_company": source_company_profile.name,
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
    source_company_profile = get_company_profile(state["source_company_profile_id"])
    microsite = MicrositeRecord(
        id=uuid4().hex,
        company_name=company_name,
        slug=f"{slugify(company_name)}-{uuid4().hex[:6]}",
        source_company_id=source_company_profile.id,
        source_company_name=source_company_profile.name,
        source_company_website=source_company_profile.website_url,
        source_company_logo_path=source_company_profile.logo_path,
        tagline=content.tagline,
        headline=content.headline,
        summary=content.summary,
        cta_label=content.cta_label,
        visual_direction=content.visual_direction,
        generated_at=utc_now_iso(),
        generation_run_id=state["run_id"],
        model_name=state.get("model_name"),
        theme=source_company_profile.theme,
        stats=content.stats,
        sections=content.sections,
    )
    step = make_step(
        "finalize_microsite",
        started_at,
        start_perf,
        "completed",
        {"slug": microsite.slug, "source_company": source_company_profile.name},
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


def run_generation(company_name: str, source_company_profile_id: str) -> tuple[MicrositeRecord | None, GenerationRunRecord]:
    started_at = utc_now_iso()
    start_perf = time.perf_counter()
    run_id = uuid4().hex
    source_company_profile = get_company_profile(source_company_profile_id)
    state = get_generation_graph().invoke(
        {
            "run_id": run_id,
            "company_name": company_name,
            "source_company_profile_id": source_company_profile.id,
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
        steps=[
            RunStep.model_validate(
                {
                    **step,
                    "metadata": {
                        **step.get("metadata", {}),
                        "source_company": step.get("metadata", {}).get("source_company", source_company_profile.name),
                    },
                }
            )
            for step in state.get("steps", [])
        ],
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
    ensure_database_tables()
    migrate_json_file_to_database()
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
        "persistence": "postgres",
        "microsites": len(load_microsites()),
        "runs": len(load_runs()),
        "prompts": len(load_prompts()),
        "company_profiles": len(COMPANY_PROFILE_CONFIG),
        "model": get_openai_model_name(),
        "langsmith_tracing": os.getenv("LANGSMITH_TRACING", "false"),
        "mcp_enabled": bool(mcp_servers),
        "mcp_servers": mcp_servers,
        "mcp_config_error": mcp_config_error,
    }


@app.get("/api/company-profiles", response_model=list[CompanyProfileRecord])
def get_company_profiles() -> list[CompanyProfileRecord]:
    return list_company_profiles()


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


@app.delete("/api/prompts/{prompt_id}")
def delete_prompt(prompt_id: str) -> dict[str, bool]:
    prompts = load_prompts()
    target = next((prompt for prompt in prompts if prompt.id == prompt_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail=f"Prompt '{prompt_id}' was not found")
    if target.is_active:
        raise HTTPException(status_code=400, detail="Active prompts cannot be deleted")

    save_prompts([prompt for prompt in prompts if prompt.id != prompt_id])
    return {"deleted": True}


@app.post("/api/microsites/generate-batch", response_model=GenerateMicrositesResponse)
def generate_batch(request: GenerateMicrositesRequest) -> GenerateMicrositesResponse:
    prospects = cleaned_prospects(request.prospects)
    if not prospects:
        raise HTTPException(status_code=400, detail="At least one prospect is required")

    source_company_profile = get_company_profile(request.company_profile_id)

    records = load_microsites()
    created: list[MicrositeRecord] = []
    failed: list[str] = []

    for prospect in prospects:
        microsite, run = run_generation(prospect, source_company_profile.id)
        if microsite is None:
            failed.append(f"{source_company_profile.name} x {prospect}: {run.error or 'generation failed'}")
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


class SandboxStepResult(BaseModel):
    step_name: str
    status: str
    started_at: str
    duration_ms: float
    output: str
    model_name: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SandboxRunRecord(BaseModel):
    run_id: str
    prospect: str
    source_company: str
    status: str
    started_at: str
    completed_at: str
    total_duration_ms: float
    steps: list[SandboxStepResult]
    final_html: str


class SandboxPromptRequest(BaseModel):
    system_prompt: str = Field(description="Skill/system instructions for the LLM")
    user_prompt: str = Field(description="User message template. Use {{company_name}} as placeholder.")
    prospect: str = Field(description="Prospect company name, e.g. Zepto")
    source_company: str = Field(default="", description="Source company name for context, e.g. Razorpay")
    model: str | None = None


class SandboxStepRequest(BaseModel):
    system_prompt: str
    user_prompt: str
    model: str | None = None


@app.post("/api/sandbox/step/render-prompt", response_model=SandboxStepResult)
def sandbox_render_prompt(request: SandboxPromptRequest) -> SandboxStepResult:
    started_at = utc_now_iso()
    start_perf = time.perf_counter()
    rendered = request.user_prompt.replace("{{company_name}}", request.prospect)
    rendered = rendered.replace("{{source_company}}", request.source_company)
    return SandboxStepResult(
        step_name="render_prompt",
        status="completed",
        started_at=started_at,
        duration_ms=round((time.perf_counter() - start_perf) * 1000, 2),
        output=rendered,
        metadata={
            "prospect": request.prospect,
            "source_company": request.source_company,
            "system_prompt_length": len(request.system_prompt),
            "user_prompt_length": len(rendered),
        },
    )


@app.post("/api/sandbox/step/generate", response_model=SandboxStepResult)
def sandbox_step_generate(request: SandboxStepRequest) -> SandboxStepResult:
    started_at = utc_now_iso()
    start_perf = time.perf_counter()
    model_name = request.model or get_openai_model_name()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY is not configured")

    try:
        llm = ChatOpenAI(model=model_name, api_key=api_key, temperature=0.9)
        result = llm.invoke([
            {"role": "system", "content": request.system_prompt},
            {"role": "user", "content": request.user_prompt},
        ])
        duration_ms = round((time.perf_counter() - start_perf) * 1000, 2)
        usage = normalize_usage(result)
        actual_model = getattr(result, "response_metadata", {}).get("model_name", model_name)
        raw_html = stringify_message_content(result.content)

        return SandboxStepResult(
            step_name="generate_html",
            status="completed",
            started_at=started_at,
            duration_ms=duration_ms,
            output=raw_html,
            model_name=actual_model,
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
            total_tokens=usage.get("total_tokens"),
            metadata={"model_requested": model_name, "model_used": actual_model},
        )
    except Exception as exc:
        return SandboxStepResult(
            step_name="generate_html",
            status="failed",
            started_at=started_at,
            duration_ms=round((time.perf_counter() - start_perf) * 1000, 2),
            output="",
            model_name=model_name,
            metadata={"error": str(exc)},
        )


SANDBOX_RUNS_PATH = DATA_DIR / "sandbox_runs.json"


def load_sandbox_runs() -> list[dict[str, Any]]:
    if not SANDBOX_RUNS_PATH.exists():
        return []
    return load_json_list(SANDBOX_RUNS_PATH)


def save_sandbox_run(record: SandboxRunRecord) -> None:
    runs = load_sandbox_runs()
    runs = [record.model_dump(), *runs]
    save_json_list(SANDBOX_RUNS_PATH, runs[:100])


@app.post("/api/sandbox/run", response_model=SandboxRunRecord)
def sandbox_full_run(request: SandboxPromptRequest) -> SandboxRunRecord:
    run_id = uuid4().hex
    run_started_at = utc_now_iso()
    run_start_perf = time.perf_counter()
    steps: list[SandboxStepResult] = []

    prompt_result = sandbox_render_prompt(request)
    steps.append(prompt_result)
    rendered_prompt = prompt_result.output

    gen_request = SandboxStepRequest(
        system_prompt=request.system_prompt,
        user_prompt=rendered_prompt,
        model=request.model,
    )
    gen_result = sandbox_step_generate(gen_request)
    steps.append(gen_result)

    html = gen_result.output
    if "```html" in html:
        html = html.replace("```html\n", "").replace("```\n", "").replace("```", "")
    html = html.strip()

    status = "completed" if gen_result.status == "completed" and html else "failed"
    record = SandboxRunRecord(
        run_id=run_id,
        prospect=request.prospect,
        source_company=request.source_company,
        status=status,
        started_at=run_started_at,
        completed_at=utc_now_iso(),
        total_duration_ms=round((time.perf_counter() - run_start_perf) * 1000, 2),
        steps=steps,
        final_html=html,
    )
    save_sandbox_run(record)
    return record


@app.get("/api/sandbox/runs")
def list_sandbox_runs() -> list[dict[str, Any]]:
    return load_sandbox_runs()


@app.post("/api/sandbox/generate", response_model=SandboxStepResult)
def sandbox_generate_compat(request: SandboxStepRequest) -> SandboxStepResult:
    return sandbox_step_generate(request)


@app.get("/api/observability/requests", response_model=list[ApiRequestEvent])
def list_api_requests(limit: int = 50) -> list[ApiRequestEvent]:
    return load_request_events()[:limit]
