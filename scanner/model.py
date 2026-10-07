"""Row shape, tabs, and the dedup key shared by every part of the scanner."""
import re
from urllib.parse import urlsplit

COLUMNS = [
    "company", "role", "tier", "class_year", "opens", "deadline", "location", "link",
    "source", "verified", "fit", "status", "date_found", "decision_maker", "dm_email",
    "outreach_status", "notes", "key",
]
HEADERS = [
    "Company", "Role", "Tier", "Class-year eligibility", "Opens", "Deadline", "Location", "Link",
    "Source", "Verified on firm page", "Fit (1-5)", "Status", "Date found", "Decision maker",
    "Their email", "Outreach status", "Notes", "key",
]
TABS = ["URGENT", "URGENT (SUB 3)", "PIPELINE", "APPLIED", "RULED OUT"]

# Columns you own once a row exists. The scanner never overwrites a non-empty value here.
USER_OWNED = {"status", "decision_maker", "dm_email", "outreach_status", "notes"}

CLASS_YEAR = ("confirmed 2029", "2028 only", "unclear", "none stated")

_STOP = re.compile(
    r"\b(summer|winter|spring|fall|autumn|20\d\d|intern(ship)?s?|program(me)?|usa?|united states|"
    r"remote|hybrid|onsite|on-site|new york|los angeles|san francisco|london|nyc|ny|ca|la|sf|us|"
    r"[sfw]2[5-9]|soph|sophomore|the|and|of|for|-)\b"
)


def norm(s):
    s = (s or "").lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


COMPANY_ALIASES = {
    "jpmorgan chase": "jpmorgan", "jp morgan": "jpmorgan", "jpmorganchase": "jpmorgan",
    "goldman sachs": "goldman", "morgan stanley": "morgan stanley", "bank of america": "bofa",
    "the walt disney company": "disney", "walt disney": "disney", "fox corporation": "fox",
    "fox": "fox", "l e k consulting": "lek", "lek consulting": "lek", "l e k": "lek",
    "pwc strategy": "pwc", "strategy and pwc": "pwc", "capital one": "capital one",
    "snap inc": "snap", "meta platforms": "meta", "nvidia corporation": "nvidia",
}


def company_key(name):
    n = norm(name)
    n = re.sub(r"\b(inc|llc|corp|corporation|co|company|group|holdings|ltd)\b", "", n).strip()
    return COMPANY_ALIASES.get(n, n)


def role_key(role):
    r = _STOP.sub(" ", norm(role))
    return re.sub(r"\s+", " ", r).strip()


def row_key(company, role):
    return f"{company_key(company)}|{role_key(role)}"


SPECIFIC = re.compile(r"(\d{4,}|/jobs?/|/postings?/|/requisition|jobs\.lever\.co/[^/]+/.+|ashbyhq\.com/[^/]+/.+|"
                      r"[?&](gh_jid|jobid|job_id|id)=)", re.I)


def canon_url(url):
    """Canonical form of a posting URL, or '' for a generic careers page (never a merge key)."""
    if not url or not SPECIFIC.search(url):
        return ""
    p = urlsplit(url.strip())
    path = re.sub(r"/(apply|application)/?$", "", p.path.rstrip("/"))
    return f"{p.netloc.lower().removeprefix('www.')}{path}"


def blank_row(**kw):
    row = {c: "" for c in COLUMNS}
    row.update({k: v for k, v in kw.items() if v is not None})
    if not row["key"]:
        row["key"] = row_key(row["company"], row["role"])
    return row
