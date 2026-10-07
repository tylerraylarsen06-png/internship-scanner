"""Talk to the Sheet's Apps Script web app. Until it is deployed, the run falls back to a local xlsx."""
import json
import os
import urllib.parse
import urllib.request
from pathlib import Path

ENV = Path(__file__).resolve().parent.parent / "config/secrets.env"


def _cfg():
    cfg = {}
    if ENV.exists():
        for line in ENV.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                cfg[k.strip()] = v.strip()
    cfg.update({k: v for k, v in os.environ.items() if k.startswith("SHEET_")})
    return cfg


def configured():
    c = _cfg()
    return bool(c.get("SHEET_WEBAPP_URL") and c.get("SHEET_TOKEN"))


def pull():
    c = _cfg()
    url = f"{c['SHEET_WEBAPP_URL']}?{urllib.parse.urlencode({'token': c['SHEET_TOKEN']})}"
    with urllib.request.urlopen(url, timeout=120) as r:
        d = json.load(r)
    if not d.get("ok"):
        raise RuntimeError(d.get("error"))
    return d["rows"]


def push(rows, batch=200):
    c = _cfg()
    total = {"appended": 0, "updated": 0, "moved": 0}
    for i in range(0, len(rows), batch):
        body = json.dumps({"token": c["SHEET_TOKEN"], "rows": rows[i:i + batch]}, default=str).encode()
        req = urllib.request.Request(c["SHEET_WEBAPP_URL"], data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=300) as r:
            d = json.load(r)
        if not d.get("ok"):
            raise RuntimeError(d.get("error"))
        for k in total:
            total[k] += d.get(k, 0)
    return total
