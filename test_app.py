"""Self-check for the local app server (hunt/app.py). Run: uv run python test_app.py

Offline: search and the posts/scan modules are stubbed; all subjects are fictional.
"""

import asyncio
import json
import os
import sys
import tempfile
import time
import types
import warnings

os.environ["HUNT_HOME"] = tempfile.mkdtemp()  # before hunt.case reads it

warnings.filterwarnings("ignore", message="Using `httpx` with")  # Starlette prefers httpx2; httpx works
from starlette.testclient import TestClient  # noqa: E402

from hunt import app as server
from hunt.case import Case
from hunt.seed import Finding, Seed

TOKEN, PORT = "test-token", 8123
BASE = f"http://127.0.0.1:{PORT}"
JSON = {"origin": BASE, "content-type": "application/json"}
CSP = server.CSP


def client(**kw) -> TestClient:
    """Entered, so one event loop lives across requests and background jobs keep running."""
    return TestClient(server.make_app(TOKEN, PORT), base_url=BASE, follow_redirects=False, **kw).__enter__()


def events(c: TestClient, job: str, last: int = 0) -> list[tuple[int, dict]]:
    out = []
    with c.stream("GET", f"/api/jobs/{job}/events", headers={"last-event-id": str(last)}) as r:
        assert r.headers["content-type"].startswith("text/event-stream")
        for block in r.read().decode().split("\n\n"):
            fields = dict(line.split(": ", 1) for line in block.splitlines() if not line.startswith(":"))
            if "id" in fields:
                out.append((int(fields["id"]), json.loads(fields["data"])))
    return out


def wait_done(c: TestClient, job: str):
    for _ in range(100):
        if events(c, job) and events(c, job)[-1][1]["type"] in ("done", "error"):
            return
        time.sleep(0.05)
    raise AssertionError("job never finished")


# --- Security: host, sign-in, origin, content type, fetch metadata, headers --------------------
c = client()
r = c.get("/api/cases")
assert r.status_code == 403 and "not signed in" in r.json()["error"], r.text  # no cookie
assert c.get("/login?t=wrong").status_code == 403
r = c.get(f"/login?t={TOKEN}")
assert r.status_code == 303 and r.headers["location"] == "/"
cookie = r.headers["set-cookie"].lower()
assert "httponly" in cookie and "samesite=strict" in cookie, cookie
r = c.get("/api/cases")
assert r.status_code == 200 and r.json() == [], r.text
assert r.headers["x-content-type-options"] == "nosniff" and r.headers["content-security-policy"] == CSP
assert not any(h.startswith("access-control") for h in r.headers), r.headers  # no CORS, ever
assert c.get("/api/cases", headers={"host": "evil.test"}).status_code == 403  # DNS rebinding
assert c.get("/api/cases", headers={"host": f"127.0.0.1:{PORT + 1}"}).status_code == 403
assert c.get("/api/cases", headers={"sec-fetch-site": "cross-site"}).status_code == 403
assert c.get("/api/cases", headers={"sec-fetch-site": "same-site"}).status_code == 403
assert c.get("/api/cases", headers={"sec-fetch-site": "same-origin"}).status_code == 200

new = {"label": "Vance claim", "seeds": ["kestrel_vane88", "Robert Vance"], "kind": "insurance",
       "purpose": "Insurer XYZ claim 123, legitimate interest", "injury_date": "2026-03-01", "look_for": ["sport"],
       "tool": "person"}
body = json.dumps(new)
assert c.post("/api/cases", content=body, headers={"content-type": "application/json"}).status_code == 403  # no Origin
assert c.post("/api/cases", content=body, headers={**JSON, "origin": "http://evil.test"}).status_code == 403
assert c.post("/api/cases", content=body, headers={**JSON, "origin": f"http://localhost:{PORT}",
                                                   "sec-fetch-site": "cross-site"}).status_code == 403
assert c.post("/api/cases", content=body, headers={"origin": BASE, "content-type": "text/plain"}).status_code == 415
assert c.post("/api/cases", content=json.dumps({**new, "purpose": " "}), headers=JSON).status_code == 400
r = c.post("/api/cases", content=body, headers=JSON)
assert r.status_code == 201 and r.json() == {"slug": "vance-claim"}, r.text
assert c.post("/api/cases", content=body, headers=JSON).json() == {"slug": "vance-claim-2"}  # never merged
r = c.get("/api/cases/vance-claim").json()
assert r["details"]["kind"] == "insurance" and r["details"]["look_for"] == ["sport"], r
assert {"kind": "username", "value": "kestrel_vane88"} in r["seeds"] and r["steps"]["search"] == "todo", r
assert c.get("/api/cases/nope").status_code == 404
r = c.get("/")  # the frontend: index.html, never cached stale
assert r.status_code == 200 and "<html" in r.text.lower() and r.headers["cache-control"] == "no-cache", r.headers
assert c.get("/app.js").headers["cache-control"] == "no-cache"
r = c.get("/api/cases/..%2F..")  # dot segments resolve inside hunt/static at most
assert r.status_code in (307, 404) and "purpose" not in r.text, (r.status_code, r.text[:200])

# --- Evidence: name pattern, no traversal, HTML never rendered from our origin -----------------
case = Case.open("vance-claim")
sha, rel = case._store(b"<script>alert(1)</script>", "html")
r = c.get(f"/{rel.replace('evidence/', 'evidence/vance-claim/')}")
assert r.status_code == 200 and r.text == "<script>alert(1)</script>"
assert r.headers["content-type"].startswith("text/plain") and r.headers["content-security-policy"] == "sandbox", r.headers
assert r.headers["x-content-type-options"] == "nosniff"
for bad in ("..%2F..%2Fcase.db", "..%2Fcase.db", "case.db", f"{sha}.html%2F..", f"{sha[:-1]}.html", f"{sha}.toolong"):
    r = c.get(f"/evidence/vance-claim/{bad}")
    assert r.status_code in (403, 404) and "SQLite" not in r.text, (bad, r.status_code)
assert c.get(f"/evidence/..%2F{case.name}/{sha}.html").status_code == 404

# --- Jobs: SSE replay from Last-Event-ID, throttled progress, one job per case, cancel ---------
async def fake_search(case, seeds, emit, capture=True, pause=None):
    emit({"type": "stage", "stage": "asking"})
    for i in range(10):  # a burst of progress: only the first and the latest survive the throttle
        emit({"type": "scan", "checked": i + 1, "total": 10, "photos": 0, "videos": 0, "found": 0, "eta_s": None})
    emit({"type": "log", "message": "half way"})
    await asyncio.sleep(0.3)
    emit({"type": "stage", "stage": "done"})

server.search.run = fake_search
job = c.post("/api/cases/vance-claim/search", content="{}", headers=JSON).json()["job"]
assert c.post("/api/cases/vance-claim/search", content="{}", headers=JSON).status_code == 409
assert c.get("/api/cases/vance-claim").json()["active_job"] == {"id": job, "kind": "search"}
wait_done(c, job)
everything = events(c, job)
assert [i for i, _ in everything] == list(range(1, len(everything) + 1)), everything  # ids in order
scans = [e for _, e in everything if e["type"] == "scan"]
assert [s["checked"] for s in scans] == [1, 10], scans
assert everything[-1][1] == {"type": "done", "ok": True}
replay = events(c, job, last=2)
assert replay == everything[2:], replay
assert c.post(f"/api/jobs/{job}/pause", content="{}", headers=JSON).json() == {"state": "done"}
assert c.post(f"/api/jobs/{job}/explode", content="{}", headers=JSON).status_code == 404


async def slow_search(case, seeds, emit, capture=True, pause=None):
    await asyncio.sleep(30)

server.search.run = slow_search
job = c.post("/api/cases/vance-claim/search", content="{}", headers=JSON).json()["job"]
assert c.post(f"/api/jobs/{job}/pause", content="{}", headers=JSON).json() == {"state": "paused"}
assert c.post(f"/api/jobs/{job}/resume", content="{}", headers=JSON).json() == {"state": "running"}
assert c.post(f"/api/jobs/{job}/cancel", content="{}", headers=JSON).json() == {"state": "cancelled"}
wait_done(c, job)
assert events(c, job)[-1][1] == {"type": "error", "message": "cancelled"}

# --- Is it him? ---------------------------------------------------------------------------------
handle = Seed("username", "kestrel_vane88")
case.add_run("maigret", handle, "found", 3, 600, "")
case.add_finding(Finding("maigret", handle, "SiteA", "https://a.test/kestrel_vane88",
                         {"fullname": "Bob Vance"}, body="<html>A</html>"))
case.add_finding(Finding("maigret", handle, "SiteB", "https://b.test/kestrel_vane88", {"fullname": "Bob Vance"}))
case.add_finding(Finding("maigret", Seed("username", "rvance"), "SiteC", "https://c.test/rvance",
                         {"fullname": "Dana Holt"}))  # someone else
p = c.get("/api/cases/vance-claim/person").json()
assert {a["site"] for a in p["accounts"]} == {"SiteA", "SiteB"} and p["decision"] is None, p
assert p["summary"][0]["tag"] in ("name", "username") and p["weakest_verdict"], p
assert not any(r[:1] in "+-" for a in p["accounts"] for r in a["reasons"]), p  # no weights shown
assert c.post("/api/cases/vance-claim/decisions", content=json.dumps({"decision": "maybe"}), headers=JSON).status_code == 400
c.post("/api/cases/vance-claim/decisions", content=json.dumps({"url": "https://b.test/kestrel_vane88",
                                                               "decision": "not him"}), headers=JSON)
r = c.post("/api/cases/vance-claim/decisions", content=json.dumps({"decision": "him", "note": "photos match"}),
           headers=JSON).json()
assert r["accounts"] == ["https://a.test/kestrel_vane88"], r  # the person no longer includes SiteB
p = c.get("/api/cases/vance-claim/person").json()
assert p["decision"] == "him" and [a["decision"] for a in p["accounts"]] == ["him"], p

# --- Posts, media and scan, against stand-ins for hunt.posts / hunt.scan -------------------------
sys.modules["hunt.scan"] = None  # as if this build had no scanner; stand-ins replace it below
assert c.post("/api/cases/vance-claim/scan", content="{}", headers=JSON).status_code == 501
store = {"posts": [], "hits": []}
posts = types.ModuleType("hunt.posts")
scan = types.ModuleType("hunt.scan")


async def collect(case, accounts, since, emit):
    store["posts"].append({"id": 1, "source": "bluesky", "account_url": accounts[0]["url"], "url": "https://bsky.test/p/1",
                           "posted_at": "2026-04-10T10:00:00+00:00", "text": "5k run", "origin": "fetched", "media": []})
    return 1


def add_files(case, paths, platform, posted_at):
    for p in paths:
        assert p.exists() and p.read_bytes() == b"\xff\xd8\xffjpegdata"
        store["posts"].append({"id": len(store["posts"]) + 1, "source": platform, "origin": "added",
                               "posted_at": posted_at, "media": []})
    return list(range(len(paths)))


async def run(case, look_for, limits, injury_date, emit, pause, check_everything=False):
    assert look_for == ["sport"] and injury_date == "2026-03-01"
    store["hits"].append({"id": 7, "post_id": 1, "category": "sport", "what": "running a race", "verdict": "likely",
                          "status": "new", "posted_at": "2026-04-10T10:00:00+00:00", "timing": "after", "days_after": 40})
    emit({"type": "hit", **store["hits"][0]})


def set_status(case, hit_id, status):
    hit = next(h for h in store["hits"] if h["id"] == hit_id)
    hit["status"] = status
    return hit


posts.collect, posts.add_files, posts.list_posts = collect, add_files, lambda case: store["posts"]
scan.CATEGORIES, scan.run, scan.set_status = {"sport": {"label": "sport and gym"}}, run, set_status
scan.hits = lambda case: store["hits"]
sys.modules["hunt.posts"], sys.modules["hunt.scan"] = posts, scan

job = c.post("/api/cases/vance-claim/scan", content="{}", headers=JSON).json()["job"]
wait_done(c, job)
stages = [e["stage"] for _, e in events(c, job) if e["type"] == "stage"]
assert stages == ["collecting", "scanning", "done"], events(c, job)
files = [("files[]", ("a.jpg", b"\xff\xd8\xffjpegdata", "image/jpeg")), ("files[]", ("b.jpg", b"\xff\xd8\xffjpegdata", "image/jpeg"))]
r = c.post("/api/cases/vance-claim/media", files=files, data={"platform": "instagram", "posted_at": "2026-05-01"},
           headers={"origin": BASE})
assert r.status_code == 200 and r.json() == {"added": 2}, r.text
r = c.post("/api/cases/vance-claim/media", files=[("files[]", ("x.svg", b"<svg onload=alert(1)>", "image/svg+xml"))],
           headers={"origin": BASE})
assert r.status_code == 415, r.text
assert c.post("/api/cases/vance-claim/media", files=files, headers={"origin": "http://evil.test"}).status_code == 403
assert not list(Case.open("vance-claim").dir.glob(".upload-*"))  # temporary copies cleaned up
r = c.get("/api/cases/vance-claim/posts").json()
assert r["counts"] == {"read_automatically": 1, "added_by_you": 2, "flagged": 1, "by_category": {"sport": 1}}, r["counts"]
assert r["weekly"] == [{"week": "2026-W15", "posts": 1, "flagged": 1}, {"week": "2026-W18", "posts": 2, "flagged": 0}], r
assert c.post("/api/cases/vance-claim/hits/7", content=json.dumps({"status": "great"}), headers=JSON).status_code == 400
assert c.post("/api/cases/vance-claim/hits/7", content=json.dumps({"status": "in report"}), headers=JSON).json()["status"] == "in report"

# --- Report and exports -------------------------------------------------------------------------
rep = c.get("/api/cases/vance-claim/report").json()
assert rep["checks"]["every_sentence_cited"] and rep["checks"]["tampered"] == [], rep["checks"]
assert rep["evidence"][0]["id"] == "E-7" and any("running a race" in s["text"] for s in rep["sentences"])
r = c.get("/api/cases/vance-claim/report.html")
assert r.headers["content-disposition"].startswith("attachment") and "&lt;" not in r.text.split("<h1>")[0], r.headers
r = c.get("/api/cases/vance-claim/report.json?screening=1").json()
assert r["report"]["screening"] and all(m["ok"] for m in r["manifest"])
assert c.get("/api/cases/vance-claim/report.docx").status_code == 404
cases = c.get("/api/cases").json()
assert cases[0]["headline"] in ("Confirmed · report ready", "Report ready"), cases
assert c.get("/api/cases/vance-claim").json()["steps"] == {"search": "done", "identity": "done", "posts": "done",
                                                            "report": "done"}
c.__exit__(None, None, None)

print("ok")
