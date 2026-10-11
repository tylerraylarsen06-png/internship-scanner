"""One scanner run. Called by the scheduled task every 3 days, or by hand.

  python3 -m scanner.run                 full run (ATS scan + GitHub lists + inbox), push to Sheet
  python3 -m scanner.run --skip-ats      skip the ~15 min career-ops board scan
  python3 -m scanner.run --offline       reuse downloaded files, no network
  python3 -m scanner.run --no-push       do not write the Sheet

Rows found by the Claude side of the run (Handshake, LinkedIn reading, Firecrawl,
web search) are dropped as JSON lists into data/inbox/*.json and ingested here, then moved to
data/inbox/done/.
"""
import argparse
import json
import shutil
from datetime import date
from pathlib import Path

from . import sheet, sources, stage
from .classify import parse_date
from .model import TABS, blank_row
from .store import Store

ROOT = Path(__file__).resolve().parent.parent
INBOX = ROOT / "data/inbox"
LOG = []


def log(msg):
    LOG.append(msg)


def ingest_inbox():
    rows = []
    INBOX.mkdir(parents=True, exist_ok=True)
    (INBOX / "done").mkdir(exist_ok=True)
    for f in sorted(INBOX.glob("*.json")):
        for r in json.load(open(f)):
            rows.append(blank_row(**{k: str(v) for k, v in r.items() if v is not None}))
        shutil.move(str(f), INBOX / "done" / f.name)
    log(f"inbox rows {len(rows)}")
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--skip-ats", action="store_true")
    ap.add_argument("--no-push", action="store_true")
    ap.add_argument("--today")
    a = ap.parse_args(argv)
    today = date.fromisoformat(a.today) if a.today else date.today()

    st = Store()
    first_push = not st.rows or not any(r.get("_pushed") for r in st.rows.values())
    use_sheet = sheet.configured() and not a.no_push
    if use_sheet:
        log(f"sheet edits applied {st.pull_sheet(sheet.pull())}")

    found = sources.all_free(log, offline=a.offline, skip_ats=a.skip_ats) + ingest_inbox()
    new_keys, touched = [], set()
    for r in found:
        res = st.add(r, today)
        k = st.find(r)
        if res == "new":
            new_keys.append(k)
        if res in ("new", "merged"):
            touched.add(k)
    if not a.offline:
        sources.enrich_workday_deadlines(st, log)
    moves = st.retab(today)
    touched |= {k for k, _ in moves}
    answers_path = ROOT / "queue/answers.json"
    extra = json.load(open(answers_path)) if answers_path.exists() else {}
    items, no_link = stage.build(st, extra_answers=extra, today=today)
    touched |= {i["key"] for i in items} | st.dirty

    push_rows = list(st.rows.values()) if first_push else [st.rows[k] for k in touched]
    if use_sheet and push_rows:
        res = sheet.push([{**r} for r in push_rows])
        for r in push_rows:
            r["_pushed"] = today.isoformat()
        log(f"sheet push {res}")
        st.dirty.clear()
    st.save()
    st.export_xlsx(ROOT / "data/Internship_Master.xlsx")

    new = [st.rows[k] for k in new_keys]
    new_live = [r for r in new if r["tab"] in ("URGENT", "URGENT (SUB 3)", "PIPELINE")]
    due = [r for r in st.by_tab("URGENT") if parse_date(r.get("deadline"))
           and 0 <= (parse_date(r["deadline"]) - today).days <= 30 and r.get("status") != "applied"]
    report = {
        "date": today.isoformat(), "new_total": len(new), "new_live": len(new_live),
        "new_urgent": [f"{r['company']} | {r['role']} | fit {r['fit']} | {r.get('deadline') or 'no deadline'} | {r['link']}"
                       for r in new if r["tab"] == "URGENT"],
        "due_30d": [f"{r['company']} | {r['role']} | due {r['deadline']} | {r['link']}" for r in due],
        "rescore": [r["key"] for r in sorted(new_live, key=lambda r: -float(r["fit"] or 0))
                    if float(r["fit"] or 0) >= 3.5 and r["key"] not in st.rubric][:25],
        "queue": len(items), "urgent_no_direct_link": [f"{r['company']} | {r['role']}" for r in no_link],
        "tabs": {t: len(st.by_tab(t)) for t in TABS},
        "sheet": "pushed" if use_sheet else "not configured: wrote data/Internship_Master.xlsx",
        "log": LOG,
    }
    json.dump(report, open(ROOT / "data/last_run.json", "w"), indent=1)

    if not new_live and not due:
        print(f"{today}: nothing new, nothing due.")
        return report
    print(f"{today}: {len(new_live)} new live row(s), {len(report['new_urgent'])} new URGENT, "
          f"{len(due)} deadline(s) inside 30 days, {len(items)} staged to apply.")
    for line in report["due_30d"]:
        print("  DUE   " + line)
    for line in report["new_urgent"][:40]:
        print("  NEW   " + line)
    return report


if __name__ == "__main__":
    main()
