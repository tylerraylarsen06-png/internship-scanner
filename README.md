# internship-scanner

I built this to run my own internship search. It pulls postings from 46 company job boards through their ATS APIs (Greenhouse, Lever, Ashby, Workday), 4 public GitHub internship lists, and Handshake and LinkedIn read in a browser. It merges them into one list, rules out the ones I can't apply to, ranks the rest, and pushes them to a Google Sheet sorted by what to do first. When I'm ready to apply, it opens each application with Playwright and fills in what it can, but the Submit button is always left to me.

So far it has tracked over 1,700 postings.

This repo is the code only. My answers, my resume and every posting it has collected stay on my machine.

## How a run works

```
             46 job boards                   4 GitHub lists              inbox/*.json
   (Greenhouse, Lever, Ashby, Workday)  (SimplifyJobs, pittcsc,     (rows found by a browser pass:
                  │                        vanshb03, zapply)          Handshake, LinkedIn reading,
                  │                              │                    firm career pages)
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

- **Job boards.** Each board is read through its public JSON endpoint, not by scraping the page. Greenhouse, Lever and Ashby publish one, and Workday tenants expose a search API behind every careers site. `probe_boards.py` checks a candidate board against its API before it is added to `config/portals.scanner.yml`.
- **GitHub lists.** The big student-run internship repos publish a `listings.json`. Four of them are read every run. They overlap a lot, which is why deduping matters.
- **Handshake and LinkedIn.** A scheduled Claude in Chrome pass reads new postings (reading only, nothing is clicked or sent) and drops them into `data/inbox/` as JSON. Firm career pages with no API are read with Firecrawl on a fixed credit budget. Everything in the inbox goes through the same pipeline as the boards. The full instructions for that pass are in `docs/SCHEDULED_RUN.md`.

### Deduping

The same internship shows up on a company board, on two GitHub lists and on Handshake, each with a slightly different title and link. `model.py` builds a key from a normalized company name and role, and canonicalizes URLs (drops query strings and tracking parameters, collapses `/apply` variants), so the copies merge into one row that remembers every source it came from.

### Ranking and ruling things out

Most postings are not a fit, and the useful work is saying why. `classify.py` rules a row out with a reason a person can read:

- junior or senior only, or a summer 2028 internship
- a program restricted to a group I'm not part of
- a co-op that runs during the semester
- an off-season term that isn't local or remote
- a location outside the US, Canada and Europe

Everything left gets a pre-score from 1 to 5. A later review pass can read the posting and write a better score over it with `scanner/update.py`. Rows land in five Sheet tabs: URGENT (fit 4+, or due inside 30 days at 3.0+), URGENT (SUB 3), PIPELINE, APPLIED and RULED OUT.

Class year is the hardest field. A GitHub list saying "sophomores eligible" is not trusted until it was read on the firm's own page. Those labels are downgraded to "unclear", and `verified.py` holds the facts that were checked by hand. A verified fact always beats an inherited one.

### The Sheet

`apps_script/Code.gs` is a small web app bound to the Sheet, protected by a token. Some columns belong to me once a row exists (status, notes, contact). The scanner reads my edits back before every run and never overwrites those columns, so the Sheet can be edited by hand without a run undoing it.

### Applying without ever submitting

`stage.py` builds a queue of everything due soon and above a fit threshold, with the ATS detected and the answers from `config/profile.json` attached. `bin/apply` opens each one in a separate Playwright browser profile, fills the fields it can match (name, school, graduation date, work authorization and so on), uploads the resume, and puts a red "NOT SUBMITTED" banner across the top listing what still needs a person.

Workday applications are multi-page, so `workday.mjs` walks them up to the Review page. Every click goes through `guard.mjs`, which refuses anything whose text, label or automation ID says submit, send, finish, sign in, create account, accept or agree, and only allows buttons on a short allow-list (Apply, Next, Save and Continue, Upload). `tests/test_never_submit.py` fails if `fill.mjs` or `workday.mjs` ever gains a raw click, key press, form submit or `dispatchEvent`, and runs the guard against the cases that matter.

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
| `scanner/stage.py` | Builds the apply queue and attaches answers from `config/profile.json` |
| `scanner/update.py` | Write-back for scores, notes and drafts from a review pass |
| `scanner/outreach.py` | Optional. Drafts a short note to a person on the team, behind a fail-closed do-not-contact check. Needs a separate private module that is not published here |
| `apply/fill.mjs` | Opens and fills applications |
| `apply/workday.mjs` | Walks Workday's multi-page flow up to the Review page |
| `apply/guard.mjs` | The only code allowed to click, and it refuses Submit |
| `apps_script/Code.gs` | The Google Sheet side |
| `config/companies.yml` | Company list and tier |
| `config/portals.scanner.yml` | The 46 job boards and title filters |
| `config/firecrawl_pages.yml` | Firm career pages with no API |
| `docs/SCHEDULED_RUN.md` | Instructions for the scheduled browser and review pass |
| `tests/` | Classification cases and the never-submit checks |

## Setup

Requirements: Python 3 with PyYAML, Node, and a local checkout of [career-ops](https://github.com/santifer/career-ops) at `~/dev/career-ops`. The job board scan runs through its zero-token scanner, pointed at this project's own portals file, and the apply step uses its Playwright install.

```
pip install pyyaml
cp config/profile.example.json config/profile.json    # your answers and resume path
cp config/secrets.env.example config/secrets.env      # Sheet web app URL and token
```

Edit `config/profile.json` with your own answers and put your resume at the path it names. Any question the profile does not cover is left blank and flagged, never guessed.

To connect the Google Sheet:

1. Open the Sheet, then Extensions > Apps Script. Replace the editor contents with `apps_script/Code.gs` and save.
2. Run `setup` from the function menu, approve the permissions, and copy the token from the execution log.
3. Deploy > New deployment > Web app, executing as Me with access set to Anyone. The token is what protects it.
4. Put the URL and token in `config/secrets.env`.

Without the Sheet configured, a run writes `data/Internship_Master.xlsx` instead.

## Running it

```
bin/scan                     # one full run (the board scan takes 15 to 25 minutes)
bin/scan --skip-ats          # GitHub lists and inbox only
bin/apply --list             # print the queue, open nothing
bin/apply                    # open and fill what is due within 14 days, never submit
bin/apply --match fox        # one company
python3 -m unittest discover -s tests -t .   # tests
```

`data/`, `queue/`, `assets/`, `config/profile.json` and `config/secrets.env` are all in `.gitignore`.

## Roadmap

- **Onboarding interview.** Before the first scan, Claude asks what you want (roles, cities, terms, class year, companies you care about) and writes the profile and company list from your answers.
- **Outreach months ahead.** Feed urgent postings into the networking and outreach system, so it suggests people to contact at the companies you're applying to well before the deadline.
- **Live Sheet sync.** Push changes to the Google Sheet through Apps Script as they happen, instead of once per run.

Built with Chewbacca
