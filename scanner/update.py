"""Write-back for the Claude side of a run: rubric scores, verification, decision makers, drafts.

  python3 -m scanner.update score KEY --fit 4.5 [--class-year "confirmed 2029"] [--deadline 2026-10-18]
                                      [--opens ...] [--verified y] [--note "..."]
  python3 -m scanner.update person KEY --name "Jane Doe" [--email ...] [--linkedin ...] [--channel email]
  python3 -m scanner.update draft KEY --subject "..." --body-file path.txt
  python3 -m scanner.update answer KEY --why-file path.txt
  python3 -m scanner.update rule-out KEY --why "..."
  python3 -m scanner.update rescore-list            # rows from the last run that need the rubric pass

Every change marks the row dirty so the next `bin/scan` pushes it to the Sheet.
"""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

from .store import Store

ROOT = Path(__file__).resolve().parent.parent
ANSWERS = ROOT / "queue/answers.json"
DRAFTS = ROOT / "queue/outreach_drafts.md"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["score", "person", "draft", "answer", "rule-out", "rescore-list"])
    ap.add_argument("key", nargs="?")
    for f in ["fit", "class-year", "deadline", "opens", "verified", "note", "name", "email", "linkedin",
              "channel", "subject", "body-file", "why-file", "why"]:
        ap.add_argument(f"--{f}")
    a = ap.parse_args(argv)
    st = Store()
    today = date.today()

    if a.cmd == "rescore-list":
        last = json.load(open(ROOT / "data/last_run.json"))
        for k in last.get("rescore", []):
            r = st.rows.get(k)
            if r and k not in st.rubric and r["tab"] in ("URGENT", "URGENT (SUB 3)", "PIPELINE"):
                print(json.dumps({"key": k, "company": r["company"], "role": r["role"], "link": r["link"],
                                  "fit": r["fit"], "class_year": r["class_year"], "deadline": r["deadline"]}))
        return

    r = st.rows.get(a.key)
    if not r:
        sys.exit(f"no row with key {a.key!r}")

    if a.cmd == "score":
        if a.fit:
            r["fit"] = float(a.fit)
            st.rubric.add(a.key)
        for field, val in [("class_year", a.class_year), ("deadline", a.deadline), ("opens", a.opens),
                           ("verified", a.verified)]:
            if val:
                r[field] = val
        if a.note:
            r["notes"] = f"{a.note} {r.get('notes', '')}".strip()
    elif a.cmd == "person":
        from .outreach import person_blocked
        blocked = person_blocked({"name": a.name, "email": a.email or "", "linkedin": a.linkedin or ""}, r["company"])
        if blocked:
            r["outreach_status"] = "DNC: do not contact"
            r["notes"] = f"DNC hold on {a.name}: {'; '.join(blocked)}. {r.get('notes', '')}".strip()
            print("BLOCKED by Do Not Contact:", "; ".join(blocked))
        else:
            r["decision_maker"] = a.name
            r["dm_email"] = a.email or a.linkedin or ""
            r["outreach_status"] = f"found via {a.channel or 'email'}"
            print("ok")
    elif a.cmd == "draft":
        from .outreach import validate_draft
        body = Path(a.body_file).read_text().strip()
        v = validate_draft(a.subject, body)
        if v:
            sys.exit("draft violates the rules: " + "; ".join(v))
        with open(DRAFTS, "a") as f:
            f.write(f"\n## {r['company']} | {r['role']}\nTo: {r['decision_maker']} {r['dm_email']}\n"
                    f"Subject: {a.subject}\n\n{body}\n")
        r["outreach_status"] = f"drafted {today}"
        print("ok")
    elif a.cmd == "answer":
        answers = json.load(open(ANSWERS)) if ANSWERS.exists() else {}
        answers.setdefault(a.key, {})["why"] = Path(a.why_file).read_text().strip()
        ANSWERS.parent.mkdir(exist_ok=True)
        json.dump(answers, open(ANSWERS, "w"), indent=1)
    elif a.cmd == "rule-out":
        r["tab"] = "RULED OUT"
        r["notes"] = f"RULED OUT: {a.why}. {r.get('notes', '')}".strip()

    st.dirty.add(a.key)
    st.save()


if __name__ == "__main__":
    main()
