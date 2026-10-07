# internship-scanner

I built this to run my internship search. It pulls postings from 46 company job boards and 4 public GitHub internship lists, merges them into one list, rules out the ones I can't apply to, scores the rest, and pushes them to a Google Sheet sorted by what to do first. When I'm ready to apply, it opens each application in a browser and fills in what it can. It never presses Submit.

So far it has tracked 1,431 postings. 1,223 of those came in through the automated sources, and the rest were imported from the spreadsheet I kept by hand before this existed.

This is the code only. My answers, my company list, my resume and every posting it has collected stay on my machine.

## How a run works

```
             46 job boards                   4 GitHub lists              inbox/*.json
   (Greenhouse, Lever, Ashby, Workday)  (SimplifyJobs, pittcsc,     (rows found by hand or by
                  │                        vanshb03, zapply)          an AI pass: Handshake,
                  │                              │                    LinkedIn reading, firm pages)
                  └──────────────┬───────────────┴──────────────┬─────────────┘
                                 ▼                              ▼
                    sources.py: one row shape for every source
                                 │
                                 ▼
                    classify.py: rule-outs, class year, location tier, pre-score
                                 │
                                 ▼
                    store.py: data/master.json, deduped on company + role
                                 │
                 ┌───────────────┼────────────────────┐
                 ▼               ▼                    ▼
           sheet.py ──►    stage.py ──►         run report
        Google Sheet      queue/queue.json     (new, urgent, due in 30 days)
        (5 tabs)               │
                               ▼
                     apply/fill.mjs: open, fill, STOP
```

### Sources

- **Job boards.** Each board is hit through its public JSON endpoint, not by scraping the page. Greenhouse, Lever and Ashby publish one; Workday tenants expose a search API behind every careers site. `probe_boards.py` checks a candidate board against its public API before it is added.
- **GitHub lists.** The big student-run internship repos publish a `listings.json`. Four of them are read every run. They overlap a lot, which is why deduping matters.
- **Inbox.** Anything found another way (Handshake, a firm's own careers page, a manual search) is dropped into `data/inbox/` as JSON and goes through the same pipeline as everything else.

### Deduping

The same internship shows up on a company board, on two GitHub lists and on Handshake, each with a slightly different title and a different link. `model.py` builds a key from a normalized company name and role, and canonicalizes URLs (drops query strings and tracking parameters, collapses `/apply` variants), so the four copies merge into one row that remembers every source it came from.

### Ruling things out

Most postings are not for me, and the useful work is saying why. `classify.py` rules a row out with a reason a person can read:

- junior or senior only, or a summer 2028 internship
- a program restricted to a group I'm not part of
- a co-op that runs during the semester
- an off-season term that isn't local or remote
- a location outside the US, Canada and Europe

Class year is the hardest field. A GitHub list or an old spreadsheet saying "sophomores eligible" is not trusted until it was read on the firm's own page. Those labels are downgraded to "unclear," and a separate verification file (`verified.py`) holds the facts that were checked by hand. A verified fact always beats an inherited one.

### The Sheet

`apps_script/Code.gs` is a small web app bound to the Sheet. The scanner writes rows into five tabs: URGENT, URGENT (SUB 3), PIPELINE, APPLIED and RULED OUT. Some columns belong to me once a row exists (status, notes, contact). The scanner reads my edits back before every run and never overwrites those columns, so the Sheet can be edited by hand without a run undoing it.

### Applying without ever submitting

`stage.py` builds a queue of everything due soon and above a fit threshold, with the ATS detected and the answers attached. `bin/apply` opens each one in its own browser window, fills the fields it can match (name, school, graduation date, work authorization and so on), uploads the resume, and puts a red "NOT SUBMITTED" banner across the top with a list of what still needs a person.

Workday applications are multi-page, so `workday.mjs` clicks through them. Every click goes through `guard.mjs`, which refuses anything whose text, label or automation ID says submit, send, finish, sign in, create account, accept or agree, and only allows buttons on a short allow-list (Apply, Next, Save and Continue, Upload). `tests/test_never_submit.py` fails the build if `fill.mjs` or `workday.mjs` ever gains a raw click, key press, form submit or `dispatchEvent`, and runs the guard against the cases that matter.

Signing in, checking agreement boxes and pressing Submit are always left to me.

## Files

| Path | What it does |
|---|---|
| `scanner/run.py` | One full run: sources, inbox, merge, classify, Sheet, stage, report |
| `scanner/sources.py` | Job board scan and the GitHub list readers |
| `scanner/probe_boards.py` | Checks candidate boards against their public APIs |
| `scanner/classify.py` | Rule-outs, class year, location tier, pre-score, urgency |
| `scanner/verified.py` | Hand-checked firm page facts that override everything else |
| `scanner/model.py` | Row shape, row key, URL canonicalization |
| `scanner/store.py` | `data/master.json`, merge logic, Sheet write-back |
| `scanner/sheet.py` | Talks to the Apps Script web app |
| `scanner/stage.py` | Builds the apply queue and attaches answers |
| `scanner/update.py` | Write-back for scores, notes and drafts from a review pass |
| `scanner/outreach.py` | Optional. Finds and drafts a note to a person on the team, behind a fail-closed do-not-contact check. Needs a private module that is not published here |
| `apply/fill.mjs` | Opens and fills applications |
| `apply/workday.mjs` | Walks Workday's multi-page flow up to the Review page |
| `apply/guard.mjs` | The only code allowed to click, and it refuses Submit |
| `apps_script/Code.gs` | The Google Sheet side |
| `tests/` | Classification cases and the never-submit checks |

## Running it

```
cp config/answers.example.json config/answers.local.json      # your answers and resume path
cp config/companies.example.yml config/companies.yml           # your company list
cp config/secrets.env.example config/secrets.env               # Sheet web app URL and token
pip install pyyaml
bin/scan              # one run
bin/apply --list      # see the queue
bin/apply             # open and fill, never submit
python3 -m unittest discover -s tests
```

The job board scan runs through [career-ops](https://github.com/santifer/career-ops)'s zero-token scanner, pointed at this project's own portals file, and the apply step uses its Playwright install. Without the Sheet configured, a run writes `data/Internship_Master.xlsx` instead.

Every answer file, company list and data folder above is in `.gitignore`.
