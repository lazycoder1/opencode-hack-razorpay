"""Postgres data layer using psycopg (sync).

Tables:
    council_runs            – full council pipeline run records
    council_stage_artifacts – persisted stage outputs and approval states
    council_prompt_library  – tenant-scoped council prompts
    microsites              – generated HTML microsites with slugs for serving
    eval_results            – eval set run results
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

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
    council_run_id  TEXT,
    metadata        JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_microsites_slug ON microsites(slug);

CREATE TABLE IF NOT EXISTS seller_research_cache (
    id              TEXT PRIMARY KEY,
    company_name    TEXT NOT NULL,
    company_key     TEXT UNIQUE NOT NULL,
    research_output TEXT NOT NULL DEFAULT '',
    prompt_system   TEXT NOT NULL DEFAULT '',
    prompt_user     TEXT NOT NULL DEFAULT '',
    model_name      TEXT,
    input_tokens    INTEGER,
    output_tokens   INTEGER,
    total_tokens    INTEGER,
    cost_usd        DOUBLE PRECISION,
    duration_ms     DOUBLE PRECISION,
    metadata        JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_seller_cache_key ON seller_research_cache(company_key);

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

MIGRATIONS_SQL = [
    # --- council_runs new columns ---
    "ALTER TABLE council_runs ADD COLUMN IF NOT EXISTS tenant_key TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE council_runs ADD COLUMN IF NOT EXISTS industry_research TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE council_runs ADD COLUMN IF NOT EXISTS narrative_brief JSONB NOT NULL DEFAULT '{}'",
    "ALTER TABLE council_runs ADD COLUMN IF NOT EXISTS microsite_content JSONB NOT NULL DEFAULT '{}'",
    "ALTER TABLE council_runs ADD COLUMN IF NOT EXISTS role_pages JSONB NOT NULL DEFAULT '{}'",
    "ALTER TABLE council_runs ADD COLUMN IF NOT EXISTS approved BOOLEAN NOT NULL DEFAULT FALSE",
    "ALTER TABLE council_runs ADD COLUMN IF NOT EXISTS verdict TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE council_runs ADD COLUMN IF NOT EXISTS iteration_count INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE council_runs ADD COLUMN IF NOT EXISTS pending_followups JSONB NOT NULL DEFAULT '[]'",
    "ALTER TABLE council_runs ADD COLUMN IF NOT EXISTS followup_target TEXT NOT NULL DEFAULT ''",
    # --- microsites new columns ---
    "ALTER TABLE microsites ADD COLUMN IF NOT EXISTS source_company TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE microsites ADD COLUMN IF NOT EXISTS tenant_key TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE microsites ADD COLUMN IF NOT EXISTS headline TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE microsites ADD COLUMN IF NOT EXISTS tagline TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE microsites ADD COLUMN IF NOT EXISTS summary TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE microsites ADD COLUMN IF NOT EXISTS council_run_id TEXT",
    # --- indexes ---
    "CREATE INDEX IF NOT EXISTS idx_council_runs_tenant_created ON council_runs(tenant_key, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_microsites_tenant_created ON microsites(tenant_key, created_at DESC)",
    # --- backfill tenant_key from source_company ---
    "UPDATE council_runs SET tenant_key = regexp_replace(lower(source_company), '[^a-z0-9]+', '-', 'g') WHERE tenant_key = '' AND source_company <> ''",
    "UPDATE microsites SET tenant_key = regexp_replace(lower(source_company), '[^a-z0-9]+', '-', 'g') WHERE tenant_key = '' AND source_company <> ''",
    # --- new tables: council_stage_artifacts ---
    """CREATE TABLE IF NOT EXISTS council_stage_artifacts (
        id              TEXT PRIMARY KEY,
        run_id          TEXT NOT NULL,
        tenant_key      TEXT NOT NULL DEFAULT '',
        stage           TEXT NOT NULL,
        artifact_type   TEXT NOT NULL DEFAULT 'stage_output',
        approval_state  TEXT NOT NULL DEFAULT 'pending_review',
        approval_notes  TEXT NOT NULL DEFAULT '',
        payload         JSONB NOT NULL DEFAULT '{}',
        created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        UNIQUE(run_id, stage, artifact_type)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_stage_artifacts_run ON council_stage_artifacts(run_id, stage)",
    "CREATE INDEX IF NOT EXISTS idx_stage_artifacts_tenant ON council_stage_artifacts(tenant_key, updated_at DESC)",
    # --- new tables: council_prompt_library ---
    """CREATE TABLE IF NOT EXISTS council_prompt_library (
        id              TEXT PRIMARY KEY,
        tenant_key      TEXT NOT NULL,
        stage           TEXT NOT NULL,
        name            TEXT NOT NULL,
        system_prompt   TEXT NOT NULL DEFAULT '',
        user_prompt     TEXT NOT NULL DEFAULT '',
        is_active       BOOLEAN NOT NULL DEFAULT FALSE,
        metadata        JSONB NOT NULL DEFAULT '{}',
        created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
    )""",
    "CREATE INDEX IF NOT EXISTS idx_council_prompt_tenant_stage ON council_prompt_library(tenant_key, stage, updated_at DESC)",
]


def ensure_schema() -> None:
    """Create tables if they don't exist, then run migrations for existing tables."""
    try:
        # Phase 1: create original tables
        with get_conn() as conn:
            conn.execute(SCHEMA_SQL)
            conn.commit()
    except Exception:
        logger.warning("Base schema creation had issues (tables may already exist)")

    # Phase 2: run each migration independently so one failure doesn't block others
    for statement in MIGRATIONS_SQL:
        try:
            with get_conn() as conn:
                conn.execute(statement)
                conn.commit()
        except Exception as exc:
            # Swallow expected errors like "column already exists" or "relation already exists"
            err_str = str(exc).lower()
            if "already exists" in err_str or "duplicate" in err_str:
                pass
            else:
                logger.warning("Migration statement failed (non-fatal): %s — %s", statement[:80], exc)

    logger.info("Database schema ensured")


def tenant_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-") or "default"


# ---------------------------------------------------------------------------
# Council runs
# ---------------------------------------------------------------------------

def save_council_run(run: dict[str, Any]) -> None:
    sql = """
    INSERT INTO council_runs (
        run_id, tenant_key, prospect, source_company, status, started_at, completed_at,
        total_duration_ms, total_cost_usd, steps,
        seller_research, prospect_research, generation_plan, review_notes,
        final_html, skill_prompt, user_prompt_template, industry_research,
        narrative_brief, microsite_content, role_pages,
        approved, verdict, iteration_count, pending_followups, followup_target
    ) VALUES (
        %(run_id)s, %(tenant_key)s, %(prospect)s, %(source_company)s, %(status)s,
        %(started_at)s, %(completed_at)s,
        %(total_duration_ms)s, %(total_cost_usd)s, %(steps)s,
        %(seller_research)s, %(prospect_research)s, %(generation_plan)s, %(review_notes)s,
        %(final_html)s, %(skill_prompt)s, %(user_prompt_template)s, %(industry_research)s,
        %(narrative_brief)s, %(microsite_content)s, %(role_pages)s,
        %(approved)s, %(verdict)s, %(iteration_count)s, %(pending_followups)s, %(followup_target)s
    )
    ON CONFLICT (run_id) DO UPDATE SET
        tenant_key = EXCLUDED.tenant_key,
        status = EXCLUDED.status,
        completed_at = EXCLUDED.completed_at,
        total_duration_ms = EXCLUDED.total_duration_ms,
        total_cost_usd = EXCLUDED.total_cost_usd,
        steps = EXCLUDED.steps,
        seller_research = EXCLUDED.seller_research,
        prospect_research = EXCLUDED.prospect_research,
        generation_plan = EXCLUDED.generation_plan,
        review_notes = EXCLUDED.review_notes,
        final_html = EXCLUDED.final_html,
        industry_research = EXCLUDED.industry_research,
        narrative_brief = EXCLUDED.narrative_brief,
        microsite_content = EXCLUDED.microsite_content,
        role_pages = EXCLUDED.role_pages,
        approved = EXCLUDED.approved,
        verdict = EXCLUDED.verdict,
        iteration_count = EXCLUDED.iteration_count,
        pending_followups = EXCLUDED.pending_followups,
        followup_target = EXCLUDED.followup_target
    """
    with get_conn() as conn:
        conn.execute(sql, {
            **run,
            "tenant_key": run.get("tenant_key") or tenant_key(run.get("source_company", "")),
            "steps": Jsonb(run.get("steps", [])),
            "skill_prompt": run.get("skill_prompt", ""),
            "user_prompt_template": run.get("user_prompt_template", ""),
            "industry_research": run.get("industry_research", ""),
            "narrative_brief": Jsonb(run.get("narrative_brief", {})),
            "microsite_content": Jsonb(run.get("microsite_content", {})),
            "role_pages": Jsonb(run.get("role_pages", {})),
            "approved": run.get("approved", False),
            "verdict": run.get("verdict", ""),
            "iteration_count": run.get("iteration_count", 0),
            "pending_followups": Jsonb(run.get("pending_followups", [])),
            "followup_target": run.get("followup_target", ""),
        })
        conn.commit()


def list_council_runs(limit: int = 50, source_company: str | None = None) -> list[dict[str, Any]]:
    if source_company:
        sql = "SELECT * FROM council_runs WHERE tenant_key = %s ORDER BY created_at DESC LIMIT %s"
        params = (tenant_key(source_company), limit)
    else:
        sql = "SELECT * FROM council_runs ORDER BY created_at DESC LIMIT %s"
        params = (limit,)
    with get_conn() as conn:
        cur = conn.execute(sql, params)
        cols = [desc.name for desc in cur.description]
        rows = cur.fetchall()
    return [_row_to_dict(cols, row) for row in rows]


def get_council_run(run_id: str, source_company: str | None = None) -> dict[str, Any] | None:
    if source_company:
        sql = "SELECT * FROM council_runs WHERE run_id = %s AND tenant_key = %s"
        params = (run_id, tenant_key(source_company))
    else:
        sql = "SELECT * FROM council_runs WHERE run_id = %s"
        params = (run_id,)
    with get_conn() as conn:
        cur = conn.execute(sql, params)
        cols = [desc.name for desc in cur.description]
        row = cur.fetchone()
    return _row_to_dict(cols, row) if row else None


# ---------------------------------------------------------------------------
# Microsites (HTML storage + slug serving)
# ---------------------------------------------------------------------------

def save_microsite(record: dict[str, Any]) -> None:
    sql = """
    INSERT INTO microsites (
        id, slug, company_name, tenant_key, source_company, headline, tagline, summary,
        html, council_run_id, metadata
    ) VALUES (
        %(id)s, %(slug)s, %(company_name)s, %(tenant_key)s, %(source_company)s,
        %(headline)s, %(tagline)s, %(summary)s,
        %(html)s, %(council_run_id)s, %(metadata)s
    )
    ON CONFLICT (slug) DO UPDATE SET
        tenant_key = EXCLUDED.tenant_key,
        html = EXCLUDED.html,
        headline = EXCLUDED.headline,
        summary = EXCLUDED.summary,
        metadata = EXCLUDED.metadata
    """
    with get_conn() as conn:
        conn.execute(sql, {
            **record,
            "tenant_key": record.get("tenant_key") or tenant_key(record.get("source_company", "")),
            "metadata": Jsonb(record.get("metadata", {})),
        })
        conn.commit()


def list_microsites_db(limit: int = 100, source_company: str | None = None) -> list[dict[str, Any]]:
    if source_company:
        sql = "SELECT * FROM microsites WHERE tenant_key = %s ORDER BY created_at DESC LIMIT %s"
        params = (tenant_key(source_company), limit)
    else:
        sql = "SELECT * FROM microsites ORDER BY created_at DESC LIMIT %s"
        params = (limit,)
    with get_conn() as conn:
        cur = conn.execute(sql, params)
        cols = [desc.name for desc in cur.description]
        rows = cur.fetchall()
    return [_row_to_dict(cols, row) for row in rows]


def get_microsite_by_slug(slug: str, source_company: str | None = None) -> dict[str, Any] | None:
    if source_company:
        sql = "SELECT * FROM microsites WHERE slug = %s AND tenant_key = %s"
        params = (slug, tenant_key(source_company))
    else:
        sql = "SELECT * FROM microsites WHERE slug = %s"
        params = (slug,)
    with get_conn() as conn:
        cur = conn.execute(sql, params)
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
# Tenant-scoped council prompt library
# ---------------------------------------------------------------------------

def list_council_prompts(tenant: str) -> list[dict[str, Any]]:
    sql = "SELECT * FROM council_prompt_library WHERE tenant_key = %s ORDER BY stage, updated_at DESC"
    with get_conn() as conn:
        cur = conn.execute(sql, (tenant_key(tenant),))
        cols = [desc.name for desc in cur.description]
        rows = cur.fetchall()
    return [_row_to_dict(cols, row) for row in rows]


def get_active_council_prompt(tenant: str, stage: str) -> dict[str, Any] | None:
    sql = "SELECT * FROM council_prompt_library WHERE tenant_key = %s AND stage = %s AND is_active = TRUE ORDER BY updated_at DESC LIMIT 1"
    with get_conn() as conn:
        cur = conn.execute(sql, (tenant_key(tenant), stage))
        cols = [desc.name for desc in cur.description]
        row = cur.fetchone()
    return _row_to_dict(cols, row) if row else None


def save_council_prompt(record: dict[str, Any]) -> None:
    sql = """
    INSERT INTO council_prompt_library (
        id, tenant_key, stage, name, system_prompt, user_prompt, is_active, metadata
    ) VALUES (
        %(id)s, %(tenant_key)s, %(stage)s, %(name)s, %(system_prompt)s, %(user_prompt)s, %(is_active)s, %(metadata)s
    )
    ON CONFLICT (id) DO UPDATE SET
        tenant_key = EXCLUDED.tenant_key,
        stage = EXCLUDED.stage,
        name = EXCLUDED.name,
        system_prompt = EXCLUDED.system_prompt,
        user_prompt = EXCLUDED.user_prompt,
        is_active = EXCLUDED.is_active,
        metadata = EXCLUDED.metadata,
        updated_at = now()
    """
    with get_conn() as conn:
        conn.execute(sql, {
            **record,
            "id": record.get("id") or uuid4().hex,
            "tenant_key": tenant_key(record.get("tenant_key") or record.get("source_company") or "default"),
            "metadata": Jsonb(record.get("metadata", {})),
        })
        conn.commit()


def activate_council_prompt(tenant: str, prompt_id: str) -> dict[str, Any] | None:
    tk = tenant_key(tenant)
    with get_conn() as conn:
        cur = conn.execute(
            "SELECT stage FROM council_prompt_library WHERE id = %s AND tenant_key = %s",
            (prompt_id, tk),
        )
        row = cur.fetchone()
        if not row:
            return None
        stage = row[0]
        conn.execute(
            "UPDATE council_prompt_library SET is_active = FALSE, updated_at = now() WHERE tenant_key = %s AND stage = %s",
            (tk, stage),
        )
        conn.execute(
            "UPDATE council_prompt_library SET is_active = TRUE, updated_at = now() WHERE id = %s AND tenant_key = %s",
            (prompt_id, tk),
        )
        conn.commit()
    return get_active_council_prompt(tenant, stage)


# ---------------------------------------------------------------------------
# Stage artifacts and approvals
# ---------------------------------------------------------------------------

def save_stage_artifact(record: dict[str, Any]) -> None:
    sql = """
    INSERT INTO council_stage_artifacts (
        id, run_id, tenant_key, stage, artifact_type, approval_state, approval_notes, payload
    ) VALUES (
        %(id)s, %(run_id)s, %(tenant_key)s, %(stage)s, %(artifact_type)s, %(approval_state)s, %(approval_notes)s, %(payload)s
    )
    ON CONFLICT (run_id, stage, artifact_type) DO UPDATE SET
        approval_state = EXCLUDED.approval_state,
        approval_notes = EXCLUDED.approval_notes,
        payload = EXCLUDED.payload,
        updated_at = now()
    """
    with get_conn() as conn:
        conn.execute(sql, {
            **record,
            "id": record.get("id") or uuid4().hex,
            "tenant_key": tenant_key(record.get("tenant_key") or record.get("source_company") or "default"),
            "artifact_type": record.get("artifact_type", "stage_output"),
            "approval_state": record.get("approval_state", "pending_review"),
            "approval_notes": record.get("approval_notes", ""),
            "payload": Jsonb(record.get("payload", {})),
        })
        conn.commit()


def list_stage_artifacts(run_id: str) -> list[dict[str, Any]]:
    sql = "SELECT * FROM council_stage_artifacts WHERE run_id = %s ORDER BY created_at ASC"
    with get_conn() as conn:
        cur = conn.execute(sql, (run_id,))
        cols = [desc.name for desc in cur.description]
        rows = cur.fetchall()
    return [_row_to_dict(cols, row) for row in rows]


def get_stage_artifact(run_id: str, stage: str) -> dict[str, Any] | None:
    sql = "SELECT * FROM council_stage_artifacts WHERE run_id = %s AND stage = %s ORDER BY updated_at DESC LIMIT 1"
    with get_conn() as conn:
        cur = conn.execute(sql, (run_id, stage))
        cols = [desc.name for desc in cur.description]
        row = cur.fetchone()
    return _row_to_dict(cols, row) if row else None


def update_stage_approval(run_id: str, stage: str, approval_state: str, approval_notes: str = "") -> bool:
    sql = "UPDATE council_stage_artifacts SET approval_state = %s, approval_notes = %s, updated_at = now() WHERE run_id = %s AND stage = %s"
    with get_conn() as conn:
        cur = conn.execute(sql, (approval_state, approval_notes, run_id, stage))
        conn.commit()
        return (cur.rowcount or 0) > 0


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
# Seller research cache
# ---------------------------------------------------------------------------

def _company_key(name: str) -> str:
    """Normalize company name to a stable cache key."""
    return name.strip().lower().replace(" ", "_")


def get_cached_seller_research(company_name: str) -> dict[str, Any] | None:
    sql = "SELECT * FROM seller_research_cache WHERE company_key = %s"
    with get_conn() as conn:
        cur = conn.execute(sql, (_company_key(company_name),))
        cols = [desc.name for desc in cur.description]
        row = cur.fetchone()
    return _row_to_dict(cols, row) if row else None


def save_seller_research_cache(record: dict[str, Any]) -> None:
    sql = """
    INSERT INTO seller_research_cache (
        id, company_name, company_key, research_output,
        prompt_system, prompt_user, model_name,
        input_tokens, output_tokens, total_tokens,
        cost_usd, duration_ms, metadata
    ) VALUES (
        %(id)s, %(company_name)s, %(company_key)s, %(research_output)s,
        %(prompt_system)s, %(prompt_user)s, %(model_name)s,
        %(input_tokens)s, %(output_tokens)s, %(total_tokens)s,
        %(cost_usd)s, %(duration_ms)s, %(metadata)s
    )
    ON CONFLICT (company_key) DO UPDATE SET
        research_output = EXCLUDED.research_output,
        prompt_system = EXCLUDED.prompt_system,
        prompt_user = EXCLUDED.prompt_user,
        model_name = EXCLUDED.model_name,
        input_tokens = EXCLUDED.input_tokens,
        output_tokens = EXCLUDED.output_tokens,
        total_tokens = EXCLUDED.total_tokens,
        cost_usd = EXCLUDED.cost_usd,
        duration_ms = EXCLUDED.duration_ms,
        metadata = EXCLUDED.metadata,
        updated_at = now()
    """
    with get_conn() as conn:
        conn.execute(sql, {
            **record,
            "company_key": _company_key(record["company_name"]),
            "metadata": Jsonb(record.get("metadata", {})),
        })
        conn.commit()


def invalidate_seller_research_cache(company_name: str) -> bool:
    sql = "DELETE FROM seller_research_cache WHERE company_key = %s"
    with get_conn() as conn:
        cur = conn.execute(sql, (_company_key(company_name),))
        conn.commit()
        return (cur.rowcount or 0) > 0


def list_seller_research_cache() -> list[dict[str, Any]]:
    sql = "SELECT id, company_name, company_key, model_name, input_tokens, output_tokens, cost_usd, duration_ms, created_at, updated_at, length(research_output) as output_chars FROM seller_research_cache ORDER BY updated_at DESC"
    with get_conn() as conn:
        cur = conn.execute(sql)
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
