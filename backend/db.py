"""Postgres data layer using psycopg (sync).

Tables:
    council_runs     – full council pipeline run records
    microsites       – generated HTML microsites with slugs for serving
    eval_results     – eval set run results
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

logger = logging.getLogger("db")


def get_db_url() -> str:
    url = os.getenv("DATABASE_URL", "")
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    return url


def get_conn() -> psycopg.Connection:
    return psycopg.connect(get_db_url())


# ---------------------------------------------------------------------------
# Schema bootstrap
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS council_runs (
    run_id          TEXT PRIMARY KEY,
    prospect        TEXT NOT NULL,
    source_company  TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at    TIMESTAMPTZ,
    total_duration_ms DOUBLE PRECISION,
    total_cost_usd  DOUBLE PRECISION,
    steps           JSONB NOT NULL DEFAULT '[]',
    seller_research TEXT NOT NULL DEFAULT '',
    prospect_research TEXT NOT NULL DEFAULT '',
    generation_plan TEXT NOT NULL DEFAULT '',
    review_notes    TEXT NOT NULL DEFAULT '',
    final_html      TEXT NOT NULL DEFAULT '',
    skill_prompt    TEXT NOT NULL DEFAULT '',
    user_prompt_template TEXT NOT NULL DEFAULT '',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS microsites (
    id              TEXT PRIMARY KEY,
    slug            TEXT UNIQUE NOT NULL,
    company_name    TEXT NOT NULL,
    source_company  TEXT NOT NULL DEFAULT '',
    headline        TEXT NOT NULL DEFAULT '',
    tagline         TEXT NOT NULL DEFAULT '',
    summary         TEXT NOT NULL DEFAULT '',
    html            TEXT NOT NULL DEFAULT '',
    council_run_id  TEXT REFERENCES council_runs(run_id),
    metadata        JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_microsites_slug ON microsites(slug);

CREATE TABLE IF NOT EXISTS eval_results (
    id              TEXT PRIMARY KEY,
    eval_name       TEXT NOT NULL,
    prospect        TEXT NOT NULL,
    source_company  TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',
    checks          JSONB NOT NULL DEFAULT '[]',
    passed          INTEGER NOT NULL DEFAULT 0,
    failed          INTEGER NOT NULL DEFAULT 0,
    total           INTEGER NOT NULL DEFAULT 0,
    council_run_id  TEXT,
    duration_ms     DOUBLE PRECISION,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


def ensure_schema() -> None:
    """Create tables if they don't exist."""
    try:
        with get_conn() as conn:
            conn.execute(SCHEMA_SQL)
            conn.commit()
        logger.info("Database schema ensured")
    except Exception:
        logger.exception("Failed to ensure database schema")
        raise


# ---------------------------------------------------------------------------
# Council runs
# ---------------------------------------------------------------------------

def save_council_run(run: dict[str, Any]) -> None:
    sql = """
    INSERT INTO council_runs (
        run_id, prospect, source_company, status, started_at, completed_at,
        total_duration_ms, total_cost_usd, steps,
        seller_research, prospect_research, generation_plan, review_notes,
        final_html, skill_prompt, user_prompt_template
    ) VALUES (
        %(run_id)s, %(prospect)s, %(source_company)s, %(status)s,
        %(started_at)s, %(completed_at)s,
        %(total_duration_ms)s, %(total_cost_usd)s, %(steps)s,
        %(seller_research)s, %(prospect_research)s, %(generation_plan)s, %(review_notes)s,
        %(final_html)s, %(skill_prompt)s, %(user_prompt_template)s
    )
    ON CONFLICT (run_id) DO UPDATE SET
        status = EXCLUDED.status,
        completed_at = EXCLUDED.completed_at,
        total_duration_ms = EXCLUDED.total_duration_ms,
        total_cost_usd = EXCLUDED.total_cost_usd,
        steps = EXCLUDED.steps,
        seller_research = EXCLUDED.seller_research,
        prospect_research = EXCLUDED.prospect_research,
        generation_plan = EXCLUDED.generation_plan,
        review_notes = EXCLUDED.review_notes,
        final_html = EXCLUDED.final_html
    """
    with get_conn() as conn:
        conn.execute(sql, {
            **run,
            "steps": Jsonb(run.get("steps", [])),
            "skill_prompt": run.get("skill_prompt", ""),
            "user_prompt_template": run.get("user_prompt_template", ""),
        })
        conn.commit()


def list_council_runs(limit: int = 50) -> list[dict[str, Any]]:
    sql = "SELECT * FROM council_runs ORDER BY created_at DESC LIMIT %s"
    with get_conn() as conn:
        cur = conn.execute(sql, (limit,))
        cols = [desc.name for desc in cur.description]
        rows = cur.fetchall()
    return [_row_to_dict(cols, row) for row in rows]


def get_council_run(run_id: str) -> dict[str, Any] | None:
    sql = "SELECT * FROM council_runs WHERE run_id = %s"
    with get_conn() as conn:
        cur = conn.execute(sql, (run_id,))
        cols = [desc.name for desc in cur.description]
        row = cur.fetchone()
    return _row_to_dict(cols, row) if row else None


# ---------------------------------------------------------------------------
# Microsites (HTML storage + slug serving)
# ---------------------------------------------------------------------------

def save_microsite(record: dict[str, Any]) -> None:
    sql = """
    INSERT INTO microsites (
        id, slug, company_name, source_company, headline, tagline, summary,
        html, council_run_id, metadata
    ) VALUES (
        %(id)s, %(slug)s, %(company_name)s, %(source_company)s,
        %(headline)s, %(tagline)s, %(summary)s,
        %(html)s, %(council_run_id)s, %(metadata)s
    )
    ON CONFLICT (slug) DO UPDATE SET
        html = EXCLUDED.html,
        headline = EXCLUDED.headline,
        summary = EXCLUDED.summary,
        metadata = EXCLUDED.metadata
    """
    with get_conn() as conn:
        conn.execute(sql, {
            **record,
            "metadata": Jsonb(record.get("metadata", {})),
        })
        conn.commit()


def list_microsites_db(limit: int = 100) -> list[dict[str, Any]]:
    sql = "SELECT * FROM microsites ORDER BY created_at DESC LIMIT %s"
    with get_conn() as conn:
        cur = conn.execute(sql, (limit,))
        cols = [desc.name for desc in cur.description]
        rows = cur.fetchall()
    return [_row_to_dict(cols, row) for row in rows]


def get_microsite_by_slug(slug: str) -> dict[str, Any] | None:
    sql = "SELECT * FROM microsites WHERE slug = %s"
    with get_conn() as conn:
        cur = conn.execute(sql, (slug,))
        cols = [desc.name for desc in cur.description]
        row = cur.fetchone()
    return _row_to_dict(cols, row) if row else None


def get_microsite_html(slug: str) -> str | None:
    sql = "SELECT html FROM microsites WHERE slug = %s"
    with get_conn() as conn:
        cur = conn.execute(sql, (slug,))
        row = cur.fetchone()
    return row[0] if row else None


# ---------------------------------------------------------------------------
# Eval results
# ---------------------------------------------------------------------------

def save_eval_result(record: dict[str, Any]) -> None:
    sql = """
    INSERT INTO eval_results (
        id, eval_name, prospect, source_company, status, checks,
        passed, failed, total, council_run_id, duration_ms
    ) VALUES (
        %(id)s, %(eval_name)s, %(prospect)s, %(source_company)s, %(status)s, %(checks)s,
        %(passed)s, %(failed)s, %(total)s, %(council_run_id)s, %(duration_ms)s
    )
    """
    with get_conn() as conn:
        conn.execute(sql, {
            **record,
            "checks": Jsonb(record.get("checks", [])),
        })
        conn.commit()


def list_eval_results(limit: int = 50) -> list[dict[str, Any]]:
    sql = "SELECT * FROM eval_results ORDER BY created_at DESC LIMIT %s"
    with get_conn() as conn:
        cur = conn.execute(sql, (limit,))
        cols = [desc.name for desc in cur.description]
        rows = cur.fetchall()
    return [_row_to_dict(cols, row) for row in rows]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row_to_dict(cols: list[str], row: tuple) -> dict[str, Any]:
    d: dict[str, Any] = {}
    for col, val in zip(cols, row):
        if isinstance(val, datetime):
            d[col] = val.isoformat()
        else:
            d[col] = val
    return d
