"""Self-check for the new frontend's flags and evidence (docs/frontend-v2.md): GET /api/cases/{slug}/flags and the parts that
draw it. Run: uv run python test_v2_flags.py. Fictional people only; the server runs in-process on a scratch HUNT_HOME.
"""

import hashlib
import os
import tempfile
import warnings

os.environ["HUNT_HOME"] = tempfile.mkdtemp()  # before hunt.case reads it
warnings.filterwarnings("ignore", message="Using `httpx` with")
from starlette.testclient import TestClient  # noqa: E402

from hunt import app as server, scan  # noqa: E402
from hunt.api2 import flags  # noqa: E402
from hunt.case import Case  # noqa: E402

# The mapping of the design's eight checks onto Hunt is explicit, and every category Hunt scans for is named by a check
assert [c["id"] for c in flags.CHECKS] == ["activity", "location", "lifestyle", "assets", "identity", "photo", "newacct", "network"]
assert {c["status"] for c in flags.CHECKS} == {"built", "partial", "not yet"} and all(c["how"] for c in flags.CHECKS)
assert {c["id"]: c["status"] for c in flags.CHECKS}["lifestyle"] == "not yet" and {c["id"]: c["status"] for c in flags.CHECKS}["activity"] == "built"
covered = {k for c in flags.CHECKS + flags.OWN for k in c["look_for"]}
assert covered == set(scan.CATEGORIES), covered ^ set(scan.CATEGORIES)
assert flags.severity("almost certain") == flags.severity("likely") == "high" and flags.severity("roughly even chance") == "med"
assert flags.severity("unlikely") == flags.severity(None) == "low"
assert flags.grade("fetched", "likely", False) == "B2" and flags.grade("captured", "roughly even chance", True) == "B4"
assert flags.grade("vendor", "unlikely", False) == "C4" and flags.grade(None, "likely", False) is None and flags.grade("added", None, False) is None
assert flags.risk([]) == {"score": 0, "label": "Low", "items": 0, "meaning": "how much there is to review, not the chance of fraud"}
assert flags.risk([{"severity": "high", "status": "new"}] * 4)["label"] == "High"
assert flags.risk([{"severity": "med", "status": "kept"}, {"severity": "high", "status": "not relevant"}]) == \
    {"score": 16, "label": "Low", "items": 1, "meaning": "how much there is to review, not the chance of fraud"}

# A case with one flagged post and one lead, through the real route
c = Case.create("Kestrel Vane", "test: flags", kind="insurance", injury_date="2026-03-05", limits="Can't lift over 5 kg or run",
                look_for=["lifting", "sport", "a new car"], subject_residence="US-AZ")
c.db.executescript(scan.SCHEMA)
photo = b"\x89PNG\r\n\x1a\n" + b"kestrel" * 40
sha = hashlib.sha256(photo).hexdigest()
(c.dir / "evidence").mkdir(exist_ok=True)
(c.dir / "evidence" / f"{sha}.png").write_bytes(photo)
acct = "https://bsky.app/profile/kvane88.bsky.social"
pid = c.db.execute("insert into posts values (null, 'Bluesky', ?, ?, '2026-03-14T07:12:00+00:00', 'Moving day, boxes everywhere', 'fetched', "
                   "'2026-03-20T09:00:00+00:00')", (acct, f"{acct}/post/1")).lastrowid
mid = c.db.execute("insert into media values (null, ?, 'image', ?, ?, null, 'https://cdn.test/1.png')", (pid, f"evidence/{sha}.png", sha)).lastrowid
hid = c.db.execute("insert into hits (post_id, media_id, category, what, verdict, p, timing, days_after, status, who, file, blur, created) values "
                   "(?, ?, 'lifting', 'a person carrying a heavy box', 'likely', 0.7, 'after', 9, 'new', 'him', ?, 0, '2026-03-20T09:05:00+00:00')",
                   (pid, mid, f"evidence/{sha}.png")).lastrowid
BASE = "http://127.0.0.1:8128"
tc = TestClient(server.make_app("t", 8128), base_url=BASE, follow_redirects=False).__enter__()
tc.get("/login?t=t")
POST = {"origin": BASE}  # the app's CSRF guard wants the page's own origin on a POST
for f in ("parts/flags.js", "parts/evidence.js"):
    assert tc.get(f"/v2/{f}").status_code == 200, f
d = tc.get(f"/api/cases/{c.name}/flags").json()
assert d["look_for"] == ["lifting", "sport", "a new car"] and d["injury_date"] == "2026-03-05" and d["background"] is False
assert [f["key"] for f in d["flags"]] == ["lifting", "sport", "a new car"] and d["flags"][2]["custom"] is True
assert d["flags"][0] == {"key": "lifting", "label": "Lifting or carrying", "custom": False, "count": 1, "worst": "high"}
assert d["flags"][1]["count"] == 0 and d["flags"][1]["worst"] is None
ev = {e["id"]: e for e in d["evidence"]}
card = ev[f"hit-{hid}"]
assert card["kind"] == "hit" and card["ref"] == hid and card["flag_label"] == "Lifting or carrying" and card["severity"] == "high"
assert card["text"] == "a person carrying a heavy box" and card["caption"] == "Moving day, boxes everywhere" and card["date"] == "2026-03-14T07:12:00+00:00"
assert card["media"] == {"url": f"/evidence/{c.name}/{sha}.png", "kind": "image", "t0": None, "t1": None, "blur": False, "duration": None}
assert card["archived"] == "2026-03-20T09:00:00+00:00" and card["sha256"] == sha and card["grade"] == "B2" and card["notes"] == []
assert card["source"] == "Bluesky" and card["handle"] == "kvane88.bsky.social" and card["url"] == f"{acct}/post/1" and card["status"] == "new"
assert tc.get(card["media"]["url"]).content == photo  # the real file, by its hash
lead_cards = [e for e in d["evidence"] if e["kind"] != "hit"]
assert [e["flag"] for e in lead_cards] == ["lifting"] and lead_cards[0]["grade"] == "B2" and lead_cards[0]["severity"] == "med", lead_cards
assert "boxes everywhere" in lead_cards[0]["text"] and lead_cards[0]["notes"] == [f"cites E-{pid}"]
assert d["counts"] == {"flagged": 1, "leads": 1, "not_relevant": 0}
assert d["risk"] == {"score": 34, "label": "Low", "items": 2, "meaning": "how much there is to review, not the chance of fraud"}

# "Not relevant" through the existing route takes the item out of the counts and the risk, but keeps its card
assert tc.post(f"/api/cases/{c.name}/hits/{hid}", json={"status": "not relevant"}, headers=POST).status_code == 200
d = tc.get(f"/api/cases/{c.name}/flags").json()
assert d["flags"][0]["count"] == 0 and d["counts"] == {"flagged": 0, "leads": 1, "not_relevant": 1} and d["risk"]["items"] == 1
assert {e["id"]: e["status"] for e in d["evidence"]}[f"hit-{hid}"] == "not relevant"
lead_id = lead_cards[0]["ref"]
assert tc.post(f"/api/cases/{c.name}/leads/{lead_id}", json={"status": "kept"}, headers=POST).status_code == 200
d = tc.get(f"/api/cases/{c.name}/flags").json()
assert {e["ref"]: e["status"] for e in d["evidence"] if e["kind"] != "hit"} == {lead_id: "kept"}

# A background case gets no risk figure; a case with nothing collected answers cleanly
bg = Case.create("Rowan Ashby", "test: screening", kind="background", subject_residence="US-AZ")
d = tc.get(f"/api/cases/{bg.name}/flags").json()
assert d["risk"] is None and d["background"] is True and d["evidence"] == [] and d["flags"] == [] and d["counts"]["flagged"] == 0
print("ok")
