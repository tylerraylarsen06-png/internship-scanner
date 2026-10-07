"""Stage the apply queue: direct link, ATS, form type, and pre-filled answers.

Writes queue/queue.json for `bin/apply`. Never submits anything, anywhere.
"""
import json
import re
from datetime import date
from pathlib import Path

from .classify import due_within
from .model import canon_url

ROOT = Path(__file__).resolve().parent.parent
QUEUE = ROOT / "queue/queue.json"

# Your answers live in config/answers.local.json (gitignored). Copy config/answers.example.json to start.
# Any question not covered there is left blank and flagged for you; never guessed.
_LOCAL = ROOT / "config/answers.local.json"
_PROFILE = json.load(open(_LOCAL if _LOCAL.exists() else ROOT / "config/answers.example.json"))
RESUME = Path(_PROFILE.pop("resume_path", "assets/resume.pdf")).expanduser()
if not RESUME.is_absolute():
    RESUME = ROOT / RESUME
ANSWERS = _PROFILE

MIN_QUEUE_FIT = 3.5  # bin/apply opens URGENT rows at or above this score

ATS = [
    ("greenhouse", re.compile(r"greenhouse\.io|gh_jid=", re.I)),
    ("lever", re.compile(r"lever\.co", re.I)),
    ("ashby", re.compile(r"ashbyhq\.com", re.I)),
    ("workday", re.compile(r"myworkdayjobs\.com|workday", re.I)),
    ("handshake", re.compile(r"joinhandshake\.com", re.I)),
    ("smartrecruiters", re.compile(r"smartrecruiters\.com", re.I)),
    ("icims", re.compile(r"icims\.com", re.I)),
]
FORM_TYPE = {
    "greenhouse": "short form: resume + profile fields, auto-filled",
    "lever": "short form: resume + profile fields, auto-filled",
    "ashby": "short form: resume + profile fields, auto-filled",
    "handshake": "one-click: Handshake quick apply with your stored resume",
    "workday": "Workday: script clicks Apply, you sign in, script autofills from resume and fills each page, stops at Review",
    "smartrecruiters": "short form: resume + profile fields",
    "icims": "full form: account required",
    "other": "manual: open and fill by hand using the answers below",
}


def detect_ats(url):
    for name, pat in ATS:
        if pat.search(url or ""):
            return name
    return "other"


def apply_url(url, ats):
    if ats == "lever" and not url.rstrip("/").endswith("/apply"):
        return url.rstrip("/") + "/apply"
    if ats == "workday" and "/apply" not in url:
        return url.rstrip("/") + "/apply"
    return url


def build(store, extra_answers=None, today=None):
    """Queue every URGENT row scoring 4+ (or due inside 30 days) that has a real posting link."""
    today = today or date.today()
    items, no_link = [], []
    for r in store.by_tab("URGENT"):
        if r.get("status") in ("applied", "passed"):
            continue
        try:
            if float(r.get("fit") or 0) < MIN_QUEUE_FIT:
                continue  # due soon but a poor fit: visible in URGENT, not opened by bin/apply
        except ValueError:
            continue
        if not canon_url(r.get("link")):  # generic careers page, not a posting: nothing to fill yet
            no_link.append(r)
            continue
        ats = detect_ats(r["link"])
        items.append({
            "key": r["key"], "company": r["company"], "role": r["role"], "deadline": r.get("deadline", ""),
            "fit": r.get("fit", ""), "ats": ats, "form": FORM_TYPE[ats],
            "url": apply_url(r["link"], ats), "posting": r["link"],
            "answers": {**ANSWERS, **(extra_answers or {}).get(r["key"], {})},
            "due14": due_within(r, today, 14),  # bin/apply opens these by default
        })
        if r.get("status") in ("", "new"):
            r["status"] = "staged"
    QUEUE.parent.mkdir(exist_ok=True)
    json.dump({"built": today.isoformat(), "resume": str(RESUME), "items": items}, open(QUEUE, "w"), indent=1)
    return items, no_link
