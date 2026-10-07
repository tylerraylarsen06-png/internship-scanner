"""Free sources: career-ops ATS scan output and the GitHub lists. No credits."""
import csv
import json
import re
import subprocess
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from .model import blank_row

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CAREER_OPS = Path.home() / "dev/career-ops"

GITHUB_JSON = {
    "SimplifyJobs": "https://raw.githubusercontent.com/SimplifyJobs/Summer2027-Internships/dev/.github/scripts/listings.json",
    "vanshb03": "https://raw.githubusercontent.com/vanshb03/Summer2027-Internships/dev/.github/scripts/listings.json",
    "pittcsc": "https://raw.githubusercontent.com/pittcsc/Summer2027-Internships/dev/.github/scripts/listings.json",
}
ZAPPLY = "https://raw.githubusercontent.com/zapplyjobs/underclassmen-internships/main/README.md"

# Simplify-style lists are ~90% SWE/hardware. Keep what fits the profile; named
# underclassman programs always pass, whatever their category.
KEEP_CATEGORY = re.compile(r"product", re.I)
KEEP_TITLE = re.compile(
    r"(strateg|consult|business|operations|\bops\b|product|program manag|analyst|finance|investment|banking|"
    r"marketing|brand|growth|partnership|sales|solutions|customer|gtm|revenue|corporate development|"
    r"chief of staff|sophomore|freshman|underclass|explore|\bstep\b|ignite|insight|externship|summit)", re.I)
DROP_TITLE = re.compile(r"(software engineer|hardware|firmware|electrical|mechanical|embedded|"
                        r"machine learning engineer|research scientist|quant)", re.I)


def fetch(url, dest):
    req = urllib.request.Request(url, headers={"User-Agent": "internship-scanner"})
    with urllib.request.urlopen(req, timeout=60) as r:
        dest.write_bytes(r.read())
    return dest


def _fmt_ts(ts):
    return datetime.fromtimestamp(ts, timezone.utc).date().isoformat() if ts else ""


def github_json(name, url, offline=False):
    path = DATA / f"{name}.json"
    if not offline:
        fetch(url, path)
    rows = []
    for x in json.load(open(path)):
        if not (x.get("active") and x.get("is_visible", True)):
            continue
        terms = " ".join(x.get("terms") or [x.get("season", "")])
        if terms and not re.search(r"(summer 2027|spring 2027|winter 2027|n/a|^$)", terms, re.I):
            continue
        title = x.get("title", "")
        cat = x.get("category", "")
        if not (KEEP_CATEGORY.search(cat) or KEEP_TITLE.search(title)) or (
                DROP_TITLE.search(title) and not KEEP_TITLE.search(title.split("-")[0])):
            continue
        rows.append(blank_row(
            company=x.get("company_name", ""), role=title, link=x.get("url", ""),
            location="; ".join(x.get("locations") or []), source=f"github:{name}",
            opens=_fmt_ts(x.get("date_posted")), notes=f"{cat}; {terms}".strip("; "),
        ))
    return rows


def zapply(offline=False):
    path = DATA / "zapply.md"
    if not offline:
        fetch(ZAPPLY, path)
    rows, section = [], ""
    for line in open(path):
        if line.startswith("## "):
            section = line[3:].strip()
        if not line.startswith("| ") or line.startswith("| Name") or line.startswith("| ---"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3:
            continue
        m = re.match(r"\[(.+?)\]\((.+?)\)", cells[0])
        name, link = (m.group(1), m.group(2)) if m else (cells[0], "")
        status, year, note = cells[1], cells[2], cells[3] if len(cells) > 3 else ""
        if re.search(r"closed|❌", status, re.I):
            continue
        company = re.split(r"\s+(?=[A-Z][a-z]+ |SWE|STEP|Explore|\()", name, maxsplit=1)[0]
        rows.append(blank_row(
            company=company, role=name, link=link, source="github:zapply-underclassmen",
            notes=f"{section}; {status}; year: {year}; {note}".strip("; "),
            class_year="confirmed 2029" if re.search(r"soph|all|first.?and.?second|freshman and", year, re.I)
            else ("unclear" if year else "none stated"),
        ))
    return rows


def run_career_ops_scan(log):
    """Zero-token ATS scan (Greenhouse, Lever, Ashby, Workday...) against the scanner's own portals file."""
    env = {
        "CAREER_OPS_PORTALS": str(ROOT / "config/portals.scanner.yml"),
        "CAREER_OPS_SCAN_HISTORY": str(DATA / "scan-history.tsv"),
        "CAREER_OPS_PIPELINE": str(DATA / "pipeline.md"),
    }
    import os
    proc = subprocess.run(["node", "scan.mjs", "--json", "--quiet"], cwd=CAREER_OPS,
                          env={**os.environ, **env}, capture_output=True, text=True, timeout=3600)
    (DATA / "scan_err.log").write_text(proc.stderr[-20000:])
    log(f"career-ops scan exit {proc.returncode}")


INTERNISH = re.compile(r"(intern\b|internship|co-?op|externship|insight (program|day|series)|summit|fellow|"
                       r"sophomore|freshman|underclass|explore|\bstep\b|ignite|discovery (day|program)|launchpad|"
                       r"summer analyst|winternship)", re.I)


def career_ops_rows():
    path = DATA / "scan-history.tsv"
    if not path.exists():
        return []
    rows = []
    for r in csv.DictReader(open(path), delimiter="\t"):
        if r.get("status") not in ("added", "new", "") or not INTERNISH.search(r.get("title", "")):
            continue
        rows.append(blank_row(
            company=r["company"], role=r["title"], link=r["url"], location=r.get("location", ""),
            source=f"ats:{r.get('portal', '')}", opens=(r.get("posted_at") or "")[:10],
            verified="y",  # read straight off the firm's own ATS
        ))
    return rows


def all_free(log, offline=False, skip_ats=False):
    out = []
    if not skip_ats and not offline:
        run_career_ops_scan(log)
    out += career_ops_rows()
    log(f"ats rows {len(out)}")
    for name, url in GITHUB_JSON.items():
        try:
            got = github_json(name, url, offline)
            log(f"{name} rows {len(got)}")
            out += got
        except Exception as e:  # one dead list must not sink the run
            log(f"{name} FAILED {e}")
    try:
        got = zapply(offline)
        log(f"zapply rows {len(got)}")
        out += got
    except Exception as e:
        log(f"zapply FAILED {e}")
    return out


WORKDAY_JOB = re.compile(r"https://([^/]+\.myworkdayjobs\.com)/(?:[a-z]{2}-[A-Z]{2}/)?([^/]+)/job/(.+?)/?$")


def workday_details(url):
    """Free public JSON for one Workday posting: end date, start date, location. None if unreadable."""
    m = WORKDAY_JOB.match(url or "")
    if not m:
        return None
    host, site, path = m.groups()
    tenant = host.split(".")[0]
    try:
        req = urllib.request.Request(f"https://{host}/wday/cxs/{tenant}/{site}/job/{path}",
                                     headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.load(r).get("jobPostingInfo", {})
    except Exception:
        return None


def enrich_workday_deadlines(store, log, limit=400):
    """Fill deadline/opens from the firm's own Workday page for live rows that have none. Firm page => verified."""
    n = 0
    for r in list(store.rows.values()):
        if n >= limit:
            break
        if r["tab"] not in ("URGENT", "URGENT (SUB 3)", "PIPELINE") or r.get("deadline") or "myworkdayjobs.com" not in r.get("link", ""):
            continue
        d = workday_details(r["link"])
        n += 1
        if not d:
            continue
        if d.get("endDate"):
            r["deadline"] = d["endDate"]
            store.dirty.add(r["key"])
        if d.get("startDate") and not r.get("opens"):
            r["opens"] = d["startDate"]
        if d.get("canApply") is False:
            r["notes"] = f"Workday says applications are closed. {r.get('notes', '')}".strip()
    log(f"workday deadline lookups {n}")
