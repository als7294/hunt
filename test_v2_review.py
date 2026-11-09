"""Self-check for the review step's API (hunt/api2/review.py). Run: uv run python test_v2_review.py

Offline, fictional people only: the case is built by hand and nothing is searched.
"""

import asyncio
import os
import tempfile
import warnings

os.environ["HUNT_HOME"] = tempfile.mkdtemp()
warnings.filterwarnings("ignore", message="Using `httpx` with")

from hunt import app as server  # noqa: E402,F401  (api2 modules import from it)
from hunt import search  # noqa: E402
from hunt.api2 import review as rv  # noqa: E402
from hunt.case import Case  # noqa: E402
from hunt.seed import Finding, Seed  # noqa: E402

name, handle, place = Seed("name", "Dorian Vell"), Seed("username", "velvetforge"), Seed("location", "Ocala, FL")
case = Case("review test", "self-check, fictional")
case.add_seeds([name, handle, place])
case.add_run("maigret", handle, "found", 4, 700, "")
add = lambda seed, site, url, **attrs: case.add_finding(Finding("maigret", seed, site, url, attrs))
add(handle, "Tube", "https://tube.test/velvetforge", fullname="Dorian Vell", website="https://github.com/forge-dv")
add(handle, "Chess", "https://chess.test/velvetforge", fullname="Dorian Vell", other_usernames=["bad_lead_77"])
add(handle, "Pics", "https://pics.test/velvetforge")  # a handle alone: possibly theirs
add(handle, "LinkedIn", "https://www.linkedin.com/in/velvetforge", fullname="Dorian Vell")  # login-walled
add(name, "Chess", "https://chess.test/dvell-1", fullname="Dorian Vell")  # a namesake on a site she'll reject on
add(name, "Pics", "https://pics.test/dvell-2", fullname="Dorian Vell")
case.add_finding(Finding("businesses", name, "Business registry", "https://biz.test/77", {"fullname": "Dorian Vell", "location": "Ocala, FL"}))
checks = {"lifting": {"label": "lifting or carrying"}, "travel": {"label": "travel"}}
case.set_details(look_for=["travel", "a second job"])


def read():
    return rv.review(asyncio.run(search.snapshot(case)), case.details(), checks)


r = read()
rows = {a["url"]: a for a in r["accounts"]}
# Accounts only, likely first; a record never a row; a namesake stays out until she rejects something on that site
assert "https://biz.test/77" not in rows and "https://chess.test/dvell-1" not in rows, rows
assert r["accounts"][0]["in_person"] and not r["accounts"][-1]["in_person"], r["accounts"]
tube = rows["https://tube.test/velvetforge"]
# Real reasons, in match.score's order, no weights; the score is its own; nothing decided yet
assert tube["why"] and not tube["why"][0] in "+-" and all(not x["text"][:1] in "+-" for x in tube["reasons"]) and tube["decision"] is None
assert r["subject"] == {"name": "Dorian Vell", "meta": "Ocala, FL", "match": max(a["probability"] for a in r["accounts"] if a["in_person"])}
# Login-walled: marked for the Hunt Browser; the others aren't
assert rows["https://www.linkedin.com/in/velvetforge"]["browser"] and not tube["browser"]
# Real checks, what the case already looks for ticked, her own text kept as custom
assert r["checks"] == [{"key": "lifting", "label": "lifting or carrying", "on": False}, {"key": "travel", "label": "travel", "on": True}]
assert r["custom"] == ["a second job"] and r["others"] == []
assert any(l["value"] == "bad_lead_77" for l in r["leads"]), r["leads"]

# She rejects an account: it stays listed, its leads go, and what else the case holds on that site is offered
case.decide("https://chess.test/velvetforge", "not him")
r = read()
rows = {a["url"]: a for a in r["accounts"]}
assert rows["https://chess.test/velvetforge"]["decision"] == "not him" and not rows["https://chess.test/velvetforge"]["in_person"]
assert not any(l["value"] == "bad_lead_77" for l in r["leads"]), r["leads"]
assert [o["url"] for o in r["others"]] == ["https://chess.test/dvell-1"], r["others"]  # never another site's namesake
assert r["others"][0]["decision"] is None
# Picking that one: it's a row now, no longer an offer
case.decide("https://chess.test/dvell-1", "him")
r = read()
assert any(a["url"] == "https://chess.test/dvell-1" and a["in_person"] for a in r["accounts"]) and r["others"] == []
print("ok")
