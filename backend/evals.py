"""Named eval set for council-generated microsites.

Run manually: python3 -m backend.evals
Each test case runs the council pipeline and checks output against named assertions.
Results are persisted to the eval_results table in Postgres.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any
from uuid import uuid4

try:
    from .council import run_council
    from .db import ensure_schema, save_eval_result
except ImportError:
    from council import run_council
    from db import ensure_schema, save_eval_result

logger = logging.getLogger("evals")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


# ---------------------------------------------------------------------------
# Default skill + prompt (same as sandbox defaults)
# ---------------------------------------------------------------------------

DEFAULT_SKILL = (
    "You are a world-class frontend designer and developer. "
    "You create distinctive, production-grade HTML microsites with exceptional attention to aesthetic details. "
    "Return ONLY a single, complete, self-contained HTML document. No markdown fences, no explanation. "
    "The HTML must be a complete standalone page with inline CSS, responsive design, and Google Fonts."
)

DEFAULT_PROMPT = (
    "Create a sales microsite for a partnership pitch: {{source_company}} selling to {{company_name}}. "
    "Include a hero section, 3-4 value propositions, stats, a CTA section, and a footer. "
    "Make it feel premium and modern. Return ONLY the raw HTML."
)


# ---------------------------------------------------------------------------
# Named test cases
# ---------------------------------------------------------------------------

EVAL_CASES: list[dict[str, Any]] = [
    {
        "name": "razorpay_x_zepto",
        "prospect": "Zepto",
        "source_company": "Razorpay",
        "checks": [
            {"name": "html_is_valid", "description": "Output starts with <!DOCTYPE html> or <html"},
            {"name": "contains_prospect_name", "description": "HTML mentions the prospect company"},
            {"name": "contains_source_name", "description": "HTML mentions the source company"},
            {"name": "has_cta", "description": "HTML contains a call-to-action button or link"},
            {"name": "min_length", "description": "HTML is at least 2000 chars (not a stub)"},
            {"name": "seller_research_not_empty", "description": "Seller research was produced"},
            {"name": "prospect_research_not_empty", "description": "Prospect research was produced"},
            {"name": "all_steps_completed", "description": "All 5 council steps completed"},
        ],
    },
    {
        "name": "stripe_x_swiggy",
        "prospect": "Swiggy",
        "source_company": "Stripe",
        "checks": [
            {"name": "html_is_valid", "description": "Output starts with <!DOCTYPE html> or <html"},
            {"name": "contains_prospect_name", "description": "HTML mentions the prospect company"},
            {"name": "contains_source_name", "description": "HTML mentions the source company"},
            {"name": "has_cta", "description": "HTML contains a call-to-action button or link"},
            {"name": "min_length", "description": "HTML is at least 2000 chars (not a stub)"},
            {"name": "seller_research_not_empty", "description": "Seller research was produced"},
            {"name": "prospect_research_not_empty", "description": "Prospect research was produced"},
            {"name": "all_steps_completed", "description": "All 5 council steps completed"},
        ],
    },
    {
        "name": "aws_x_flipkart",
        "prospect": "Flipkart",
        "source_company": "AWS",
        "checks": [
            {"name": "html_is_valid", "description": "Output starts with <!DOCTYPE html> or <html"},
            {"name": "contains_prospect_name", "description": "HTML mentions the prospect company"},
            {"name": "contains_source_name", "description": "HTML mentions the source company"},
            {"name": "has_cta", "description": "HTML contains a call-to-action button or link"},
            {"name": "min_length", "description": "HTML is at least 2000 chars (not a stub)"},
            {"name": "all_steps_completed", "description": "All 5 council steps completed"},
        ],
    },
    {
        "name": "cred_x_razorpay",
        "prospect": "Razorpay",
        "source_company": "CRED",
        "checks": [
            {"name": "html_is_valid", "description": "Output starts with <!DOCTYPE html> or <html"},
            {"name": "contains_prospect_name", "description": "HTML mentions the prospect company"},
            {"name": "contains_source_name", "description": "HTML mentions the source company"},
            {"name": "has_cta", "description": "HTML contains a call-to-action button or link"},
            {"name": "min_length", "description": "HTML is at least 2000 chars (not a stub)"},
            {"name": "seller_research_not_empty", "description": "Seller research was produced"},
            {"name": "prospect_research_not_empty", "description": "Prospect research was produced"},
            {"name": "all_steps_completed", "description": "All 5 council steps completed"},
        ],
    },
    {
        "name": "plaid_x_cred",
        "prospect": "CRED",
        "source_company": "Plaid",
        "checks": [
            {"name": "html_is_valid", "description": "Output starts with <!DOCTYPE html> or <html"},
            {"name": "contains_prospect_name", "description": "HTML mentions the prospect company"},
            {"name": "contains_source_name", "description": "HTML mentions the source company"},
            {"name": "min_length", "description": "HTML is at least 2000 chars (not a stub)"},
            {"name": "all_steps_completed", "description": "All 5 council steps completed"},
        ],
    },
]


# ---------------------------------------------------------------------------
# Check runner
# ---------------------------------------------------------------------------

def run_check(check_name: str, run_result: Any) -> bool:
    html = run_result.final_html or ""
    html_lower = html.lower()

    if check_name == "html_is_valid":
        return html_lower.startswith("<!doctype html") or html_lower.startswith("<html")

    if check_name == "contains_prospect_name":
        return run_result.prospect.lower() in html_lower

    if check_name == "contains_source_name":
        return run_result.source_company.lower() in html_lower

    if check_name == "has_cta":
        return bool(re.search(r"<(button|a\s)[^>]*(cta|contact|get.started|learn.more|schedule|demo|try)", html_lower))

    if check_name == "min_length":
        return len(html) >= 2000

    if check_name == "seller_research_not_empty":
        return len(run_result.seller_research.strip()) > 100

    if check_name == "prospect_research_not_empty":
        return len(run_result.prospect_research.strip()) > 100

    if check_name == "all_steps_completed":
        return len(run_result.steps) >= 5 and all(s.status == "completed" for s in run_result.steps)

    logger.warning("Unknown check: %s", check_name)
    return False


# ---------------------------------------------------------------------------
# Main eval runner
# ---------------------------------------------------------------------------

def run_eval_case(case: dict[str, Any], skill: str = DEFAULT_SKILL, prompt_template: str = DEFAULT_PROMPT) -> dict[str, Any]:
    """Run one eval case through the council and check all assertions."""
    logger.info("Running eval: %s (%s x %s)", case["name"], case["source_company"], case["prospect"])
    start = time.perf_counter()

    council_result = run_council(
        prospect=case["prospect"],
        source_company=case["source_company"],
        skill_prompt=skill,
        user_prompt_template=prompt_template,
    )

    duration_ms = round((time.perf_counter() - start) * 1000, 2)
    check_results: list[dict[str, Any]] = []
    passed = 0
    failed = 0

    for check in case["checks"]:
        result = run_check(check["name"], council_result)
        check_results.append({
            "name": check["name"],
            "description": check["description"],
            "passed": result,
        })
        if result:
            passed += 1
        else:
            failed += 1

    total = passed + failed
    status = "passed" if failed == 0 else "failed"

    eval_record = {
        "id": uuid4().hex,
        "eval_name": case["name"],
        "prospect": case["prospect"],
        "source_company": case["source_company"],
        "status": status,
        "checks": check_results,
        "passed": passed,
        "failed": failed,
        "total": total,
        "council_run_id": council_result.run_id,
        "duration_ms": duration_ms,
    }

    try:
        save_eval_result(eval_record)
        logger.info("Eval %s persisted to DB", case["name"])
    except Exception:
        logger.exception("Failed to persist eval result for %s", case["name"])

    return eval_record


def run_all_evals(skill: str = DEFAULT_SKILL, prompt_template: str = DEFAULT_PROMPT) -> list[dict[str, Any]]:
    """Run all named eval cases and return results."""
    results: list[dict[str, Any]] = []
    for case in EVAL_CASES:
        result = run_eval_case(case, skill, prompt_template)
        results.append(result)
        logger.info(
            "  %s: %s (%d/%d passed, %.1fs)",
            case["name"], result["status"], result["passed"], result["total"], result["duration_ms"] / 1000,
        )
    return results


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from dotenv import load_dotenv
    from pathlib import Path

    base = Path(__file__).resolve().parent
    load_dotenv(base / ".env.local")
    load_dotenv(base / ".env.prod")

    ensure_schema()

    print("\n=== Running eval set ===\n")
    results = run_all_evals()

    total_passed = sum(r["passed"] for r in results)
    total_failed = sum(r["failed"] for r in results)
    total_checks = sum(r["total"] for r in results)

    print(f"\n=== Eval summary: {total_passed}/{total_checks} checks passed across {len(results)} cases ===")
    for r in results:
        mark = "PASS" if r["status"] == "passed" else "FAIL"
        print(f"  [{mark}] {r['eval_name']}: {r['passed']}/{r['total']} ({r['duration_ms']/1000:.1f}s)")
    print()
