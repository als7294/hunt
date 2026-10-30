"""Self-check for the local app server (hunt/app.py). Run: uv run python test_app.py

Offline: search and the posts/scan modules are stubbed; all subjects are fictional.
"""

import asyncio
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import types
import warnings

from PIL import Image

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
r = c.get("/")  # a page load in a tab from an earlier start: a readable page, not a JSON error
assert r.status_code == 403 and "Open Hunt again" in r.text and r.headers["content-type"].startswith("text/html"), r.text
assert "<script" not in r.text and "content-security-policy" in r.headers
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
Case.open("vance-claim").audit("search", {})  # as search.run logs on starting; cancelled before it finishes
assert c.post(f"/api/jobs/{job}/pause", content="{}", headers=JSON).json() == {"state": "paused"}
assert c.post(f"/api/jobs/{job}/resume", content="{}", headers=JSON).json() == {"state": "running"}
assert c.post(f"/api/jobs/{job}/cancel", content="{}", headers=JSON).json() == {"state": "cancelled"}
wait_done(c, job)
assert events(c, job)[-1][1] == {"type": "error", "message": "cancelled"}
assert c.get("/api/cases/vance-claim").json()["steps"]["search"] == "todo"  # interrupted: search again
Case.open("vance-claim").audit("search finished", {})

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
assert c.get("/api/cases/vance-claim").json()["counts"]["accounts"] == 2  # the person, not SiteC
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
for path, keys in (("people", {"notice", "people"}), ("timeline", {"injury_date", "events"}),
                   ("leads", {"injury_date", "restrictions", "leads"})):
    r = c.get(f"/api/cases/vance-claim/{path}")
    assert r.status_code == 200 and keys <= set(r.json()), (path, r.text)

# --- Posts, media and scan, against stand-ins for hunt.posts / hunt.scan -------------------------
from hunt import app as hunt_app
assert hunt_app._window({"injury_date": "2026-03-01"}) == "2025-12-01" and hunt_app._window({"injury_date": None}) is None
v = c.get("/api/cases/vance-claim/vendor").json()  # no Apify key in tests: nothing runs, nothing is spent
assert v["key_set"] is False and v["run"] == [] and v["ok"] is False, v
sys.modules["hunt.scan"] = None  # as if this build had no scanner; stand-ins replace it below
assert c.post("/api/cases/vance-claim/scan", content="{}", headers=JSON).status_code == 501
store = {"posts": [], "hits": []}
posts = types.ModuleType("hunt.posts")
scan = types.ModuleType("hunt.scan")


async def collect(case, accounts, since, emit):  # like hunt.posts: announces its own stage
    emit({"type": "stage", "stage": "collecting"})
    store["posts"].append({"id": 1, "source": "bluesky", "account_url": accounts[0]["url"], "url": "https://bsky.test/p/1",
                           "posted_at": "2026-04-10T10:00:00+00:00", "text": "5k run", "origin": "fetched", "media": []})
    return 1


def add_files(case, paths, platform, posted_at):
    for p in paths:
        assert p.exists() and p.read_bytes() == b"\xff\xd8\xffjpegdata" and p.name in ("a.jpg", "b.jpg"), p  # names kept
        store["posts"].append({"id": len(store["posts"]) + 1, "source": platform, "origin": "added",
                               "posted_at": posted_at, "media": []})
    return list(range(len(paths)))


async def run(case, look_for, limits, injury_date, emit, pause, check_everything=False):
    assert look_for == ["sport"] and injury_date == "2026-03-01"
    emit({"type": "stage", "stage": "scanning"})
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
if shutil.which("sips"):  # macOS: a HEIC photo arrives as a JPEG
    jpg, heic = os.path.join(tempfile.mkdtemp(), "p.jpg"), os.path.join(tempfile.mkdtemp(), "p.heic")
    __import__("PIL.Image").Image.new("RGB", (64, 48), "red").save(jpg)
    subprocess.run(["sips", "-s", "format", "heic", jpg, "--out", heic], capture_output=True, check=True)
    got = []
    posts.add_files = lambda case, paths, platform, posted_at: got.extend(p.suffix for p in paths) or [1]
    r = c.post("/api/cases/vance-claim/media", files=[("files[]", ("IMG_1.HEIC", open(heic, "rb").read(), "image/heic"))],
               headers={"origin": BASE})
    assert r.json() == {"added": 1} and got == [".jpg"], (r.text, got)
    posts.add_files = add_files
assert not list(Case.open("vance-claim").dir.glob(".upload-*"))  # temporary copies cleaned up
r = c.get("/api/cases/vance-claim/posts").json()
assert r["counts"] == {"read_automatically": 1, "added_by_you": 2, "captured": 0, "flagged": 1,
                       "by_category": {"sport": 1}}, r["counts"]
assert r["weekly"] == [{"week": "2026-W15", "posts": 1, "flagged": 1}, {"week": "2026-W18", "posts": 2, "flagged": 0}], r
assert c.post("/api/cases/vance-claim/hits/7", content=json.dumps({"status": "great"}), headers=JSON).status_code == 400
assert c.post("/api/cases/vance-claim/hits/7", content=json.dumps({"status": "in report"}), headers=JSON).json()["status"] == "in report"

# --- Report settings and case details for the header ----------------------------------------------
assert c.get("/api/settings").json()["firm"] == ""
r = c.post("/api/settings", content=json.dumps({"firm": "Example Investigations", "licence": "PI-000000",
                                                 "investigator": "Jo Example", "timezone": "America/Chicago"}), headers=JSON)
assert r.status_code == 200 and r.json()["licence"] == "PI-000000", r.text
assert c.post("/api/settings", content=json.dumps({"timezone": "Nowhere/Land"}), headers=JSON).status_code == 400
assert c.post("/api/settings", content=json.dumps({"firm": "x"}), headers={**JSON, "origin": "http://evil.test"}).status_code == 403
png = __import__("io").BytesIO()
__import__("PIL.Image").Image.new("RGB", (30, 10), "navy").save(png, "PNG")
assert c.post("/api/settings/logo", files=[("file", ("x.svg", b"<svg/>", "image/svg+xml"))], headers={"origin": BASE}).status_code == 415
assert c.post("/api/settings/logo", content=b"{}", headers=JSON).status_code == 415  # uploads only
r = c.post("/api/settings/logo", files=[("file", ("logo.png", png.getvalue(), "image/png"))], headers={"origin": BASE})
assert r.status_code == 200 and r.json()["logo"] is True, r.text
assert c.get("/api/settings/logo").headers["content-type"] == "image/png"
r = c.post("/api/cases/vance-claim/details", content=json.dumps({"client": "Fictional Mutual", "assignment_date": "2026-03-20",
                                                                  "adjuster": "A. Adjuster", "file_number": "EX-1"}), headers=JSON)
assert r.status_code == 200 and r.json()["details"]["client"] == "Fictional Mutual", r.text
assert c.post("/api/cases/vance-claim/details", content=json.dumps({"assignment_date": "20/03/2026"}), headers=JSON).status_code == 400
assert c.post("/api/cases/vance-claim/details", content=json.dumps({"label": "renamed"}), headers=JSON).status_code == 400
assert c.get("/api/cases/vance-claim").json()["details"]["file_number"] == "EX-1"
h = c.get("/api/cases/vance-claim/report").json()["header"]
assert (h["firm"], h["client"], h["file_number"], h["timezone"]) == ("Example Investigations", "Fictional Mutual", "EX-1",
                                                                    "America/Chicago"), h
assert c.post("/api/settings", content=json.dumps({"logo": None}), headers=JSON).json()["logo"] is False

# --- Face comparison: gated by residence, opt-in with a legal basis, reference photos as evidence --------------
assert c.get("/api/face/gate?residence=US-IL").json()["allowed"] is False
assert c.get("/api/face/gate?residence=US-AZ").json() == {"allowed": True, "rule": "no biometric-law block for US-AZ"}
api = "/api/cases/vance-claim"
assert c.get(api).json()["face"] == {"on": False, "basis": None, "references": []}
png = io.BytesIO(); Image.new("RGB", (40, 40), "gray").save(png, "PNG")
ref = [("files[]", ("me.png", png.getvalue(), "image/png"))]
assert c.post(f"{api}/reference", files=ref, headers={"origin": BASE}).status_code == 409  # off: no reference taken
r = c.post(f"{api}/face", content=json.dumps({"basis": "claimant consent form, file 1"}), headers=JSON)
assert r.status_code == 403 and "residence is unknown" in r.json()["error"], r.text  # no residence on file: blocked
c.post(f"{api}/details", content=json.dumps({"subject_residence": "US-AZ"}), headers=JSON)
assert c.post(f"{api}/face", content=json.dumps({"basis": ""}), headers=JSON).status_code == 400  # a basis is required
assert c.post(f"{api}/face", content=json.dumps({"basis": "claimant consent form, file 1"}), headers=JSON).json()["on"]
assert c.post(f"{api}/reference", files=[("files[]", ("x.svg", b"<svg/>", "image/svg+xml"))], headers={"origin": BASE}).status_code == 415
refs = c.post(f"{api}/reference", files=ref, headers={"origin": BASE}).json()["references"]
assert len(refs) == 1 and c.get(refs[0]).status_code == 200 and c.get(f"{api}/person").json()["reference"] == refs
sha = refs[0].rsplit("/", 1)[1].split(".")[0]
assert c.request("DELETE", f"{api}/reference/{sha}", content="{}", headers=JSON).json()["references"] == []
assert c.request("DELETE", f"{api}/face", content="{}", headers=JSON).json()["on"] is False

# --- Leads: a caption's or record's lead is kept or set aside here, audited --------------------------------
assert c.post("/api/cases/vance-claim/leads/abc123", content=json.dumps({"status": "kept"}), headers=JSON).json() == {"id": "abc123", "status": "kept"}
assert c.post("/api/cases/vance-claim/leads/abc123", content=json.dumps({"status": "maybe"}), headers=JSON).status_code == 400
assert c.post("/api/cases/vance-claim/leads/abc123", content=json.dumps({"status": None}), headers=JSON).json()["status"] is None
assert "restrictions" in c.get("/api/cases/vance-claim/leads").json()

# --- People around the subject: "Not relevant" hides one, audited, and can be undone ------------------------
r = c.post("/api/cases/vance-claim/people/abc123/hide", content="{}", headers=JSON)
assert r.status_code == 200 and r.json()["hidden"] == ["abc123"], r.text
assert c.post("/api/cases/vance-claim/people/abc123/hide", content=json.dumps({"hidden": False}), headers=JSON).json()["hidden"] == []
assert "notice" in c.get("/api/cases/vance-claim/people").json()

# --- Free keys: saved into the environment, listed without their values, cleared -----------------
os.environ.pop("HUNT_GRAVATAR_KEY", None)
r = c.post("/api/keys", content=json.dumps({"HUNT_GRAVATAR_KEY": "gk-example"}), headers=JSON)
assert r.status_code == 200 and "gk-example" not in r.text, r.text
assert {k["key"]: k for k in r.json()["keys"]}["HUNT_GRAVATAR_KEY"]["where"] == "saved" and os.environ["HUNT_GRAVATAR_KEY"] == "gk-example"
assert "gk-example" not in c.get("/api/keys").text
assert c.post("/api/keys", content=json.dumps({"HUNT_NOPE": "x"}), headers=JSON).status_code == 400
assert c.post("/api/keys", content=json.dumps({"HUNT_GRAVATAR_KEY": "x"}), headers={**JSON, "origin": "http://evil.test"}).status_code == 403
c.post("/api/keys", content=json.dumps({"HUNT_GRAVATAR_KEY": ""}), headers=JSON)
assert "HUNT_GRAVATAR_KEY" not in os.environ
# Preview reads only a confirmed account, or a post on one; someone the posts name is never a seed (A1, A3)
r = c.post("/api/cases/vance-claim/preview", content=json.dumps({"url": "https://www.instagram.com/example"}), headers=JSON)
assert r.status_code == 400 and "confirmed" in r.json()["error"], r.text
Case.open("vance-claim").decide("https://www.instagram.com/example", "him")
r = c.post("/api/cases/vance-claim/preview", content=json.dumps({"url": "https://www.instagram.com/example"}), headers=JSON)
assert r.status_code == 200 and r.json()["status"] == "failed" and "Hunt Browser" in r.json()["note"], r.text  # a login-walled site: the note says so
assert c.post("/api/cases/vance-claim/preview", content=json.dumps({"url": "https://www.instagram.com/example2"}), headers=JSON).status_code == 400
Case.open("vance-claim").decide("https://www.instagram.com/example", "unsure")
store["posts"].append({"id": 99, "source": "bluesky", "account_url": store["posts"][0]["account_url"], "url": "https://bsky.test/p/99",
                       "posted_at": "2026-04-12T10:00:00+00:00", "text": "Fishing with my brother Dan Vell", "origin": "fetched", "media": []})
for seed in ("Dan Vell", "dan_vell", "dan.vell@example.com"):
    r = c.post("/api/cases/vance-claim/seeds", content=json.dumps({"seeds": [seed]}), headers=JSON)
    assert r.status_code == 409 and "own case" in r.json()["error"], (seed, r.text)
assert "Dan Vell" not in str(c.get("/api/cases/vance-claim").json()["seeds"])
store["posts"].pop()

# --- Report and exports -------------------------------------------------------------------------
rep = c.get("/api/cases/vance-claim/report").json()
assert rep["checks"]["every_sentence_cited"] and rep["checks"]["tampered"] == [], rep["checks"]
assert rep["evidence"][0]["id"] == "E-7" and any("running a race" in s["text"] for s in rep["sentences"])
r = c.get("/api/cases/vance-claim/report.html?view=1")  # "Web page": inline, sandboxed
assert r.headers["content-disposition"].startswith("inline") and "sandbox" in r.headers["content-security-policy"], r.headers
assert "script-src" not in r.headers["content-security-policy"] and "default-src 'none'" in r.headers["content-security-policy"]
r = c.get("/api/cases/vance-claim/report.html")
assert r.headers["content-disposition"].startswith("attachment") and "&lt;" not in r.text.split("<h1>")[0], r.headers
r = c.get("/api/cases/vance-claim/report.json?screening=1").json()
assert r["report"]["screening"] and all(m["ok"] for m in r["manifest"])
assert c.get("/api/cases/vance-claim/report.docx").status_code == 404
# The residence: a known ISO 3166 code or a US state, normalised; the wizard offers the same list (F2, AP2)
url = "/api/cases/vance-claim/details"
for bad in ("XX", "US-ZZ", "EU", "DE-BY", "U"):
    assert c.post(url, content=json.dumps({"subject_residence": bad}), headers=JSON).status_code == 400, bad
assert c.post(url, content=json.dumps({"subject_residence": " uk "}), headers=JSON).status_code == 200
assert Case.open("vance-claim").meta("subject_residence") == "GB"
c.post(url, content=json.dumps({"subject_residence": ""}), headers=JSON)
assert c.get("/api/face/gate?residence=XX").json()["allowed"] is False
js = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "hunt", "static", "app.js")).read()
from hunt.case import COUNTRIES  # noqa: E402
assert set(js.split("const ISO_COUNTRIES = '")[1].split("'")[0].split()) == COUNTRIES
# Counsel's approval of a restricted-audience item: named, audited, for a hit that exists
url = "/api/cases/vance-claim/hits/7/counsel"
assert c.post(url, content=json.dumps({"by": " "}), headers=JSON).status_code == 400
assert c.post("/api/cases/vance-claim/hits/999/counsel", content=json.dumps({"by": "A. Counsel"}), headers=JSON).status_code == 404
assert c.post(url, content=json.dumps({"by": "A. Counsel", "note": "Friends-only post, approved"}), headers=JSON).json() == \
    {"hit": 7, "counsel": "A. Counsel"}
assert Case.open("vance-claim").rows("select action from audit order by rowid desc limit 1")[0]["action"] == "counsel approved"
# A background check: no export until she confirms an account, and no map of the people around the subject (K1, A8)
bg = c.post("/api/cases", content=json.dumps({**new, "label": "Quill check", "kind": "background", "seeds": ["rquill_example"],
                                              "purpose": "Employer XYZ: pre-employment check, consent on file"}), headers=JSON).json()["slug"]
r = c.get(f"/api/cases/{bg}/report.html")
assert r.status_code == 409 and "confirm" in r.json()["error"], r.text
assert c.get(f"/api/cases/{bg}/people").json() == {"notice": server.NOT_IN_SCREENING, "people": []}
assert c.get(f"/api/cases/{bg}/report").json()["screening"] is True
Case.open(bg).decide("https://github.com/rquill_example", "him")
assert c.get(f"/api/cases/{bg}/report.json").status_code == 200
cases = c.get("/api/cases").json()
assert next(x for x in cases if x["slug"] == "vance-claim")["headline"] in ("Confirmed · report ready", "Report ready"), cases
assert c.get("/api/cases/vance-claim").json()["steps"] == {"search": "done", "identity": "done", "posts": "done",
                                                            "report": "done"}
# --- Facebook: saved pages (with their _files folder), screenshots, the investigator's links -----------
del sys.modules["hunt.posts"]  # the real posts store from here on
FB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "facebook")
fb_case = {**new, "label": "Vell claim", "seeds": ["Dorian Vell", "@dorian.vell", "location:Port Alder"]}
slug = c.post("/api/cases", content=json.dumps(fb_case), headers=JSON).json()["slug"]
blank = os.path.join(tempfile.mkdtemp(), "IMG_2041.jpg")
__import__("PIL.Image").Image.new("RGB", (64, 48), "gray").save(blank)
saved = [("files[]", ("Saved/Dorian Vell _ Facebook.html", open(os.path.join(FB, "Dorian Vell _ Facebook.html"), "rb").read(),
                      "text/html"))]
for name in os.listdir(os.path.join(FB, "Dorian Vell _ Facebook_files")):
    saved.append(("files[]", (f"Saved/Dorian Vell _ Facebook_files/{name}",
                              open(os.path.join(FB, "Dorian Vell _ Facebook_files", name), "rb").read(), "image/jpeg")))
saved += [("files[]", ("Saved/Dorian Vell _ Facebook_files/icon.svg", b"<svg onload=alert(1)>", "image/svg+xml")),
          ("files[]", ("Saved/Dorian Vell _ Facebook_files/l9oFVWfjS2E.css", b"body{}", "text/css")),
          ("files[]", ("mobile_fr.mhtml", open(os.path.join(FB, "mobile_fr.mhtml"), "rb").read(), "multipart/related")),
          ("files[]", ("IMG_2041.jpg", open(blank, "rb").read(), "image/jpeg"))]
url = f"/api/cases/{slug}/facebook"
r = c.post(url, files=saved, data={"saved_at": "2026-10-28T15:00:00"}, headers={"origin": BASE})
assert r.status_code == 200, r.text
assert r.json() == {"added": 9, "posts": 9, "pages": 2, "screenshots": 1, "skipped": [
    "Saved/Dorian Vell _ Facebook_files/icon.svg", "Saved/Dorian Vell _ Facebook_files/l9oFVWfjS2E.css"]}, r.json()
assert c.post(url, files=saved, headers={"origin": BASE}).json()["added"] == 0  # the same pages again: nothing new
listed = c.get(f"/api/cases/{slug}/posts").json()
leg = next(p for p in listed["posts"] if p["url"] == "https://www.facebook.com/dorian.vell/posts/pfbid02XaLegDay7701")
assert leg["source"] == "Facebook" and leg["origin"] == "added" and leg["posted_at"] == "2026-10-25T13:02:00+00:00"
assert leg["extra"]["place"] == "Iron Harbor Gym" and leg["extra"]["posted_at_text"] == "3d" and len(leg["media"]) == 1
assert c.get(f"/evidence/{slug}/{os.path.basename(leg['media'][0]['file'])}").headers["content-type"] == "image/jpeg"
page = c.get(f"/evidence/{slug}/{os.path.basename(leg['extra']['evidence'])}")  # the saved page, kept as it came
assert page.headers["content-type"].startswith("text/plain") and page.headers["content-security-policy"] == "sandbox"
assert "Leg day done" in page.text
squat = next(p for p in listed["posts"] if p["text"].startswith("Séance de muscu"))
mhtml = c.get(f"/evidence/{slug}/{os.path.basename(squat['extra']['evidence'])}")
assert squat["extra"]["evidence"].endswith(".mhtml") and mhtml.headers["content-type"].startswith("text/plain")
assert sum(p["source"] == "Facebook" and not p["extra"] for p in listed["posts"]) == 1  # the plain photo, as a file
for bad in ("../evil.html", "/tmp/evil.html", "Saved/../../evil.html", "C:/evil.html"):
    r = c.post(url, files=[("files[]", (bad, b"<html></html>", "text/html"))], headers={"origin": BASE})
    assert r.status_code == 400, (bad, r.status_code)
assert c.post(url, files=[("files[]", ("notes.txt", b"hello", "text/plain"))], headers={"origin": BASE}).status_code == 400
assert c.post(url, files=saved, headers={"origin": "http://evil.test"}).status_code == 403
assert c.post(url, files=saved, data={"saved_at": "last week"}, headers={"origin": BASE}).status_code == 400
assert not list(Case.open(slug).dir.glob(".upload-*"))
links = c.get(f"/api/cases/{slug}/facebook/links").json()["links"]
assert {"label": "Facebook people: Dorian Vell", "url": "https://www.facebook.com/search/people/?q=Dorian+Vell"} in links
assert any(link["url"] == "https://www.facebook.com/dorian.vell" for link in links)
assert any('"Dorian Vell" "Port Alder"' in link["label"] for link in links)
assert c.get("/api/cases/nope/facebook/links").status_code == 404
# Court portals and race-results sites to open by hand; the powerlifting load only at the size she was shown
async def opl_size(url):
    return 170 << 20
async def opl_update(*a, **k):
    loaded.append(a)
    return {"rows": "1"}
loaded, server.setup._content_length, server.sources.activity.update = [], opl_size, opl_update
links = c.get(f"/api/cases/{slug}/records/links").json()
assert any(x["label"].startswith("PACER") for x in links["courts"]), links["courts"]
assert any("athlinks.com" in x["url"] and "Dorian+Vell" in x["url"] for x in links["activity"]), links["activity"]
assert links["powerlifting"] == {"loaded": None, "size": 170 << 20}, links["powerlifting"]
assert c.post("/api/powerlifting", json={"size": 1}, headers={"origin": BASE}).status_code == 400
wait_done(c, c.post("/api/powerlifting", json={"size": 170 << 20}, headers={"origin": BASE}).json()["job"])
assert loaded == [()], loaded

c.__exit__(None, None, None)

print("ok")
