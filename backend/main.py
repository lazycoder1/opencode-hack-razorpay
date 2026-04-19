from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
STORAGE_PATH = DATA_DIR / "microsites.json"


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


class MicrositeRecord(BaseModel):
    id: str
    company_name: str
    slug: str
    tagline: str
    headline: str
    summary: str
    cta_label: str
    generated_at: str
    theme: MicrositeTheme
    stats: list[str]
    sections: list[MicrositeSection]


class GenerateMicrositesResponse(BaseModel):
    created: list[MicrositeRecord]
    total_count: int


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


def ensure_storage() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not STORAGE_PATH.exists():
        STORAGE_PATH.write_text("[]", encoding="utf-8")


def load_records() -> list[MicrositeRecord]:
    ensure_storage()
    raw = json.loads(STORAGE_PATH.read_text(encoding="utf-8"))
    return [MicrositeRecord.model_validate(item) for item in raw]


def save_records(records: list[MicrositeRecord]) -> None:
    ensure_storage()
    STORAGE_PATH.write_text(
        json.dumps([record.model_dump() for record in records], indent=2),
        encoding="utf-8",
    )


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


def generate_sections(company_name: str) -> list[MicrositeSection]:
    return [
        MicrositeSection(
            title="Signal",
            body=(
                f"{company_name} gets a first-pass narrative page with a clear opening story, bold title, "
                "and sections that are ready for a future research-backed upgrade."
            ),
        ),
        MicrositeSection(
            title="Storyline",
            body=(
                f"This barebones version frames {company_name} as a priority account and gives the team a visual "
                "microsite instead of a static internal document."
            ),
        ),
        MicrositeSection(
            title="Next move",
            body=(
                "When the research workflow is ready, this page can swap the placeholder storyline for research-led "
                "copy, proof points, and account-specific sections."
            ),
        ),
    ]


def generate_stats(company_name: str) -> list[str]:
    word_count = max(2, len(company_name.split()))
    return [
        f"{word_count} narrative blocks",
        "Unique visual palette",
        "Ready for research enrichment",
    ]


def generate_microsite(company_name: str) -> MicrositeRecord:
    palette = pick_palette(company_name)
    slug = f"{slugify(company_name)}-{uuid4().hex[:6]}"
    generated_at = datetime.now(UTC).isoformat()

    return MicrositeRecord(
        id=uuid4().hex,
        company_name=company_name,
        slug=slug,
        tagline="Manual prospect to graphical microsite",
        headline=f"{company_name}, reframed as a live microsite",
        summary=(
            f"A lightweight account page for {company_name} that gives your team a visual starting point today. "
            "This is intentionally barebones and ready for research-driven upgrades later."
        ),
        cta_label="Open a discovery-ready walkthrough",
        generated_at=generated_at,
        theme=MicrositeTheme(**palette),
        stats=generate_stats(company_name),
        sections=generate_sections(company_name),
    )


@app.on_event("startup")
def on_startup() -> None:
    ensure_storage()


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "microsites": len(load_records())}


@app.post("/api/microsites/generate-batch", response_model=GenerateMicrositesResponse)
def generate_batch(request: GenerateMicrositesRequest) -> GenerateMicrositesResponse:
    prospects = cleaned_prospects(request.prospects)
    records = load_records()
    created = [generate_microsite(prospect) for prospect in prospects]
    all_records = created + records
    save_records(all_records)
    return GenerateMicrositesResponse(created=created, total_count=len(all_records))


@app.get("/api/microsites", response_model=list[MicrositeRecord])
def list_microsites() -> list[MicrositeRecord]:
    return load_records()


@app.get("/api/microsites/by-slug/{slug}", response_model=MicrositeRecord)
def get_microsite_by_slug(slug: str) -> MicrositeRecord:
    for record in load_records():
        if record.slug == slug:
            return record
    raise ValueError(f"Microsite '{slug}' was not found")
