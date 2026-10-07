"""Seed the master list from the Part 1 triage of the old workbook (run once)."""
import json
import re
from datetime import date
from pathlib import Path

from .model import blank_row
from .model import TABS as TABS_ALL
from .store import Store

DATA = Path(__file__).resolve().parent.parent / "data"
SKIP_NAMES = re.compile(r"^(Jane Street / DE Shaw / Apple)$")


def split_name(name):
    parts = [p.strip() for p in re.split(r"\s*\|\s*", name) if p.strip()]
    if len(parts) >= 2:
        return parts[0], " | ".join(parts[1:])
    return name.strip(), name.strip()


def cell_date(v):
    m = re.match(r"(\d{4}-\d{2}-\d{2})", v or "")
    return m.group(1) if m else (v or "")


def seed(today=None):
    today = today or date.today()
    st = Store()
    counts = {}
    for t in json.load(open(DATA / "triage.json")):
        if t["bucket"] == "SOURCE" or SKIP_NAMES.match(t["name"]):
            continue
        c = t["cells"]
        if t["tab"] == "Ranked List":
            opens, deadline, link, notes = c[4], c[5], c[11], f"{c[10]} | verify: {c[12]}"
            year = ""
        else:
            year, opens, deadline, link, notes = c[3], c[5], c[6], c[7], c[8]
        company, role = split_name(t["name"])
        if company.startswith("Goldman") and re.search(r"early insight|emerging leaders", role, re.I):
            role = "Emerging Leaders Series"  # GS renamed Early Insights; one program
        row = blank_row(company=company, role=role, opens=cell_date(opens), deadline=cell_date(deadline),
                        link=link, source=f"old-sheet:{t['tab']}#{t['row']}",
                        notes=f"{notes} (old sheet: {year})".strip())
        if t["bucket"] == "KEEP" and "applied" in t["reason"].lower() and "Goldman" not in t["name"]:
            row["status"], tab, why = "applied", "APPLIED", ""
        elif t["bucket"] == "KEEP" and "Goldman Emerging Leaders: applied" in t["reason"]:
            row["status"], tab, why = "applied", "APPLIED", ""
            row["notes"] = "Applied Oct 2026 (per scope doc). " + row["notes"]
        elif t["bucket"] == "KEEP":
            tab, why = None, None
        else:
            tab, why = "RULED OUT", f"{t['bucket']}: {t['reason']}"
        if why is None:
            res = st.add(row, today)
        else:
            from .classify import enrich
            enrich(row)
            res = st.add(row, today, tab=tab, why=why or "")
            if tab == "APPLIED":
                st.rows[st.find(row)]["tab"] = "APPLIED"
        counts[res] = counts.get(res, 0) + 1
    st.save()
    return counts, {tab: len(st.by_tab(tab)) for tab in TABS_ALL}


if __name__ == "__main__":
    print(seed())
