"""Self-check for the case report (hunt/report.py). Run: uv run python test_report.py

Offline; all subjects here are fictional.
"""

import asyncio
import os
import tempfile

os.environ["HUNT_HOME"] = tempfile.mkdtemp()  # before hunt.case reads it

from hunt import report
from hunt.case import Case
from hunt.search import build
from hunt.seed import Finding, Seed

case = Case.create("Vance claim", "Insurer XYZ claim 123", kind="insurance", reference="CLM-123",
                   injury_date="2026-03-01", look_for=["sport", "injury"], tool="person")
handle = Seed("username", "kestrel_vane88")
case.add_seeds([handle, Seed("name", "Robert Vance"), Seed("phone", "+15205550143")])
case.add_run("maigret", handle, "found", 2, 600, "")
case.add_run("-", Seed("phone", "+15205550143"), "skipped", 0, 0, "no source searches this kind yet")
case.add_run("whatsmyname", handle, "failed", 0, 0, "ReadTimeout")
case.add_finding(Finding("maigret", handle, "Bluesky", "https://bsky.app/profile/kestrel_vane88",
                         {"fullname": "Bob Vance"}, body="<html>profile</html>"))
case.add_finding(Finding("maigret", handle, "Instagram", "https://instagram.com/kestrel_vane88", {"fullname": "Bob Vance"}))
img_sha, img = case._store(b"\xff\xd8\xff fake jpeg", "jpg")
hits = [
    {"id": 1, "category": "sport", "what": "finishing a 10k <race>", "verdict": "almost certain", "status": "in report",
     "posted_at": "2026-04-10", "timing": "after", "days_after": 40, "source": "Bluesky", "file": img},
    {"id": 2, "category": "injury", "what": "a post about the knee injury", "verdict": "likely", "status": "kept",
     "posted_at": "2026-03-02", "timing": "after", "days_after": 1, "source": "Bluesky", "file": None},
    {"id": 3, "category": "sport", "what": "a gym selfie", "verdict": "likely", "status": "not relevant",
     "posted_at": None, "source": "Instagram", "file": None},
]
labels = {"sport": "sport and gym", "injury": "mentions of the injury"}


def compose(screening=False):
    return report.compose(case, build(case), [], hits, case.verify(), screening=screening, labels=labels)


# Before the investigator confirms: "a person", machine verdicts no stronger than "likely"
rep = compose()
texts = " ".join(s["text"] for s in rep["sentences"])
assert all(s["cites"] for s in rep["sentences"]) and rep["checks"]["every_sentence_cited"], rep["sentences"]
assert len(rep["couldnt_see"]) == len(rep["couldnt_see_cites"]) and all(rep["couldnt_see_cites"])
assert [x["id"] for x in rep["sections"]][-1] == "couldnt_see"
assert not any(x["section"] == "couldnt_see" for x in rep["sentences"])  # the app shows them as bullets, once
assert "a person matching the details supplied" in texts and "Robert Vance's" not in texts
assert "almost certain" not in texts and "very likely" not in texts, texts
assert rep["evidence"][0]["verdict"] == "likely", rep["evidence"]
assert any(c.startswith("A-") for s in rep["sentences"] if s["section"] == "identity" for c in s["cites"])
assert any(c.startswith("M-") for s in rep["sentences"] if s["section"] == "method" for c in s["cites"])
assert not any(w in texts for w in ("+2.", "+3.", "+4.", "bits")), texts  # never weights
gaps = " ".join(rep["couldnt_see"])
assert "phone details" in gaps and "whatsmyname failed" in gaps and "Posts on Instagram weren't read" in gaps, gaps
assert "Bluesky weren't read" not in gaps and "ruled not relevant" in gaps and "no date" in gaps, gaps
assert "Court and other public records" in gaps, gaps
assert {e["id"] for e in rep["evidence"]} == {"E-1", "E-2"}  # kept or in report only
assert "40 days after the injury" in texts

# An uncited sentence can't be written
try:
    report._Doc(False).say("summary", "Trust me.", [])
    raise AssertionError("an uncited sentence must be refused")
except AssertionError as e:
    assert "uncited" in str(e)

# Namesakes are accounts whose name matches but nothing else does; a clashing name isn't one
assert "shares the name" not in texts  # Instagram's name matches and it's in the person

# Once confirmed, the report names the subject
case.decide("", "him")
case.decide("https://bsky.app/profile/kestrel_vane88", "him")
rep = compose()
texts = " ".join(s["text"] for s in rep["sentences"])
assert "Robert Vance's" in texts and "a person matching" not in texts, texts
marked = next(x for x in rep["sentences"] if x["text"].startswith("The investigator marked Bluesky"))
assert len([c for c in marked["cites"] if c.startswith("M-a")]) == 2, marked  # its own decision + the person's
assert "investigator confirmed this account" not in texts, texts

# Screening: protected traits (here, health) leave the report entirely
rep = compose(screening=True)
texts = " ".join(s["text"] for s in rep["sentences"])
assert report.PROTECTED.search(texts) is None, report.PROTECTED.search(texts)
assert "2026-03-01" not in texts and {e["id"] for e in rep["evidence"]} == {"E-1"}, rep["evidence"]
assert all(s["cites"] for s in rep["sentences"])

# Exports: escaped HTML with the image inlined; JSON manifest; tampering shows up everywhere
page = report.to_html(case, compose())
assert "finishing a 10k &lt;race&gt;" in page and "<race>" not in page
assert "data:image/jpeg;base64," in page
data = report.to_json(case, compose())
assert all(m["ok"] for m in data["manifest"]) and any(m["file"] == img for m in data["manifest"])
(case.dir / img).write_bytes(b"swapped")
rep = compose()
assert rep["checks"]["tampered"] == [img], rep["checks"]
assert not next(m for m in report.to_json(case, rep)["manifest"] if m["file"] == img)["ok"]
assert "Changed since saved" in report.to_html(case, rep)

if os.environ.get("HUNT_TEST_PDF"):  # needs Chromium: uv run playwright install chromium
    assert asyncio.run(report.to_pdf(page)).startswith(b"%PDF")

print("ok")
