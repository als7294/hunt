"""Self-check for the case report (hunt/report.py). Run: uv run python test_report.py

Offline; all subjects here are fictional.
"""

import asyncio
import base64
import io
import json
import os
import re
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
case.add_seeds([handle, Seed("name", "Robert Vance"), Seed("phone", "+15205550143"), Seed("employer", "Example Health")])
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
    {"id": 2, "category": "injury", "what": "a post about the knee injury", "verdict": "likely", "status": "in report",
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
assert [x["id"] for x in rep["sections"]] == ["summary", "scope", "method", "presence", "identity", "people", "records",
                                             "found", "claim", "conclusion", "couldnt_see", "disclaimers"]
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
assert re.search(r"on (Mon|Tue|Wed|Thu|Fri|Sat|Sun) 2026-", t) and ("EDT" in t or "EST" in t), t  # search times in the investigator's zone, with the day
assert "Jo Example ran the searches" in t and "with Hunt " in t, t  # who collected, with what
gaps = " ".join(rep["couldnt_see"])
assert "phone details" in gaps and "whatsmyname failed" in gaps and "Posts on Instagram weren't read" in gaps, gaps
assert "login-only" in gaps and "Bluesky weren't read" not in gaps and "ruled not relevant" in gaps, gaps
assert "no date" in gaps and "Court and other public records" in gaps, gaps
# Posts read through Apify: the method says so, and the account isn't listed as unread (C12)
posts.append({"id": 3, "source": "Instagram", "account_url": "https://instagram.com/kestrel_vane88", "url": "https://instagram.com/p/x",
              "posted_at": "2026-04-01T10:00:00+00:00", "origin": "vendor", "media": [], "extra": None, "text": "hello"})
vend = compose()
assert "1 post on Instagram was obtained through Apify, a data vendor, under the investigator's own account." in text(vend)
assert "Posts on Instagram weren't read" not in " ".join(vend["couldnt_see"]), vend["couldnt_see"]
posts.pop()
disclaim = " ".join(s["text"] for s in rep["sentences"] if s["section"] == "disclaimers")
assert "Hunt's own code created no account" in disclaim and "used no pretext" in disclaim and "SHA-256" in disclaim and report.CONFIDENTIAL in disclaim, disclaim
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
assert [x["id"] for x in rep["exhibits"]] == ["E-2", "E-1"], rep["exhibits"]  # reported items, by platform and date
filed = {"id": 5, "category": "sport", "what": "a bike ride", "verdict": "likely", "status": "kept", "posted_at": None,
         "source": "Bluesky", "file": None}  # kept for her file only (decision D4): not printed, not "undated" either
side = compose(hs=[*hits, filed, {**filed, "id": 6, "status": "new"}])
assert "E-5" not in {e["id"] for e in side["evidence"]} | {x["id"] for x in side["exhibits"]}, side["evidence"]
assert compose(hs=[*hits, {**filed, "id": 6, "status": "new"}])["couldnt_see"] == compose()["couldnt_see"]  # unseen: not counted
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
             "last_date": "2024-10-01", "recipients": ["Committee To Elect Example"], "occupation": "Engineer",
             "employer": "Example Health"}),
           ("npi", "NPI Registry", "https://npiregistry.cms.hhs.gov/provider-view/1234567890",
            {"fullname": "Robert Vance", "npi": "1234567890", "credential": "RN", "specialty": "Registered Nurse",
             "organization": "Example Health Clinic"}),
           ("edgar", "SEC EDGAR (filer)", "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0001234567",
            {"fullname": "Robert Vance", "cik": 1234567, "filings": 2, "company": "Example Health Inc"}),
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
# Licences, business registries and FMCSA carriers are records too (hunt/sources), never accounts
case.add_run("licences", name, "found", 1, 1, "")
case.add_finding(Finding("licences", name, "Texas TDLR licence", "https://data.texas.gov/resource/7358-krk7.json?license_number=TX-1",
                         {"fullname": "Robert Vance", "licence": "Electrician", "licence_number": "TX-1", "expires": "2027-01-01",
                          "employer": "Example Health"}))
rep = compose()
lic = next(r for r in rep["records"] if r["source"] == "licences")
assert lic["summary"] == "Electrician, licence TX-1, expires 2027-01-01", lic
assert "Texas TDLR licence" not in {p["platform"] for p in rep["presence"]}, rep["presence"]
assert all(x["cites"] for x in rep["sentences"])
# Court open data and powerlifting results are records too; meets after the injury are named, never in screening
for src in ("courts", "activity"):
    case.add_run(src, name, "found", 1, 1, "")
case.add_finding(Finding("courts", name, "Ohio Court of Claims", "https://data.ohio.gov/example/2026-00001",
                         {"fullname": "Robert Vance", "roles": ["plaintiff"], "court": "Ohio Court of Claims",
                          "docket_number": "2026-00001", "case_type": "Personal injury", "filed": "2026-02-01", "employer": "Example Health"}))
case.add_finding(Finding("activity", name, "OpenPowerlifting", "https://www.openpowerlifting.org/u/robertvance",
                         {"fullname": "Robert Vance", "meet_count": 2, "first_date": "2025-06-01", "last_date": "2026-04-12",
                          "federations": ["USAPL"], "best_total_kg": 480.0, "location": "Arizona, USA", "birth_year": 1990,
                          "meets": [{"date": "2025-06-01", "meet": "Desert Open", "total_kg": 450.0},
                                    {"date": "2026-04-12", "meet": "Arizona State", "total_kg": 480.0}]}))
rep = compose()
by = {r["source"]: r["summary"] for r in rep["records"]}
assert by["courts"] == "Personal injury, as plaintiff, Ohio Court of Claims, docket 2026-00001, filed 2026-02-01, employer Example Health", by
assert by["activity"] == ("2 powerlifting meets from 2025-06-01 to 2026-04-12, USAPL, best total 480 kg, home Arizona, USA, "
                          "1 meet after the date of injury: 2026-04-12, Arizona State, total 480 kg"), by
assert "court records published as open data" in text(rep) and "published powerlifting results" in text(rep)
rep = compose(screening=True)
assert "courts" not in {r["source"] for r in rep["records"]}, rep["records"]  # a personal-injury case: protected
assert all("after the date of injury" not in r["summary"] for r in rep["records"]), rep["records"]
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
# A picture that may show a child goes into the export blurred, never as the original (K7, A5)
buf = io.BytesIO()
Image.radial_gradient("L").convert("RGB").save(buf, "JPEG")
_, kid = case._store(buf.getvalue(), "jpg")
kid_hit = {"id": 9, "post_id": 1, "category": "sport", "what": "a bike ride", "verdict": "likely", "status": "in report",
           "posted_at": "2026-04-12", "source": "Bluesky", "file": kid, "blur": True}
page = report.to_html(case, compose(hs=[*hits, kid_hit]))
assert base64.b64encode(buf.getvalue()).decode() not in page and "Shown blurred" in page
assert page.count("data:image/jpeg;base64,") == 2  # the fake capture's original, and the blurred copy
(case.dir / img).write_bytes(b"swapped")
rep = compose()
assert rep["checks"]["tampered"] == [img], rep["checks"]
assert not next(m for m in report.to_json(case, rep)["manifest"] if m["file"] == img)["ok"]
assert "Changed since saved" in report.to_html(case, rep)

# A note on a reported item is printed with it, cited to the note; screening drops one in protected words
from hunt import notes  # noqa: E402
shown = next(h for h in hits if h["status"] in ("kept", "in report"))
case.db.executescript(notes.SCHEMA)  # this file's hits are fixtures, not rows notes.add could check against
for words in ("The backpack looks heavy; the trail is steep.", "She mentioned her disability in the caption."):
    case.db.execute("insert into notes values (null, '2026-04-02T10:00:00+00:00', 'hit', ?, ?, null)", (str(shown["id"]), words))
n1, n2 = notes.list_notes(case, "hit", str(shown["id"]))[-2:]
rep = compose()
said = [x for x in rep["sentences"] if x["cites"] in ([n1["cite"]], [n2["cite"]])]
assert len(said) == 2 and "The backpack looks heavy" in said[0]["text"], said
assert f"[Note {n1['id']}]" in report.to_html(case, rep) or f"Note {n1['id']}" in report.to_html(case, rep)
assert not any(n2["cite"] in x["cites"] for x in compose(screening=True)["sentences"])

# Claim and evidence (analysis.md §9): the restrictions, each kept lead in its own facts, cited to the kept item;
# a restriction with nothing behind it says so; never a machine reading above "likely"; none in screening
claim = [x for x in compose()["sentences"] if x["section"] == "claim"]
said_ = {x["text"]: x["cites"] for x in claim}
assert "The claim states: no lifting over 5 kg; no running." in said_ and "The case also asks about: sport." in said_, said_
run = next(t for t in said_ if t.startswith("Running: "))
assert "finishing a 10k" in run and said_[run] == ["E-1"] and "almost certain" not in " ".join(said_), claim
assert "Lifting: nothing found after the injury that bears on this." in said_, said_
assert [x["text"] for x in compose(screening=True)["sentences"] if x["section"] == "claim"] == \
    ["This screening version leaves out the claim and the evidence set against it."]

one = compose(hs=[h for h in hits if h["status"] in ("kept", "in report")][:1])  # singular: "was", "Exhibit"
assert "1 item relating to the listed activities was kept for this report (Exhibit " in text(one), text(one)

# A subject abroad: the basis and the reason for no notice are printed, and missing until written down (F4)
case.set_details(subject_residence="GB")
rep = compose()
assert {"abroad_basis", "no_notice"} <= set(rep["checks"]["missing"]) and "Lawful basis on record: none recorded." in text(rep)
case.set_details(abroad_basis="Legitimate interests in investigating a claim", no_notice="Notice would impair the investigation")
rep = compose()
assert "abroad_basis" not in rep["checks"]["missing"] and "The subject lives in GB. Lawful basis on record: Legitimate " \
    "interests in investigating a claim. Why they weren't told of this investigation: Notice would impair the investigation." in text(rep)
case.set_details(subject_residence="", abroad_basis="", no_notice="")

# A Washington subject (My Health My Data Act): the fraud basis is on record or missing; observed activity only,
# described by the activity looked for; nothing about the injury or physical condition (F3)
case.set_details(subject_residence="US-WA")
rep = compose()
assert "mhmda_basis" in rep["checks"]["missing"] and "Fraud basis on record: none recorded." in text(rep), text(rep)
case.set_details(mhmda_basis="Claim fraud investigation for Fictional Mutual")
rep, t = compose(), text(compose())
assert "mhmda_basis" not in rep["checks"]["missing"] and "Fraud basis on record: Claim fraud investigation" in t, t
assert "E-2" not in {e["id"] for e in rep["evidence"]} and "knee" not in t and "finishing a 10k" not in t, t
assert "relates to sport and gym" in t and "41 days after the date of loss" in t, t
assert "Lifting: nothing found after the date of loss that bears on this." in t, t  # the claim section stays, reworded
assert not any(report.HEALTH.search(x["text"]) for x in rep["sentences"] if "My Health My Data" not in x["text"]), rep["sentences"]
case.set_details(subject_residence="", mhmda_basis="")

# From a page that isn't the subject's: a finding only once her note says how it concerns them (A7)
posts.append({"id": 7, "source": "Bluesky", "account_url": "https://bsky.app/profile/a_friend", "url": "https://bsky.app/p/7",
              "posted_at": "2026-04-15T10:00:00+00:00", "origin": "captured", "media": [], "extra": {"not_subject": True}})
theirs = {"id": 7, "post_id": 7, "category": "sport", "what": "a group hike", "verdict": "likely", "status": "in report",
          "posted_at": "2026-04-15", "source": "Bluesky", "file": None}
rep = compose(hs=[*hits, theirs])
assert "E-7" not in {e["id"] for e in rep["evidence"]} and any("aren't the subject's" in x for x in rep["couldnt_see"]), rep["couldnt_see"]
case.db.execute("create table if not exists hits (id integer primary key)")
case.db.execute("insert or ignore into hits values (7)")
from hunt import notes as notes_  # noqa: E402
notes_.add(case, "The subject is tagged and in the photo", about="hit", ref=7)
assert "E-7" in {e["id"] for e in compose(hs=[*hits, theirs])["evidence"]}
posts.pop()

# Shown to a restricted audience: out of the report until counsel approves that item, then in it, saying so (K3)
posts[0]["extra"] = {"audience": "Friends"}
rep = compose()
assert "E-1" not in {e["id"] for e in rep["evidence"]} | {x["id"] for x in rep["exhibits"]}, rep["evidence"]
assert any("1 item shown to a restricted audience (Friends) was left out pending counsel's approval." == x for x in rep["couldnt_see"]), rep["couldnt_see"]
case.audit("counsel approved", {"hit": 1, "by": "A. Counsel", "note": None})
rep = compose()
assert "E-1" in {e["id"] for e in rep["evidence"]} and not any("restricted audience" in x for x in rep["couldnt_see"])
assert "It was shown to Friends, not the public; counsel (A. Counsel) approved its use in this report." in text(rep), text(rep)
posts[0]["extra"] = None

# People around the subject (legal.md A1–A10): as observed and cited, never a relationship label; a minor unnamed;
# none in screening; "Not relevant" leaves them out
from hunt import graph  # noqa: E402
posts.append({"id": 2, "source": "Bluesky", "account_url": "https://bsky.app/profile/kestrel_vane88", "url": "https://bsky.app/p/2",
              "posted_at": "2026-04-20T10:00:00+00:00", "origin": "fetched", "media": [], "extra": None,
              "text": "Lake day with my brother Dan Okafor. Proud of my son Leo, 9 years old!"})
said = [x for x in compose()["sentences"] if x["section"] == "people"]
words = " ".join(x["text"] for x in said)
assert said[0]["text"].startswith("The subject's own posts, bios and public records name 2 other people"), said
assert "Dan Okafor: a post of" in words and "my brother Dan Okafor" in words and "Brother" not in words, words
assert "A child (name withheld): a post of" in words and "Leo" not in words, words
assert all(x["cites"] == [f"A-{bsky_id}"] for x in said[1:]), said  # the post isn't kept: cited to the account that posted it
dan = next(x for x in graph.associates(posts, build(case)["candidates"], case.seeds())["people"] if x["name"] == "Dan Okafor")
case.db.execute("insert or replace into meta values ('people_hidden', ?)", (json.dumps([dan["id"]]),))
assert "Dan Okafor" not in " ".join(x["text"] for x in compose()["sentences"])  # "Not relevant"
assert [x["text"] for x in compose(screening=True)["sentences"] if x["section"] == "people"] == \
    ["This screening version leaves out the people around the subject."]
posts.pop()

# A child's name never prints (C13, A5): graph's minor pass (AN1) names them; the report withholds each, everywhere
stand_in = not hasattr(graph, "minor_names")
if stand_in:  # until the analysis branch is merged: AN1's interface, standing in
    graph.minor_names = lambda ps, cands, seeds, labels=(): ["Leo"] if any("my son Leo" in (p.get("text") or "") for p in ps) else []
    graph.redact = lambda t, names: re.sub(r"(?<!\w)Leo(?!\w)", "[name withheld]", t, flags=re.I) if t and names else t
posts.append({"id": 8, "source": "Bluesky", "account_url": "https://bsky.app/profile/kestrel_vane88", "url": "https://bsky.app/p/8",
              "posted_at": "2026-04-20T10:00:00+00:00", "origin": "fetched", "media": [], "extra": None,
              "text": "Park day with my son Leo"})
kid = {"id": 8, "post_id": 8, "category": "sport", "what": "a man pushing Leo on a swing", "caption": "Park day with my son Leo",
       "verdict": "likely", "status": "in report", "posted_at": "2026-04-20", "source": "Bluesky", "file": None}
rep = compose(hs=[*hits, kid])
page = report.to_html(case, rep)
assert "E-8" in {e["id"] for e in rep["evidence"]} and "Leo" not in page and "[name withheld]" in page, page[-3000:]
posts.pop()
if stand_in:
    del graph.minor_names, graph.redact

# A case known only by a username: no "the subject, the subject", the header names the case, and accounts she
# ruled out are cited to her decisions (they're in no table, so an account id couldn't be looked up)
handle = Case.create("example handle", "Test: a public organisation's handle", kind="diligence", tool="person")
seed = Seed("username", "examplehandle")
handle.add_seeds([seed])
for site, url in (("GitHub", "https://github.com/examplehandle"), ("Mastodon", "https://mastodon.example/@examplehandle")):
    handle.add_finding(Finding("maigret", seed, site, url, {}))
handle.decide("https://mastodon.example/@examplehandle", "not him")
rep2 = report.compose(handle, build(handle), [], [], handle.verify(), screening=False, labels={})
assert "the subject, the subject" not in text(rep2) and rep2["header"]["subject"] == "example handle", rep2["header"]
out = [x for x in rep2["sentences"] if "ruled out" in x["text"] and "other account" in x["text"]]
assert out and all(c.startswith("M-a") for c in out[0]["cites"]), out

# A background (employment) case: always the screening version, of the accounts she confirmed only, with the FCRA
# notice; relationship words, protected traits and co-parties' names never print (K1, A8, A9)
bg = Case.create("Quill check", "Employer XYZ: pre-employment check, consent on file", kind="background", tool="person")
bseed, bname = Seed("username", "rquill_example"), Seed("name", "Rob Quill")
bg.add_seeds([bseed, bname])
mine, other = "https://bsky.app/profile/rquill_example", "https://bsky.app/profile/rquill_example2"
for url in (mine, other):
    bg.add_finding(Finding("maigret", bseed, "Bluesky", url, {"fullname": "Rob Quill"}))
bg.add_run("courts", bname, "found", 1, 1, "")
court = "https://data.ohio.gov/example/2025-00002"
bg.add_finding(Finding("courts", bname, "Ohio Court of Claims", court, {"fullname": "Rob Quill", "roles": ["plaintiff"],
                       "case": "Quill v. Dana Mercer", "court": "Ohio Court of Claims", "docket_number": "2025-00002"}))
rep = report.compose(bg, build(bg), [], [], bg.verify(), labels={})
assert rep["screening"] is True and rep["presence"] == [] and rep["records"] == [], rep["presence"]  # nothing confirmed yet
assert report.FCRA in [x["text"] for x in rep["sentences"] if x["section"] == "disclaimers"]
bg.decide(mine, "him")
bg.decide(court, "him")
bposts = [{"id": i, "source": "Bluesky", "account_url": acct, "url": f"{acct}/post/{i}", "posted_at": "2026-05-01T10:00:00+00:00",
           "origin": "fetched", "media": [], "extra": None, "text": t}
          for i, acct, t in ((1, mine, "Dinner with my wife Ines"), (2, mine, "Waiting on my mom's surgery"),
                             (3, mine, "Gym at six"), (4, other, "Trail run with friends"))]
bhits = [{"id": i, "post_id": i, "category": "sport", "what": what, "caption": cap, "verdict": "likely", "status": "in report",
          "posted_at": "2026-05-01", "source": "Bluesky", "file": None}
         for i, what, cap in ((1, "two people at dinner", "Dinner with my wife Ines"), (2, "a hospital corridor", "Waiting on my mom's surgery"),
                              (3, "a gym selfie", "Gym at six"), (4, "a trail run", "Trail run with friends"))]
from hunt import notes  # noqa: E402
bg.db.execute("create table hits (id integer primary key)")  # the note's target; the hits themselves are passed in
bg.db.execute("insert into hits values (3)")
notes.add(bg, "his mom took this one", about="hit", ref=3)
rep = report.compose(bg, build(bg), bposts, bhits, bg.verify(), labels={})
page = report.to_html(bg, rep)
assert [x["url"] for x in rep["presence"]] == [mine] and [e["id"] for e in rep["evidence"]] == ["E-3"], rep["evidence"]
assert not any(report.RELATION.search(x["text"]) for x in rep["sentences"] if "screening version" not in x["text"]), rep["sentences"]
for leak in ("Ines", "surgery", "Dana Mercer", "his mom", "rquill_example2"):
    assert leak not in page, leak
assert rep["records"][0]["summary"] == "Ohio Court of Claims, docket 2025-00002", rep["records"]
assert report.RELATION.search("with my bro") and not report.RELATION.search("Pittsburgh, PA and Boston, MA")

if os.environ.get("HUNT_TEST_PDF"):  # needs Chromium: uv run playwright install chromium
    assert asyncio.run(report.to_pdf(report.to_html(case, rep, pdf=True), rep)).startswith(b"%PDF")

print("ok")
