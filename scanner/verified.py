"""Firm-page verification facts. These override anything inherited from the old sheet or a guide list.

Source of truth: ~/dev/career-ops/data/program-calendar.md / .tsv (manual firm-page verification
passes, 2026-09-18 and 2026-09-22), plus config/verified_manual.yml for checks made since (e.g. NVIDIA Ignite).
`python3 -m scanner.verified` rebuilds config/verified.json from those files.
"""
import csv
import json
import re
from pathlib import Path

import yaml

from .model import company_key, norm

ROOT = Path(__file__).resolve().parent.parent
CAL = Path.home() / "dev/career-ops/data"
OUT = ROOT / "config/verified.json"
MANUAL = ROOT / "config/verified_manual.yml"

CY_MAP = {"class of 2029 eligible": "confirmed 2029", "2028 only": "2028 only", "freshman only": "freshman only",
          "unclear": "unclear"}
GENERIC = {"program", "programs", "programme", "internship", "internships", "intern", "interns", "summer", "the", "and", "of", "for", "us", "a",
           "analyst", "associate", "cycle", "or", "sheet", "row"}


def _md_table(text, heading):
    sec = text.split(heading, 1)[1]
    rows = []
    for l in sec.splitlines()[1:]:
        if l.startswith("## "):
            break  # stop at the next section; never read the following table as this one
        if l.startswith("|") and not re.match(r"^\|\s*-", l):
            rows.append([c.strip() for c in l.strip().strip("|").split("|")])
    return rows[1:]  # drop the header row


def _prog(cell):
    m = re.match(r"\[(.+?)\]\((.+?)\)", cell)
    return (m.group(1), m.group(2)) if m else (cell.strip('"'), "")


def build():
    entries = []
    for r in csv.DictReader(open(CAL / "program-calendar.tsv"), delimiter="\t"):
        cy = CY_MAP.get(r["class_year"].strip().lower(), "unclear")
        verdict = r["bucket"]
        firm_page = bool(re.search(r"verified|own (program|posting|page|internships|application)", r["verification"], re.I))
        entries.append({"company": r["firm"], "program": r["program"], "url": r["url"], "class_year": cy,
                        "verified": "y" if firm_page and cy != "unclear" else "n", "verdict": verdict,
                        "deadline": r["deadline"], "evidence": r["verification"],
                        "rule_out": "Verified ineligible on firm page: " + r["next_action"][:120]
                        if verdict == "CONFIRMED INELIGIBLE" else ""})
    md = (CAL / "program-calendar.md").read_text()
    for c in _md_table(md, "## 2. Deferred: not your class year this cycle"):
        if len(c) < 3:
            continue
        prog, url = _prog(c[1])
        cy = CY_MAP.get(c[2].lower(), "unclear")
        entries.append({"company": c[0], "program": prog, "url": url, "class_year": cy, "verified": "y",
                        "verdict": "DEFERRED", "evidence": c[3], "deadline": "",
                        "rule_out": f"Verified {cy} on firm page: {c[3][:120]}"})
    for c in _md_table(md, "## 3. Ruled out"):
        if len(c) < 4:
            continue
        prog = c[1].strip('"')
        entries.append({"company": c[0], "program": prog, "url": "", "class_year": "unclear", "verified": "y",
                        "verdict": c[2], "evidence": c[3], "deadline": "",
                        "rule_out": f"{c[2]} (firm-page check 2026-09): {c[3][:140]}"})
    if MANUAL.exists():
        entries += yaml.safe_load(open(MANUAL)) or []
    json.dump(entries, open(OUT, "w"), indent=1)
    return entries


def _tokens(s, drop_parens=True):
    s = re.sub(r"\(.*?\)", " ", s) if drop_parens else s
    return {t for t in norm(s).split() if t not in GENERIC and len(t) > 1 and not t.isdigit()}


_CACHE = None


def lookup(company, role):
    """Best verified entry for this company+role, or None. Needs a shared distinctive word in the program name."""
    global _CACHE
    if _CACHE is None:
        _CACHE = json.load(open(OUT)) if OUT.exists() else []
    ck = company_key(company)
    own = set(ck.split()) | set(norm(company).split())
    rt = _tokens(role, drop_parens=False) - own
    best, score = None, 0.0
    for e in _CACHE:
        if company_key(e["company"]) != ck and not company_key(e["company"]).startswith(ck + " ") \
                and not ck.startswith(company_key(e["company"]) + " "):
            continue
        et = _tokens(re.sub(r"(replaces|formerly) .*", "", e["program"], flags=re.I)) - own
        if not et or not rt:
            continue
        hit = len(et & rt)
        # most of the program's own distinctive words must be in the row ("Ignite" cannot be missing),
        # and at least half the row's words must belong to the program
        if hit / len(et) < 0.75 or hit / len(rt) < 0.25:
            continue
        s = hit / len(et) + 0.01 * hit / len(et | rt)  # tie-break: closer name
        if s > score:
            best, score = e, s
    return best


if __name__ == "__main__":
    print(len(build()), "verified entries")
