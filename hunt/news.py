"""Newspaper stories that name the subject, from their hometowns' papers: family history, past places, who they are.

Free and logged out (D2 as revised: an honest UA, never a login, stop at the first refusal; sources/_page.get):
  - Library of Congress Chronicling America (loc.gov JSON): historic US newspapers to 1963, with each page's OCR text.
  - Internet Archive full-text search over its newspaper collections, with the passage that matched.
  - GDELT DOC 2.0: recent news naming them (one request every 5 seconds, as GDELT asks), then the story page itself.
Not read: Google News RSS (its feed terms allow only a personal feed reader) and Patch (its search renders in the
browser, so it isn't a plain logged-out GET).

Matched strictly, since namesakes fill the news: a story counts only when it names the subject in full ("Dorian Vell",
"Dorian M. Vell") near one of their places (the case's places, and the places the accounts and records judged to be
them give, address histories and bios included), a known relative or a known employer, or in a paper from their
hometown. A bare name never counts. A story kept is the headline, date, outlet, URL and the sentence naming them.

Family (D25, C13, A5): relatives the story names ("son of Mr. and Mrs. …") are read with _kin.from_text (graph's
RELATIONS) and reach the tree only through graph's rule (the story matched by name and place); a possible minor is
never named; nobody named is searched or seeded. Background cases (A8): no relatives, and no arrest, health or
political stories at all (report's SCREENED rules).
"""

import asyncio
import re
from urllib.parse import quote

from . import graph, match, people_search, report as reports
from .seed import Finding, Seed
from .sources import _page
from .sources._api import client
from .sources._kin import from_text

NAME = "news"
LOC = "https://www.loc.gov/collections/chronicling-america/"
IA = "https://archive.org/services/search/beta/page_production/"
GDELT = "https://api.gdeltproject.org/api/v2/doc/doc"
ROWS = 20  # results looked at per service and name
READ = 5  # pages read per service and name, for their text
GAP = " … "  # between two passages of one document that aren't next to each other (Internet Archive's highlights)
NEAR = 250  # characters either side of the name a place, relative or employer must sit within
GDELT_GAP = 5.5  # seconds: "Please limit requests to one every 5 seconds"
ARREST = re.compile(r"\b(arrest\w*|charged|booked|jail\w*|indict\w*|convict\w*|sentenced|mugshot|police|sheriff|"
                    r"dui|dwi|felony|misdemeanou?r|probation|hospital\w*|diagnos\w*|rehab\w*|overdose)\b", re.I)


async def collect(case, report: dict, emit=None) -> int:
    """Search the services for each full name seed; keep the stories that match strictly. Returns how many were kept."""
    names = [s for s in case.seeds() if s.kind == "name" and len(s.value.split()) >= 2]
    if not names:
        return 0
    background = case.details().get("kind") == "background"
    places, kin, work = known(case, report)
    have = {r["url"] for r in case.rows("select url from findings where source = ?", NAME)}
    kept = 0
    async with client(60, Accept="application/json, text/html") as c:  # loc.gov can take half a minute
        for seed in names:
            for service, read in (("Chronicling America", _loc), ("Internet Archive", _ia), ("GDELT", _gdelt)):
                stories, checked, note = [], 0, ""
                try:
                    async for story in read(c, seed.value):
                        checked += 1
                        if story["url"] not in have and (attrs := judge(story, seed.value, places, kin, work, background)):
                            have.add(story["url"])
                            stories.append(Finding(NAME, seed, f"Newspaper ({service})", story["url"], attrs))
                except _page.Refused as e:
                    note = f"; stopped: {e}"
                except Exception as e:  # a broken service is a methodology fact, not a crash
                    note = f"; failed: {type(e).__name__}"
                for f in stories:
                    case.add_finding(f)
                kept += len(stories)
                case.add_run(NAME, seed, "found" if stories else "nothing found", len(stories), checked,
                             f"{service}: {checked} stories naming '{seed.value}' looked at, {len(stories)} name them "
                             f"with a place, relative or employer of theirs{note}")
    if emit:
        emit({"type": "log", "message": f"newspapers: {kept} stories name the subject with a place, relative or employer"})
    return kept


def known(case, report: dict) -> tuple[dict[str, str], list[str], list[str]]:
    """({word to look for: the place string it came from}, relatives' names, employers) the case knows."""
    from .search import in_person
    theirs = [c for c in report.get("candidates", []) if in_person(c)]
    texts = [s.value for s in case.seeds() if s.kind in ("location", "address")] + \
        [t for c in theirs if (t := match.place_text(c["attrs"]))] + \
        [str(h) for c in theirs for h in c["attrs"].get("address_history") or [] if h]
    places = {}
    for t in texts:
        parts = [p.strip() for p in people_search.town(str(t)).split(",") if p.strip()]
        if parts and len(parts[0]) >= 3:  # the town ("Ocala"), or the state alone when that's all the case knows
            places.setdefault(parts[0], str(t))
    kin = [r["name"] for c in report.get("candidates", []) if graph._matched(c)
           for r in c["attrs"].get("relatives") or [] if r.get("name") and not r.get("minor")]
    work = [s.value for s in case.seeds() if s.kind == "employer"] + \
        [str(c["attrs"][k]) for c in theirs for k in match.EMPLOYER_KEYS if c["attrs"].get(k)]
    return places, list(dict.fromkeys(kin)), list(dict.fromkeys(w for w in work if len(w) >= 3))


def judge(story: dict, name: str, places: dict, kin: list, work: list, background: bool) -> dict | None:
    """The story's attrs if it names `name` in full with one of their places, relatives or employers (or in a paper
    from their hometown), else None. story: {url, headline, date, outlet, text, towns (the paper's own)}."""
    first, *_, last = name.split()
    full = re.compile(rf"(?i)\b{re.escape(first)}\s+(?:[a-z]\.?\s+|[a-z]+\s+)?{re.escape(last)}\b")
    passages = [" ".join(p.split()) for p in str(story.get("text") or "").split(GAP)]  # passages apart are never "near"
    for text, m in ((t, m) for t in passages for m in full.finditer(t)):
        near = text[max(0, m.start() - NEAR):m.end() + NEAR]
        has = lambda w: re.search(rf"(?i)\b{re.escape(w)}\b", near)
        why = next((f"with {w}" for w in places if has(w)), None) or \
            next((f"in a paper from {w}" for w in places for t in story.get("towns", []) if t.lower() == w.lower()), None) or \
            next((f"with their relative {k}" for k in kin if has(k)), None) or next((f"with {w}" for w in work if has(w)), None)
        if not why:
            continue
        said = next((s for s in re.split(r"(?<=[.!?])\s+", near) if m[0] in s), m[0])
        if background and (ARREST.search(near) or reports.SENSITIVE_CASE.search(near)):
            return None  # A8 and SCREENED: never an arrest, health or political story in a background case
        family = [] if background else from_text(said)  # only the sentence naming them: others in the story aren't kin
        sentence = said[:300]
        for r in family:  # a possible minor is never named, in the sentence either
            if r["minor"] and "[name withheld]" in r["quote"]:
                sentence = r["quote"][:300]
        place = next((p for w, p in places.items() if why.endswith(w)), None)
        return {"headline": story.get("headline"), "date": story.get("date"), "outlet": story.get("outlet"),
                "sentence": sentence, "fullname": m[0], "matched": f"names {m[0]} {why}",
                **({"location": place} if place else {}), **({"relatives": family} if family else {})}
    return None


async def _loc(c, name: str):
    r = await _page.get(c, f"{LOC}?q={quote(chr(34) + name + chr(34))}&fo=json&c={ROWS}&at=results")
    for i, hit in enumerate((r.json().get("results") or []) if r else []):
        text = " ".join(hit.get("description") or [])
        if i < READ and (svc := await _loc_text(c, hit)):
            text = svc
        yield {"url": hit.get("url", "").split("&q=")[0], "headline": hit.get("title"), "date": hit.get("date"),
               "outlet": (hit.get("partof_title") or [""])[0].title(), "text": text,
               "towns": [*(hit.get("location_city") or []), *(hit.get("location_state") or [])]}


async def _loc_text(c, hit: dict) -> str:
    """A page's full OCR text, from the loc.gov text service its JSON names."""
    page = await _page.get(c, hit["id"].replace("http://", "https://").split("&")[0] + "&st=text&fo=json")
    svc = page.json().get("fulltext_service") if page else None
    got = await _page.get(c, svc) if svc else None
    return " ".join(v.get("full_text", "") for v in got.json().values()) if got else ""


async def _ia(c, name: str):
    q = quote(f'"{name}" AND collection:newspapers')
    r = await _page.get(c, f"{IA}?user_query={q}&service_backend=fts&hits_per_page={ROWS}")
    for hit in (r.json()["response"]["body"]["hits"]["hits"] if r else []):
        f = hit.get("fields", {})
        yield {"url": f"https://archive.org/details/{f['identifier']}", "headline": f.get("title"),
               "date": str(f.get("date") or "")[:10], "outlet": f.get("title"),
               "text": GAP.join(hit.get("highlight", {}).get("text", [])).replace("{{{", "").replace("}}}", ""),
               "towns": re.findall(r"[A-Z][a-z]+", f.get("title") or "")}


_gdelt_at = [0.0]


async def _gdelt(c, name: str):
    loop = asyncio.get_running_loop()
    await asyncio.sleep(max(0.0, _gdelt_at[0] + GDELT_GAP - loop.time()))
    _gdelt_at[0] = loop.time()
    r = await _page.get(c, f"{GDELT}?query={quote(chr(34) + name + chr(34))}&mode=artlist&format=json&maxrecords={ROWS}")
    for i, a in enumerate((r.json().get("articles") or []) if r and r.text.lstrip().startswith("{") else []):
        text = a.get("title", "")
        if i < READ:
            try:  # each paper is its own host, paced by _page.get
                page = await _page.get(c, a["url"])
            except Exception:
                page = None  # that paper refused or broke: stopped there, the others still count
            if page:
                body = " ".join(str(d.get("articleBody") or "") for d in _page.ld_json(page.text))
                text = body or " ".join(_page.text(p) for p in re.findall(r"<p\b[^>]*>(.*?)</p>", page.text, re.S))
        yield {"url": a["url"], "headline": a.get("title"), "date": a.get("seendate", "")[:8], "outlet": a.get("domain"),
               "text": f"{a.get('title', '')}. {text}", "towns": []}

