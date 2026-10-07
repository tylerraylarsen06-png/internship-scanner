"""Tier, class-year signal, rule-outs and the fit pre-score.

The pre-score approximates the career-ops global score (CV match, North Star,
comp, culture, red flags; modes/_shared.md) with rules drawn from
modes/_profile.md. It is deliberately cheap so every row gets one. The scheduled
Claude run re-scores rows at 3.5+ against the full rubric before anything is
staged, and writes the rubric score over this one.
"""
import re
from datetime import date, datetime
from pathlib import Path

import yaml

from . import verified
from .model import company_key, norm

CONFIG = Path(__file__).resolve().parent.parent / "config"
_cfg = CONFIG / "companies.yml"
_companies = yaml.safe_load(open(_cfg if _cfg.exists() else CONFIG / "companies.example.yml"))["companies"]
TIER_A = {company_key(c["name"]) for c in _companies if c["tier"] == "A"}
TIER_B = {company_key(c["name"]) for c in _companies if c["tier"] == "B"}
CONSULTING = {company_key(c["name"]) for c in _companies if c["group"] == "scope:consulting"}
MEDIA = {company_key(c["name"]) for c in _companies if c["group"] == "scope:la-media"}
MEDIA_NAME = re.compile(r"(studio|pictures|entertainment|media|network|broadcast|records|music|films?\b|"
                        r"television|\btv\b|streaming|sports|games)", re.I)
# At a studio or network these are deal roles (rights, talent contracts, distribution terms), not law practice.
MEDIA_DEAL = re.compile(r"(business (and|&) legal affairs|business affairs|\bdeals?\b|transactions?|"
                        r"\brights\b|licensing|clearances|distribution)", re.I)
MEDIA_DEAL_FIT = 3.5  # visible in PIPELINE; lifted by hand but not forced into URGENT

QUANT_FIRMS = {"jane street", "two sigma", "citadel", "citadel securities", "hudson river trading", "hrt",
               "virtu", "virtu financial", "jump trading", "susquehanna", "sig", "optiver", "imc", "drw",
               "akuna capital", "five rings", "tower research"}  # non-quant roles at quant firms stay
NEVER = {"palantir", "palantir technologies"}

NAMED_PROGRAM = re.compile(
    r"\b(explore|step|ignite|star|accelerate|launchpad|futureforce|first play|thrive|zeal|insight|"
    r"early insight|emerging leaders|early id|discovery (day|program\w*)|summit|sophomore|freshman|underclass|"
    r"externship|winternship|teip|standout|new technologists|meta university|career\.?edyou)\b", re.I)

CONFIRMED_2029 = re.compile(
    r"(sophomore|second[- ]year|2nd[- ]year|first[- ]and second[- ]year|freshm[ae]n|first[- ]year|"
    r"underclass|class of 2029|graduat\w* (in |by )?(spring |may |december |dec )?2029|"
    r"expected graduation[^.]{0,30}2029|rising sophomore|rising junior)", re.I)
ONLY_2028 = re.compile(
    r"(junior[- ]year|rising senior|penultimate|graduat\w* (in |between )?[^.]{0,25}2028|"
    r"class of 2028|final[- ]year|one summer remaining|pre-final)", re.I)
YEAR_TALK = re.compile(r"(graduat|class of|year of study|enrolled as a)", re.I)

# Restricted programs the candidate is not eligible for (modes/_profile.md). Encouraging language is not a restriction.
RESTRICTED = re.compile(
    r"(women[- ]only|for women\b|women in (trading|tech|finance|business)|female|"
    r"\bfor black\b|black (students|leaders|undergrad)|hispanic|latin[xoa]|indigenous|native american|"
    r"first[- ]gen(eration)? (students|only|college)|\bMLT\b|\bSEO\b|management leadership for tomorrow|"
    r"lgbtq\+? (students|only)|veterans only|hbcu)", re.I)
GRAD_LEVEL = re.compile(r"\b(phd|ph\.d|doctoral|master'?s|mba|postdoc|graduate student)\b", re.I)
OFF_TERM = re.compile(r"(\b(fall 2026|summer 2026|winter 2026|spring 2026|winter 2027|spring 2027|fall 2027|"
                      r"jan(uary)? 2027|co-?op)\b|off[- ]cycle|\(\w+ 20\d\d - \w+ 20\d\d\))", re.I)
LATER_SUMMER = re.compile(r"summer 202[89]", re.I)
LA_AREA = re.compile(r"(los angeles|\bLA\b|santa monica|culver city|burbank|glendale|pasadena|el segundo|"
                     r"hawthorne|playa vista|hollywood|venice|marina del rey|beverly hills|century city|"
                     r"west hollywood|universal city|studio city|sherman oaks|torrance|long beach|irvine)", re.I)
REMOTE = re.compile(r"\bremote\b", re.I)
NOT_FIT = re.compile(r"(\btax\b|audit|assurance|\bjd\b|\bcpa\b|accounting|legal|paralegal|nurs|clinical|"
                     r"pharmac|medical affairs|scientist|lab |laborator|warehouse|retail store|store associate|"
                     r"driver|technician|mechanic|teacher|tutor)", re.I)

US_STATES = re.compile(  # codes are case-sensitive so "de", "la", "in" in addresses do not match
    r"\b(AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|"
    r"ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|DC)\b|(?i:united states|\busa?\b|remote|california|"
    r"new york|texas|illinois|washington|massachusetts|georgia|florida|pennsylvania|colorado|virginia|"
    r"north carolina|michigan|arizona|minnesota|ohio|oregon|new jersey)")
TIER2 = re.compile(r"(canada|toronto|vancouver|montreal|london|united kingdom|\buk\b|ireland|dublin|paris|france|"
                   r"germany|berlin|munich|amsterdam|netherlands|zurich|switzerland|madrid|spain|milan|italy|"
                   r"stockholm|sweden|copenhagen|oslo|norway|warsaw|europe|emea)", re.I)

ROLE_FIT = [  # (pattern, base score) first match wins
    (re.compile(r"(consult|strategy|strategic|advisory|business analyst|corporate development|bizops|"
                r"business operations|chief of staff)", re.I), 4.5),
    (re.compile(r"(product manag|associate product|\bapm\b|program manag|product ops|\bpm\b intern|"
                r"solutions|forward deployed|customer success|go[- ]to[- ]market|\bgtm\b|revenue operations|"
                r"growth|partnerships|business development)", re.I), 4.2),
    (re.compile(r"(investment|private equity|venture|banking|analyst|finance|fp&a|m&a|research analyst)", re.I), 3.6),
    (re.compile(r"(design|vfx|animation|illustrat|editor|editorial|news|publicity|social media|\bsocial\b|"
                r"production|post[- ]production|writer|writing|journalis|camera|photo|video|art\b|artist|"
                r"casting|music|sound|graphic|content|original series|live action|programming|talent relations)", re.I), 2.4),
    (re.compile(r"(marketing|brand|merchandis|operations|insights|creative strategy|"
                r"communications|sales|content strategy|advertising)", re.I), 3.4),
    (re.compile(r"(data analy|analytics|business intelligence)", re.I), 3.3),
    (re.compile(r"(machine learning|software|engineer|developer|\bswe\b|data scien|research scien|hardware|"
                r"designer|game design)", re.I), 2.3),
]


PLACEHOLDER = re.compile(r"^(tbd|tba|confidential|stealth|various|company name|undisclosed|unknown|n a|na|"
                         r"hiring company|private company|anonymous|employer)\b")
# case-sensitive on purpose: with re.I the Turkish dotless i matches every English i
FOREIGN_CHARS = re.compile("[åøæßñçãõąęłńśźżčřšžőűğşțșÅØÆÑÇÃÕĄĘŁŃŚŹŻČŘŠŽŐŰĞŞȚȘ¿¡]")
FOREIGN_WORDS = re.compile(
    r"\b(og|på|med|til|er|du|bli|af|och|för|und|für|mit|der|die|das|ein|eine|als|stagiaire|alternance|"
    r"stage|pour|des|une|avec|para|con|del|los|las|una|practicante|becario|prácticas|tirocinio|per|nel|"
    r"stagiair|voor|een|staż|praktyka|estágio|estagiário|werkstudent|praktikum|praktikant)\b", re.I)
GENDER_TAG = re.compile(r"\((m|w|f|h|d|x)\s*/\s*(m|w|f|h|d|x)(\s*/\s*(m|w|f|h|d|x))?\)", re.I)


def not_english(text):
    """Cheap language check on a title: foreign diacritics, foreign function words, or (m/w/d)-style tags."""
    if FOREIGN_CHARS.search(text) or GENDER_TAG.search(text):
        return True
    return len(FOREIGN_WORDS.findall(text)) >= 2


def link_location(url):
    """Workday and similar boards put the location in the path; use it when the location field is empty."""
    m = re.search(r"/job/([^/]+)/", url or "")
    return m.group(1).replace("-", " ") if m else ""


TIER3 = re.compile(
    r"\b(?<!new )(mexico|brazil|brasil|são paulo|sao paulo|argentina|buenos aires|chile|santiago|colombia|bogot|peru|lima|"
    r"costa rica|puerto rico|india|bengaluru|bangalore|hyderabad|mumbai|pune|chennai|gurgaon|gurugram|noida|"
    r"delhi|china|beijing|shanghai|shenzhen|hangzhou|guangzhou|hong kong|taiwan|taipei|hsinchu|japan|tokyo|"
    r"osaka|korea|seoul|singapore|malaysia|kuala lumpur|indonesia|jakarta|philippines|manila|vietnam|"
    r"ho chi minh|hanoi|thailand|bangkok|australia|sydney|melbourne|brisbane|new zealand|auckland|israel|"
    r"tel aviv|dubai|abu dhabi|uae|saudi|riyadh|qatar|doha|egypt|cairo|south africa|johannesburg|cape town|"
    r"nigeria|lagos|kenya|nairobi|pakistan|karachi|lahore|turkey|istanbul|apac|latam)\b", re.I)


def location_tier(loc):
    """US is the default: a place is Tier 3 only when it names somewhere outside the US, Canada and Europe."""
    if not loc:
        return 1
    if US_STATES.search(loc):
        return 1
    if TIER2.search(loc):
        return 2
    return 3 if TIER3.search(loc) else 1


def class_year(text):
    if CONFIRMED_2029.search(text):
        return "confirmed 2029"
    if ONLY_2028.search(text):
        return "2028 only"
    if YEAR_TALK.search(text):
        return "unclear"
    return "none stated"


def rule_out(company, role, text, loc, cy, link="", raw_link=""):
    ck = company_key(company)
    if PLACEHOLDER.match(ck) or PLACEHOLDER.match(norm(company)) or not ck:
        return f"Placeholder company name '{company}', not a real employer"
    if not_english(role):
        return "Posting not in English"
    if ck in NEVER:
        return "Palantir, ruled out"
    if ck in QUANT_FIRMS or re.search(r"\b(quant\w*|trader|trading)\b", role, re.I):
        return "Quant, deprioritized in profile"
    if RESTRICTED.search(f"{role} {text}"):
        return "Restricted program, not eligible"
    if GRAD_LEVEL.search(f"{role} {link}") or re.search(r"mba[- ]level|banking associate", f"{role} {link}", re.I):
        return "Graduate-level role"
    if cy == "2028 only":
        return "Junior/senior-only"
    if LATER_SUMMER.search(role):
        return "Summer 2028 or later: junior-year internship"
    if re.search(r"\bco-?op\b", role, re.I):
        return "Co-op: full-time during the semester"
    # An off-season term stays in when it is local: a commutable spring role is a path to a summer offer
    # at the same company. Do not tighten this.
    if OFF_TERM.search(role) and not (LA_AREA.search(f"{loc} {role}") or REMOTE.search(f"{loc} {role}")):
        return "Off-season term outside LA"
    if location_tier(loc or link_location(raw_link)) == 3:
        return ("Outside US, Canada and Europe. Surface by hand only if career-defining AND fully funded")
    return ""


def tier(company, role, ruled_out):
    if ruled_out:
        return "C"
    ck = company_key(company)
    if NAMED_PROGRAM.search(role):
        return "A"
    return "B"


def fit(company, role, cy, tier_, loc=""):
    ck = company_key(company)
    base = 3.5 if ck in TIER_B else 3.0  # a general internship program at a Tier B company is the target pattern
    for pat, score in ROLE_FIT:
        if pat.search(role):
            base = score
            break
    if MEDIA_DEAL.search(role) and (ck in MEDIA or MEDIA_NAME.search(company)):
        return MEDIA_DEAL_FIT  # capped: no Tier B or LA boost on top
    if NOT_FIT.search(role):
        return 2.0
    if ck in CONSULTING and base < 4.5:
        base = max(base, 4.0)
    base += {"confirmed 2029": 0.5, "unclear": 0.0, "none stated": 0.0, "2028 only": -1.5}[cy]
    if tier_ == "A":
        base += 0.2
    if ck in TIER_B:
        base += 0.2  # the Fox/Skechers pattern: a human reads it
        if LA_AREA.search(f"{loc} {role}"):
            base += 0.5
    if re.search(r"\b(game|gaming)\b", role, re.I):
        base -= 0.5
    return max(1.0, min(5.0, round(base * 2) / 2))


def parse_date(s):
    if not s:
        return None
    if isinstance(s, (date, datetime)):
        return s if isinstance(s, date) else s.date()
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%m/%d/%Y", "%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(str(s).strip()[:19], fmt).date()
        except ValueError:
            pass
    return None


URGENT_DEADLINE_FLOOR = 3.0  # due inside 30 days goes to URGENT only at fit 3.0+


def due_within(row, today, days):
    d = parse_date(row.get("deadline"))
    return bool(d and today <= d and (d - today).days <= days)


def tab_for(row, today, rubric_scored=False):
    """URGENT, URGENT (SUB 3) or PIPELINE for a live row."""
    try:
        f = float(row.get("fit") or 0)
    except ValueError:
        f = 0.0
    if is_urgent(row, today, rubric_scored):
        return "URGENT"
    if due_within(row, today, 30) and f < URGENT_DEADLINE_FLOOR:
        return "URGENT (SUB 3)"  # due soon but a weak fit: kept in sight, out of the work queue
    return "PIPELINE"


def is_urgent(row, today, rubric_scored=False):
    """Due inside 30 days at fit 3.0+, or fit 4+. A heuristic 4+ also needs a second signal
    (named program, confirmed class year, or LA) so the work queue stays a queue."""
    try:
        f = float(row.get("fit") or 0)
    except ValueError:
        return False
    if due_within(row, today, 30) and f >= URGENT_DEADLINE_FLOOR:
        return True
    if f < 4.0:
        return False
    if rubric_scored:
        return True
    in_la = bool(LA_AREA.search(f"{row.get('location', '')} {link_location(row.get('link', ''))}"))
    if row.get("tier") == "B" and in_la and row.get("class_year") in ("none stated", "unclear"):
        return True  # the Fox/Skechers pattern: rolling, no deadline, closes when it fills
    return row.get("tier") == "A" or row.get("class_year") == "confirmed 2029" or in_la


def apply_verified(row):
    """Firm-page facts win. Returns the verified rule-out reason, or ''."""
    v = verified.lookup(row["company"], row["role"])
    if not v:
        return ""
    if v.get("verified") == "y":
        cy = v["class_year"]
        row["class_year"] = cy if cy in ("confirmed 2029", "2028 only", "unclear") else "unclear"
        row["verified"] = "y"
        for f in ("deadline", "opens"):
            if v.get(f) and parse_date(v[f]):
                row[f] = v[f]
        tag = f"[verified: {v['evidence'][:160]}]"
        if tag not in row.get("notes", ""):
            row["notes"] = f"{tag} {row.get('notes', '')}".strip()
    return v.get("rule_out", "")


def enrich(row, text=""):
    """Fill tier / class_year / fit, and return a rule-out reason ('' if none).

    Class year is only trusted when it was read on the firm's own page (verified == "y"). A label inherited
    from the old sheet, a GitHub list or a guide site is downgraded to "unclear" until verified."""
    link = re.sub(r"[-_/]+", " ", row.get("link", ""))
    blob = f"{row['role']} {row.get('notes', '')} {text} {link}"
    v_why = apply_verified(row)
    cy = row.get("class_year") or class_year(blob)
    # only a POSITIVE label needs a firm-page read; a junior-only signal still rules the row out
    if row.get("verified") != "y" and cy == "confirmed 2029":
        note = f"[class year '{cy}' from {row.get('source') or 'an unverified source'}, not verified on firm page]"
        if note not in row.get("notes", ""):
            row["notes"] = f"{note} {row.get('notes', '')}".strip()
        cy = "unclear"
    why = v_why or rule_out(row["company"], row["role"], blob, row.get("location", ""), cy, link,
                            row.get("link", ""))
    row["class_year"] = cy
    row["tier"] = tier(row["company"], row["role"], why)
    if not row.get("fit"):
        row["fit"] = fit(row["company"], row["role"], cy, row["tier"],
                         f"{row.get('location', '')} {link_location(row.get('link', ''))}")
    return why
