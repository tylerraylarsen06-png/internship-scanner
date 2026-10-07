"""Verify candidate ATS boards against their free public APIs. No credits."""
import json, sys, urllib.request, concurrent.futures as cf

def get(url, data=None):
    req = urllib.request.Request(url, data=json.dumps(data).encode() if data else None,
                                 headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)

def probe(c):
    kind, val = c["ats"], c["board"]
    try:
        if kind == "workday":
            host, site = val.split("|")
            tenant = host.split(".")[0]
            d = get(f"https://{host}/wday/cxs/{tenant}/{site}/jobs", {"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": "intern"})
            return d.get("total", 0), [j["title"] for j in d.get("jobPostings", [])[:3]]
        if kind == "greenhouse":
            d = get(f"https://boards-api.greenhouse.io/v1/boards/{val}/jobs")["jobs"]
        elif kind == "lever":
            d = get(f"https://api.lever.co/v0/postings/{val}?mode=json")
            d = [{"title": j["text"]} for j in d]
        elif kind == "ashby":
            d = get(f"https://api.ashbyhq.com/posting-api/job-board/{val}")["jobs"]
        ints = [j["title"] for j in d if "intern" in j["title"].lower()]
        return len(d), ints[:3]
    except Exception as e:
        return -1, [str(e)[:60]]

if __name__ == "__main__":
    cands = json.load(open(sys.argv[1]))
    with cf.ThreadPoolExecutor(8) as ex:
        for c, (n, sample) in zip(cands, ex.map(probe, cands)):
            c["probe_total"], c["probe_sample"] = n, sample
            print(f'{c["name"]:24} {c["ats"]:10} {n:5}  {sample}')
    json.dump(cands, open(sys.argv[1], "w"), indent=1)
