"""Self-check for the case report (hunt/report.py). Run: uv run python test_report.py

Offline; all subjects here are fictional.
"""

import asyncio
import io
import os
import tempfile
import zipfile
from pathlib import Path

os.environ["HUNT_HOME"] = tempfile.mkdtemp()  # before hunt.case reads it

from PIL import Image

from hunt import bundle, report
from hunt.case import Case
from hunt.search import build
from hunt.seed import Finding, Seed

case = Case.create("Vance claim", "Insurer XYZ claim 123: disputed injury, permissible purpose on file", kind="insurance",
                   reference="CLM-123", injury_date="2026-03-01", look_for=["sport", "injury"], tool="person",
                   client="Fictional Mutual", adjuster="A. Adjuster", assignment_date="2026-03-20",
                   subject_dob="1990-05-05", limits="No lifting over 5 kg; no running")
case.audit("case details", {"client": "Fictional Mutual"})
handle = Seed("username", "kestrel_vane88")
case.add_seeds([handle, Seed("name", "Robert Vance"), Seed("phone", "+15205550143")])
case.add_run("maigret", handle, "found", 2, 600, "")
case.add_run("-", Seed("phone", "+15205550143"), "skipped", 0, 0, "no source searches this kind yet")
case.add_run("whatsmyname", handle, "failed", 0, 0, "ReadTimeout")
case.add_finding(Finding("maigret", handle, "Bluesky", "https://bsky.app/profile/kestrel_vane88",
                         {"fullname": "Bob Vance"}, body="<html>profile</html>"))
case.add_finding(Finding("maigret", handle, "Instagram", "https://instagram.com/kestrel_vane88", {"fullname": "Bob Vance"}))
img_sha, img = case._store(b"\xff\xd8\xff fake jpeg", "jpg")
posts = [{"id": 1, "source": "Bluesky", "account_url": "https://bsky.app/profile/kestrel_vane88", "url": "https://bsky.app/p/1",
          "posted_at": "2026-04-11T15:00:00+00:00", "origin": "fetched", "media": []}]
hits = [
    {"id": 1, "post_id": 1, "category": "sport", "what": "finishing a 10k <race>", "verdict": "almost certain",
     "status": "in report", "posted_at": "2026-04-11", "timing": "after", "days_after": 41, "source": "Bluesky", "file": img},
    {"id": 2, "category": "injury", "what": "a post about the knee injury", "verdict": "likely", "status": "kept",
     "posted_at": "2026-03-02", "timing": "after", "days_after": 1, "source": "Bluesky", "file": None},
    {"id": 3, "category": "sport", "what": "a gym selfie", "verdict": "likely", "status": "not relevant",
     "posted_at": None, "source": "Instagram", "file": None},
]
labels = {"sport": "sport and gym", "injury": "mentions of the injury"}


def compose(screening=False, hs=None):
    return report.compose(case, build(case), posts, hs or hits, case.verify(), screening=screening, labels=labels)


def text(rep):
    return " ".join(s["text"] for s in rep["sentences"])


# Settings: saved per investigator, validated; a logo must be a real PNG or JPEG
assert report.settings()["firm"] == "" and report.settings()["confidentiality"] == report.CONFIDENTIAL
for bad in ({"timezone": "Mars/Olympus"}, {"colour": "red"}, {"firm": 7}):
    try:
        report.save_settings(**bad)
        raise AssertionError(f"accepted {bad}")
    except ValueError:
        pass
prefs = report.save_settings(firm="Example Investigations", investigator="Jo Example", licence="PI-000000",
                             timezone="America/New_York", contact="jo@example.com")
assert prefs["firm"] == "Example Investigations" and prefs["timezone"] == "America/New_York" and not prefs["logo"]
for bad in (b"<svg onload=alert(1)>", b"not an image"):
    try:
        report.save_logo(bad)
        raise AssertionError("accepted a bad logo")
    except ValueError:
        pass
png = io.BytesIO()
Image.new("RGB", (60, 20), "navy").save(png, "PNG")
report.save_logo(png.getvalue())
assert report.settings()["logo"] and report.logo_path().suffix == ".png"

# Before the investigator confirms: neutral wording, machine readings no stronger than "likely"
rep = compose()
assert [x["id"] for x in rep["sections"]] == ["summary", "scope", "method", "presence", "identity", "records", "found",
                                             "conclusion", "couldnt_see", "disclaimers"]
assert all(s["cites"] for s in rep["sentences"]) and rep["checks"]["every_sentence_cited"], rep["sentences"]
assert len(rep["couldnt_see"]) == len(rep["couldnt_see_cites"]) and all(rep["couldnt_see_cites"])
assert not any(x["section"] == "couldnt_see" for x in rep["sentences"])  # the app shows them as bullets, once
t = text(rep)
assert "a person matching the details supplied" in t and "Robert Vance's" not in t
assert "almost certain" not in t and "very likely" not in t, t
assert rep["evidence"][0]["verdict"] == "likely", rep["evidence"]
assert not __import__("re").search(r"[+-]\d+\.\d\b|\bbits\b", t), t  # never weights
assert any(c.startswith("A-") for s in rep["sentences"] if s["section"] == "identity" for c in s["cites"])
assert any(c.startswith("M-") for s in rep["sentences"] if s["section"] == "method" for c in s["cites"])
assert "Fictional Mutual" in t and "claim CLM-123" in t and "No lifting over 5 kg" in t, t
assert "on Thu 2026-" in t and ("EDT" in t or "EST" in t), t  # search times in the investigator's zone, with the day
assert "Jo Example ran the searches" in t and "with Hunt " in t, t  # who collected, with what
gaps = " ".join(rep["couldnt_see"])
assert "phone details" in gaps and "whatsmyname failed" in gaps and "Posts on Instagram weren't read" in gaps, gaps
assert "login-only" in gaps and "Bluesky weren't read" not in gaps and "ruled not relevant" in gaps, gaps
assert "no date" in gaps and "Court and other public records" in gaps, gaps
disclaim = " ".join(s["text"] for s in rep["sentences"] if s["section"] == "disclaimers")
assert "no pretext" in disclaim and "SHA-256" in disclaim and report.CONFIDENTIAL in disclaim, disclaim
assert report.NOT_CONSUMER in disclaim and report.FCRA not in disclaim, disclaim  # a claim, not employment screening
assert all(x.get("platform") == "Bluesky" for x in rep["sentences"] if x["section"] == "found"), rep["sentences"]

# Header block, presence table, exhibits
h = rep["header"]
assert (h["client"], h["adjuster"], h["reference"], h["subject"], h["subject_dob"], h["investigator"], h["licence"]) == \
       ("Fictional Mutual", "A. Adjuster", "CLM-123", "Robert Vance", "1990-05-05", "Jo Example", "PI-000000"), h
assert h["title"] == "Social Media and Online Activity Investigation" and rep["checks"]["missing"] == [], rep["checks"]
rows = {p["platform"]: p for p in rep["presence"]}
assert set(rows) == {"Bluesky", "Instagram"} and rows["Bluesky"]["username"] == "kestrel_vane88", rows
assert rows["Bluesky"]["last_activity"].startswith("2026-04-11") and rows["Bluesky"]["relevant"] == "yes", rows
assert rows["Instagram"]["visibility"] == "public" and rows["Instagram"]["relevant"] == "not reviewed", rows
assert [x["id"] for x in rep["exhibits"]] == ["E-2", "E-1"], rep["exhibits"]  # kept items, by platform and date
assert {e["id"] for e in rep["evidence"]} == {"E-1", "E-2"}  # kept or in report only
found = " ".join(s["text"] for s in rep["sentences"] if s["section"] == "found")
assert "Exhibit 2: Bluesky, posted 2026-04-11, 41 days after" in found and "1 day after" in found, found
assert "whatsmyname was tried" in t and "Purpose on record: Insurer XYZ claim 123: disputed injury, permissible purpose on file." in t, t
assert "belonging, or likely belonging, to a person matching" in t and "supplied's" not in t, t

# An uncited sentence can't be written
try:
    report._Doc(False).say("summary", "Trust me.", [])
    raise AssertionError("an uncited sentence must be refused")
except AssertionError as e:
    assert "uncited" in str(e)

# A source run again shows once, citing every run
case.add_run("maigret", handle, "found", 2, 610, "")
again = [x for x in compose()["sentences"] if x["text"].startswith("maigret checked")]
assert len(again) == 1 and len(again[0]["cites"]) == 2 and "610 sites" in again[0]["text"], again

# Confirmed: the subject is named, the account's capture becomes Exhibit 1, the decision is dated
shot = io.BytesIO()
Image.new("RGB", (40, 30), "white").save(shot, "PNG")
bsky_id = case.rows("select id from findings where site = 'Bluesky'")[0]["id"]
case.add_capture(bsky_id, shot.getvalue(), "<html>rendered</html>")
case.decide("", "him")
case.decide("https://bsky.app/profile/kestrel_vane88", "him")
case.set_details(recommendations="Re-check the Bluesky account monthly.")
case.audit("case details", {"recommendations": "Re-check the Bluesky account monthly."})
rep = compose()
t = text(rep)
assert "Robert Vance's" in t and "a person matching" not in t, t
assert [x["id"] for x in rep["exhibits"]][:1] == [f"A-{bsky_id}"] and rep["exhibits"][0]["kind"] == "account screenshot"
assert rep["exhibits"][0]["page_source"].endswith(".html") and "_rendered-page_" in rep["exhibits"][0]["page_source"]
assert "personally conducted or supervised" in rep["certification"]["text"]
marked = next(x for x in rep["sentences"] if x["text"].startswith("The investigator confirmed the Bluesky"))
assert len([c for c in marked["cites"] if c.startswith("M-a")]) == 2 and " on 2026-" in marked["text"], marked
assert "investigator confirmed this account" not in t, t
assert "The investigator recommends: Re-check the Bluesky account monthly." in t, t
assert rows["Bluesky"]["exhibit"] is None and {p["platform"]: p for p in rep["presence"]}["Bluesky"]["exhibit"] == 1

# A pattern in the kept items becomes a recommendation, cited to those items
saturdays = [{**hits[0], "id": 10 + i, "posted_at": d, "file": None} for i, d in
             enumerate(("2026-04-04", "2026-04-11", "2026-04-18", "2026-04-15"))]
conc = " ".join(s["text"] for s in compose(hs=saturdays)["sentences"] if s["section"] == "conclusion")
assert "3 of the 4 dated items were posted on Saturdays" in conc, conc

# Exhibit file names are the evidence bundle's, so the report and the bundle agree
made = bundle.make(case, Path(tempfile.mkdtemp()))
in_zip = {Path(n).name for n in zipfile.ZipFile(made["path"]).namelist() if n.startswith("exhibits/")}
names = {x["name"] for x in rep["exhibits"] if x["name"]}
assert names and names <= in_zip, (names, in_zip)

# Screening: protected traits, the date of birth, the injury and screenshots all stay out
rep = compose(screening=True)
t = " ".join(x["text"] for x in rep["sentences"] if "screening version" not in x["text"])  # that one names the categories
assert report.PROTECTED.search(t) is None, report.PROTECTED.search(t)
assert "2026-03-01" not in t and "1990-05-05" not in t and {e["id"] for e in rep["evidence"]} == {"E-1"}, rep["evidence"]
assert "Assigned 2026-03-20 by Fictional Mutual (adjuster: A. Adjuster)." in t and "Purpose on record" not in t, t
assert rep["header"]["subject_dob"] is None and rep["header"]["injury_date"] is None
assert all(x["screenshot"] is None for x in rep["accounts"]) and all(x["kind"] != "account screenshot" for x in rep["exhibits"])
assert all(s["cites"] for s in rep["sentences"])
page = report.to_html(case, rep)
assert "Screening version" in page and "1990-05-05" not in page and "account screenshot" not in page

# Public records are records, not accounts; screening leaves out political and health ones entirely
name = Seed("name", "Robert Vance")
for src, n in (("fec", 3), ("npi", 1), ("edgar", 1), ("courtlistener", 2)):
    case.add_run(src, name, "found", n, 1, "")
case.add_run("courtlistener", Seed("name", "Bob Vance"), "nothing found", 0, 0,
             "not run: CourtListener needs a free account token in HUNT_COURTLISTENER_TOKEN")
records = [("fec", "FEC contributions", "https://www.fec.gov/data/receipts/individual-contributions/?contributor_name=vance",
            {"fullname": "Robert Vance", "contributions": 3, "total_usd": 450, "first_date": "2024-02-01",
             "last_date": "2024-10-01", "recipients": ["Committee To Elect Example"], "occupation": "Engineer"}),
           ("npi", "NPI Registry", "https://npiregistry.cms.hhs.gov/provider-view/1234567890",
            {"fullname": "Robert Vance", "npi": "1234567890", "credential": "RN", "specialty": "Registered Nurse"}),
           ("edgar", "SEC EDGAR (filer)", "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0001234567",
            {"fullname": "Robert Vance", "cik": 1234567, "filings": 2}),
           ("courtlistener", "CourtListener (RECAP)", "https://www.courtlistener.com/docket/1/vance-v-example-health-plan/",
            {"case": "Vance v. Example Health Plan", "nature_of_suit": "ERISA", "court": "azd"}),
           ("courtlistener", "CourtListener (RECAP)", "https://www.courtlistener.com/docket/2/vance-v-example-builders/",
            {"case": "Vance v. Example Builders", "nature_of_suit": "Contract: Other", "court": "azd"})]
for src, site, url, attrs in records:
    case.add_finding(Finding(src, name, site, url, attrs))
rep = compose()
t, gaps = text(rep), " ".join(rep["couldnt_see"])
assert {r["source"] for r in rep["records"]} == {"fec", "npi", "edgar"}, rep["records"]  # dockets carry no name to match
assert "[Rec. 1]" in report.to_html(case, rep)  # record citations read as table rows
assert not {"FEC contributions", "NPI Registry"} & {p["platform"] for p in rep["presence"]}, rep["presence"]
assert "3 itemized contributions totalling $450" in t and "NPI 1234567890, RN, Registered Nurse" in t, t
assert "2 other records under the same name were judged unlikely" in t and "SEC filer CIK 1234567" in t, t
assert "Public records were limited to FEC itemized political contributions" in gaps, gaps
assert "Posts on FEC" not in gaps and "Posts on NPI" not in gaps and "1 flagged item was ruled" in gaps, gaps
assert "courtlistener wasn't run: CourtListener needs a free account token" in gaps, gaps
assert not any("courtlistener" in x["text"] and "Bob Vance" in x["text"] for x in rep["sentences"]), rep["sentences"]
assert all(x["cites"] for x in rep["sentences"])
rep = compose(screening=True)
everything = " ".join([text(rep), *rep["couldnt_see"], str(rep["records"]), str(rep["presence"]), str(rep["exhibits"]),
                       str(rep["log"]), report.to_html(case, rep)])
for leak in ("FEC", "fec ", "itemized", "Committee To Elect", "NPI", "npi ", "Nurse", "Health Plan", "ERISA"):
    assert leak not in everything, leak
assert {r["source"] for r in rep["records"]} == {"edgar"} and "1 other record under the same name was judged" in text(rep)
assert "This screening version leaves out protected characteristics" in text(rep)  # its own words name them; it stays
assert report.PROTECTED.search(" ".join(x["text"] for x in rep["sentences"] if "screening version" not in x["text"])) is None
assert all(x["cites"] for x in rep["sentences"])
log_ids = {x["audit_log_id"] for x in compose()["log"] if x["audit_log_id"]}
assert log_ids and all(isinstance(i, int) for i in log_ids)  # matches audit-log.csv in the evidence bundle

# The case's life: re-checks, watching, legal hold and closing are reported, each cited to its log entry
case.audit("recheck", {"accounts": 1, "new_posts": 2, "changes": 1, "captured": 1})
case.audit("watch on", {"every_days": 3, "next": "2026-05-01"})
case.audit("watch off", {"why": "the case is closed"})
case.set_hold(True, "litigation expected")
case.close("Claim settled")
t = text(compose())
assert "looked at again 1 time" in t and "2 new posts, 1 change" in t and "watched every 3 days" in t, t
assert "Watching stopped on" in t and "The case was closed on" in t and "Claim settled." in t and "legal hold since" in t, t
case.reopen()
case.set_hold(False)
assert "The case was closed" not in text(compose()) and "legal hold since" not in text(compose())

# Exports: escaped HTML with images inlined, a running header and page numbers when printed
rep = compose()
page = report.to_html(case, rep)
assert "finishing a 10k &lt;race&gt;" in page and "<race>" not in page
assert page.count("data:image/png;base64,") == 2 and "data:image/jpeg;base64," in page  # logo + capture, kept photo
assert '@bottom-right{content:"Page " counter(page) " of " counter(pages)' in page and "File vance-claim" in page
assert "Appendix A: Exhibits" in page and "Appendix B: Search and case log" in page and "PI-000000" in page
assert "[Ex. 1" in page and "Log 1" in page, page[:2000]  # citations read as exhibits and log lines
assert "<h3>Bluesky</h3>" in page and "Page source" in page and "Z)</td>" in page  # platform heads; UTC in exhibits
assert "@bottom-right" not in report.to_html(case, rep, pdf=True)  # Chromium prints the PDF's own
data = report.to_json(case, rep)
assert all(m["ok"] for m in data["manifest"]) and any(m["exhibit_name"] for m in data["manifest"])
(case.dir / img).write_bytes(b"swapped")
rep = compose()
assert rep["checks"]["tampered"] == [img], rep["checks"]
assert not next(m for m in report.to_json(case, rep)["manifest"] if m["file"] == img)["ok"]
assert "Changed since saved" in report.to_html(case, rep)

if os.environ.get("HUNT_TEST_PDF"):  # needs Chromium: uv run playwright install chromium
    assert asyncio.run(report.to_pdf(report.to_html(case, rep, pdf=True), rep)).startswith(b"%PDF")

print("ok")
