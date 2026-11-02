"""Self-check for the people-search links (hunt/people_search.py; docs/research/legal.md P1–P5). Run:
uv run python test_people_search.py

Offline, fictional seeds. The links are built, never requested; and a static pass over Hunt's code checks that
nothing in it names these hosts except the link builder and Hunt Capture's never-lists (PB3).
"""

import re
from pathlib import Path

from hunt import extension, people_search
from hunt.seed import Seed

HERE = Path(__file__).parent
HOSTS = re.compile(r"whitepages|fastpeoplesearch|truepeoplesearch", re.I)
HOST = re.compile(r"(?:whitepages|fastpeoplesearch|truepeoplesearch)\.com", re.I)  # an address, not the site named in text

# --- the links: Whitepages and FastPeopleSearch only, from the name with the case's place and from each US phone ------
seeds = [Seed("name", "Dorian Quell"), Seed("location", "Tucson, Arizona"), Seed("phone", "+1 (520) 555-0143"),
         Seed("email", "dquell@example.test"), Seed("phone", "+44 20 7946 0958"), Seed("name", "José O'Brien")]
links = people_search.search_links(seeds)
assert {x["site"] for x in links} == {"Whitepages", "FastPeopleSearch"}, links  # never TruePeopleSearch (P2)
assert [x["url"] for x in links] == [
    "https://www.whitepages.com/name/Dorian-Quell/Tucson-AZ", "https://www.fastpeoplesearch.com/name/dorian-quell_tucson-az",
    "https://www.whitepages.com/phone/1-520-555-0143", "https://www.fastpeoplesearch.com/520-555-0143",
    "https://www.whitepages.com/name/Jose-Obrien/Tucson-AZ", "https://www.fastpeoplesearch.com/name/jos-o'brien_tucson-az",
], links  # as each site writes it ("O'Brien" → Obrien, é dropped); no email lookup, no non-US phone
assert people_search.search_links([Seed("username", "dquell_ex")]) == []
assert people_search.search_links([Seed("name", "Dorian Quell")])[0]["url"] == "https://www.whitepages.com/name/Dorian-Quell"
assert people_search.KINDS == ("insurance", "diligence", "journalism") and "background" not in people_search.KINDS
assert people_search.town("12 Sample Rd, Apt 4, Phoenix, Arizona 85001") == "Phoenix, AZ"
assert people_search.town("Washington, DC") == "Washington, DC" and people_search.town("Tucson, Arizona, USA") == "Tucson, AZ"
assert people_search.us_phone("520.555.0143") == "5205550143" and people_search.us_phone("+44 20 7946 0958") is None
assert people_search.host_of("https://m.truepeoplesearch.com/find/x") == "m.truepeoplesearch.com"
assert people_search.host_of("https://notwhitepages.com/") is None and people_search.host_of("https://x.com/whitepages.com") is None

# --- Hunt Capture's never-lists, both sides (PB2) ----------------------------------------------------------------------
for url in ("https://www.whitepages.com/name/Dorian-Quell", "https://fastpeoplesearch.com/520-555-0143",
            "https://m.truepeoplesearch.com/find/person/px1"):
    assert extension.platform(url) in extension.CAPTURE_OFF, url
    assert extension.account_of(url) is None, url
js = (HERE / "extension" / "background.js").read_text()
never = re.search(r"^const NEVER = /(.+)/i;$", js, re.M)
assert never, "background.js has no NEVER list"
never = re.compile(never[1].replace("\\/", "/"), re.I)
for url in ("https://www.whitepages.com/name/x", "https://fastpeoplesearch.com/x", "https://www.truepeoplesearch.com/",
            "https://www.linkedin.com/in/x/"):
    assert never.match(url), url
assert not never.match("https://www.facebook.com/whitepages.com")
# every place the extension records checks NEVER first: a screenshot (view), an archive and a recording
for fn in ("async function archive(", "async function view(", "async function record("):
    body = js[js.index(fn):js.index("\n}\n", js.index(fn))]
    assert "NEVER.test(" in body, fn
assert not HOSTS.search((HERE / "extension" / "manifest.json").read_text())  # no host permission for them

# --- PB3: nothing in Hunt requests these hosts --------------------------------------------------------------------------
# Only the link builder and the two never-lists may name them; anything else (a source, the _api client, an unfurl,
# a preview, an avatar fetch) naming one fails here.
ALLOWED = {"hunt/people_search.py", "hunt/extension.py", "extension/background.js"}
code = [p for p in (*HERE.glob("hunt/**/*.py"), *HERE.glob("hunt/static/*.js"), *HERE.glob("hunt/static/*.html"),
                    *HERE.glob("extension/*.js"), *HERE.glob("extension/*.html"), *HERE.glob("scripts/*.py"))]
named = {str(p.relative_to(HERE)) for p in code if HOST.search(p.read_text(errors="ignore"))}
assert named <= ALLOWED, named - ALLOWED
mod = (HERE / "hunt" / "people_search.py").read_text()
assert not re.search(r"^\s*(?:import|from)\s+(?:httpx|requests|aiohttp|socket|urllib\.request|http\.client|"
                     r"\.sources|\._api|\.browser|\.recheck|\.public)\b", mod, re.M), "people_search.py must not fetch"
assert re.findall(r"^(?:import|from) .*$", mod, re.M) == ["import re", "import unicodedata", "import urllib.parse",
                                                          "from . import geo"], "people_search.py imports changed: check P1"
ext_lines = [line for line in (HERE / "hunt" / "extension.py").read_text().splitlines() if HOST.search(line)]
assert ext_lines and all(re.fullmatch(r'(?:"[\w.]+\.com": "\w+",? ?)+}?', line.strip()) for line in ext_lines), ext_lines  # SITES only
assert [line for line in js.splitlines() if HOSTS.search(line)] == [line for line in js.splitlines() if line.startswith("const NEVER")]
# the links reach the screen once, from GET /person, and nothing else in Hunt calls the builder
users = {str(p.relative_to(HERE)) for p in HERE.glob("hunt/**/*.py") if "search_links(" in p.read_text() and "people_search" in p.read_text()}
assert users == {"hunt/app.py", "hunt/people_search.py"}, users
app_py = (HERE / "hunt" / "app.py").read_text()
assert app_py.count("people_search.search_links(") == 1
get_person = app_py[app_py.index("async def get_person("):app_py.index("\n\n\n", app_py.index("async def get_person("))]
assert "people_search.search_links(" in get_person
# the screen opens them only on her click: buttons into the Hunt Browser, no link, frame, embed or prefetch
app_js = (HERE / "hunt" / "static" / "app.js").read_text()
panel = app_js[app_js.index("const peopleSearch ="):app_js.index("};\n", app_js.index("const peopleSearch ="))]
assert 'data-act="browser-open"' in panel and "href=" not in panel and "<a " not in panel, panel
for f in (*HERE.glob("hunt/static/*.js"), *HERE.glob("hunt/static/*.html")):
    text = f.read_text(errors="ignore")
    assert not re.search(r"<(?:iframe|embed|object|portal)\b|rel=[\"']?(?:prefetch|preconnect|dns-prefetch|prerender)", text, re.I), f

print("ok")
