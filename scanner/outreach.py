"""Decision-maker layer for URGENT rows scoring 4+.

Order of operations, every time:
  1. Company-level Do Not Contact check (current clients and partner orgs). Before any lookup or spend.
  2. Person found (alumni network first, then a paid lookup with email verification).
  3. Person-level DNC check (email, LinkedIn, name+firm). Fail closed if the DNC list is unreadable.
  4. Draft anchored to the opening, validated against the outreach module's hard rules. Never sent from here.

The DNC list and draft rules live in a separate private module (not published), found via OUTREACH_MODULE.
"""
import json
import os
import re
import sys
from pathlib import Path

OF = Path(os.environ.get("OUTREACH_MODULE", Path.home() / "dev/outreach-finder"))
sys.path.insert(0, str(OF))
import dnc  # noqa: E402  the private DNC module, the single source of the policy
from drafts import validate_draft  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
from .stage import ANSWERS  # noqa: E402
CANDIDATES = ROOT / "queue/outreach_candidates.json"


def _entries():
    entries = dnc.load()  # raises DNCError if missing or unreadable: fail closed
    if not entries:
        raise dnc.DNCError("DNC list is empty; refusing to run outreach")
    return entries


def company_blocked(company, entries=None):
    """Org-level hits (Tier C clients, Tier D partner orgs). Ambiguous counts as blocked."""
    hits = dnc.check({"name": "", "firm": company}, entries or _entries())
    return [dnc.reason_text(h) for h in hits]


def person_blocked(person, company, entries=None):
    row = {"name": person.get("name", ""), "firm": company, "email": person.get("email", ""),
           "linkedin_url": person.get("linkedin", "")}
    hits = dnc.check(row, entries or _entries())
    if hits:
        dnc.log_exclusion(row, hits, context="internship-scanner")
    return [dnc.reason_text(h) for h in hits]


def _clean_role(role):
    role = re.sub(r"\b(19|20)\d\d\b", "", role)          # no digits in the copy
    role = re.sub(r"\s*[-–—|:]\s*", " ", role)           # no dashes either
    return re.sub(r"\s+", " ", role).strip(" ,")


def draft(first_name, company, role, why_line=None):
    """Five sentences max, one ask, 15 minutes, anchored to the live opening. Returns (subject, body, violations)."""
    r = _clean_role(role)
    why_line = why_line or ("That work put me close to the problems this team works on, and I want to hear "
                            "how the role looks from the inside.")
    subject = f"{r} at {company}"
    body = (
        f"Hi {first_name},\n\n"
        f"I saw {company} is hiring for the {r} role, and I'm applying. "
        f"{ANSWERS.get('intro_line', '')} "
        f"{why_line} "
        f"Would you have 15 minutes this week or next, before I submit?\n\n"
        f"{ANSWERS.get('first_name', '')}"
    )
    return subject, body, validate_draft(subject, body)


def build_candidates(store):
    """URGENT, fit 4+, no decision maker yet, company not blocked. Written for the Claude step to work."""
    entries = _entries()
    out, blocked = [], []
    for r in store.by_tab("URGENT"):
        try:
            if float(r.get("fit") or 0) < 4.0 or r.get("decision_maker"):
                continue
        except ValueError:
            continue
        why = company_blocked(r["company"], entries)
        if why:
            blocked.append({"company": r["company"], "role": r["role"], "dnc": why})
            continue
        out.append({"key": r["key"], "company": r["company"], "role": r["role"], "link": r["link"],
                    "deadline": r.get("deadline", "")})
    CANDIDATES.parent.mkdir(exist_ok=True)
    json.dump({"candidates": out, "blocked_by_dnc": blocked}, open(CANDIDATES, "w"), indent=1)
    return out, blocked


if __name__ == "__main__":
    from .store import Store
    c, b = build_candidates(Store())
    print(f"{len(c)} candidate(s), {len(b)} blocked by DNC")
    s, body, v = draft("Jordan", "Fox", "Summer 2027 FOX Corporation Internship Program - Business and Legal Affairs")
    print(s, "\n", body, "\nviolations:", v)
