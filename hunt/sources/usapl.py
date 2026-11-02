"""USA Powerlifting: name → sanctioned meets the person lifted in, each dated, with lifts, total and placing.

USAPL's own results database (usapl.liftingdatabase.com) is public and logged out. Two requests, as its pages make:
  search.php?term=<name>    the box on its Lifters page: matching lifters and their page ids
  lifters-view?id=<id>      a lifter's page: birth year, state, and every meet (date, meet, placing, division,
                            weight class, bodyweight, nine attempts, total, points, drug tested)
OpenPowerlifting (activity.py) copies USAPL too, weeks later; this is the federation's own page.
"""

import html
import re

from ..seed import Finding
from ._api import client, tidy
from ._results import Stopped, adult, dated, get, iso, name_parts, same

NAME = "usapl"
KINDS = {"name"}
SITE = "https://usapl.liftingdatabase.com"
HEALTH = SITE
LIMIT = 10  # lifters per name
ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
CELL = re.compile(r"<td([^>]*)>(.*?)</td>", re.S)


def _text(s: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", s)).split())


def _num(s: str) -> float | None:
    try:
        return float(s)
    except ValueError:
        return None


def _best(cells: list[tuple[str, str]]) -> float | None:
    """The heaviest good attempt of three ('lift_good' in the cell's class)."""
    return max((v for attrs, text in cells if "lift_good" in attrs and (v := _num(_text(text))) is not None), default=None)


def parse(page: str, url: str) -> dict:
    """A lifter page's fields and meets."""
    field = lambda label: _text(m[1]) if (m := re.search(rf"<th>{label}:</th>\s*<td>(.*?)</td>", page, re.S)) else None
    born = field("Birth year")
    table = page[page.find('id="competition_view_results"'):]
    table = table[:table.find("</table>")]
    meets = []
    for row in ROW.findall(table):
        cells = CELL.findall(row)
        if len(cells) < 16 or not (day := iso(_text(cells[0][1]))):
            continue
        if not adult(birth_year=born, on=day):
            continue  # a youth result is never kept
        meet_id = re.search(r"competitions-view\?id=(\d+)", cells[1][1])
        meets.append(tidy({
            "date": day, "meet": _text(cells[1][1]), "place": _text(cells[2][1]).rstrip(".") or None,
            "division": _text(cells[3][1]), "weight_class_kg": _text(cells[4][1]), "bodyweight_kg": _num(_text(cells[5][1])),
            "squat_kg": _best(cells[6:9]), "bench_kg": _best(cells[9:12]), "deadlift_kg": _best(cells[12:15]),
            "total_kg": _num(_text(cells[15][1])), "points": _num(_text(cells[16][1])) if len(cells) > 16 else None,
            "url": f"{SITE}/competitions-view?id={meet_id[1]}" if meet_id else url}))
    name = re.search(r"<h2>\s*Lifter - (.*?)</h2>", page, re.S)
    return {"fullname": _text(name[1]) if name else None, "birth_year": int(born) if born and born.isdigit() else None,
            "location": field("State"), **dated(meets)}


async def search(seed):
    parts = name_parts(seed.value)
    if not parts:
        return [], 0, "needs a first and a last name; not searched"
    first, last = parts
    found, lifters = [], []
    async with client() as c:
        try:
            r = await get(c, f"{SITE}/search.php", {"term": seed.value.strip()})
            groups = r.json() if r else []
            lifters = [i for g in groups if g.get("category") == "Lifter" for i in g.get("items") or []
                       if same(first, last, i.get("label"))]
            for item in lifters[:LIMIT]:
                url = f"{SITE}/{item['url']}"
                if not (page := await get(c, url)):
                    continue
                attrs = parse(page.text, url)
                if not adult(birth_year=attrs.get("birth_year")):
                    continue  # a youth lifter is never kept
                found.append(Finding(NAME, seed, "USA Powerlifting", url, tidy(attrs), body=page.text))
        except Stopped as e:
            return found, 0, f"USA Powerlifting: {e}"
    return found, 1, (f"USA Powerlifting results database (logged out): {len(lifters)} lifters named "
                      f"{first.title()} {last.title()}" + (f", first {LIMIT} read" if len(lifters) > LIMIT else ""))
