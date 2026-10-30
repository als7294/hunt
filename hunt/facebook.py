"""Facebook, within Hunt's rules (docs/facebook.md, docs/research/legal.md). Hunt never logs in, never
runs a Facebook search and never contacts the subject. The investigator browses Facebook under their
own access and saves what they see; this module reads what they saved.

  parse_saved(path)        posts from a saved page: "Save Page As" HTML (with its _files folder), MHTML, .webarchive
  parse_screenshot(path)   one post from a screenshot of it, read with Apple Vision OCR
  parse_public(html)       what a logged-out profile or Page serves to anyone (og: tags, numeric ID, intro)
  parse_profile(path)      parse_public on a saved profile page (its Intro card: lives in, works at, from)
  search_links(seeds)      Facebook search and search-engine links for the investigator to open; Hunt never fetches them
  categories(post)         scan categories pointed to by a post's check-in, feeling/activity tag or life event

A post is {source: "Facebook", url, post_id, posted_at, posted_at_precision, posted_at_text, author,
account_url, fb_id, text, truncated, place, activity, life_event, media: [local paths], reactions,
comments, shares}; anything not found is None. Facebook's markup is obfuscated and changes often, so
everything keys on aria labels, data-* attributes, embedded JSON and URL shapes, never class names,
and a partial post beats none. English, Spanish and French interfaces are understood.
"""

import email
import email.policy
import hashlib
import json
import mimetypes
import plistlib
import re
import tempfile
import unicodedata
import xml.etree.ElementTree as ET
from datetime import UTC, date, datetime, timedelta
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, quote_plus, unquote, urljoin, urlparse

import phonenumbers

from .seed import Seed

FB = "https://www.facebook.com"
USERNAME = re.compile(r"[A-Za-z0-9.]{5,50}")  # Facebook's own rule: letters, digits and dots, 5+ long
MEDIA = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".mp4", ".mov", ".m4v", ".webm"}
MAX_DEPTH = 400  # deeper tags are kept as siblings, so a hostile page can't exhaust the recursion limit

# --- HTML into an ElementTree (stdlib only; Facebook's HTML isn't XML) ---

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
SKIP = {"script", "style", "noscript", "template", "svg", "title"}
BLOCK = {"div", "p", "br", "h1", "h2", "h3", "h4", "h5", "h6", "li", "ul", "ol", "article", "section", "header",
         "footer", "blockquote", "table", "tr", "form", "abbr"}


class _Tree(HTMLParser):
    def __init__(self, html: str):
        super().__init__(convert_charrefs=True)
        self.root, self.comments = ET.Element("document"), []
        self.stack = [self.root]
        self.feed(html)
        self.close()

    def handle_starttag(self, tag, attrs):
        el = ET.SubElement(self.stack[-1], tag, {k: v or "" for k, v in attrs})
        if tag not in VOID and len(self.stack) < MAX_DEPTH:
            self.stack.append(el)

    def handle_startendtag(self, tag, attrs):
        ET.SubElement(self.stack[-1], tag, {k: v or "" for k, v in attrs})

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):  # also closes anything left open inside it
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        top = self.stack[-1]
        if len(top):
            top[-1].tail = (top[-1].tail or "") + data
        else:
            top.text = (top.text or "") + data

    def handle_comment(self, data):
        self.comments.append(data)


def _hidden(e) -> bool:
    style = e.get("style", "").replace(" ", "").lower()
    return e.tag in SKIP or "display:none" in style or "visibility:hidden" in style or e.get("hidden") is not None


def _text(e, skip=frozenset()) -> str:
    """Visible text, one line per block element (and per dir="auto" span, which Facebook lays out as
    its own line); emoji images count as their alt text."""
    parts = []

    def walk(n):
        if _hidden(n) or n in skip:
            return
        block = "\n" if n.tag in BLOCK or n.get("dir") == "auto" else ""
        parts.append(block + (n.text or "").replace("\n", " "))
        if n.tag == "img" and 0 < len(n.get("alt", "")) <= 4:
            parts.append(n.get("alt"))
        for c in n:
            walk(c)
            parts.append((c.tail or "").replace("\n", " "))
        parts.append(block)

    walk(e)
    lines = (re.sub(r"\s+", " ", line).strip() for line in "".join(parts).split("\n"))
    return "\n".join(line for line in lines if line)


def _descendants(e, skip):
    for c in e:
        if c not in skip:
            yield c
            yield from _descendants(c, skip)


def _fold(s: str) -> str:
    """Lower case without accents, same length as the input (so match positions carry over)."""
    return "".join(unicodedata.normalize("NFD", c)[0] for c in s.lower()).replace("’", "'")


# --- URLs ---

NOT_ACCOUNT = {"hashtag", "search", "photo", "photos", "watch", "reel", "reels", "stories", "events", "help", "policies",
               "privacy", "login", "recover", "sharer", "share", "ufi", "ajax", "notifications", "messages", "friends",
               "marketplace", "gaming", "bookmarks", "settings", "groups", "pages", "people", "media", "legal",
               "business", "places", "careers", "public", "home", "watchparty", "fundraisers", "l", "dialog", "plugins"}
TABS = {"about", "photos", "videos", "friends", "reels", "posts", "followers", "following", "map", "likes", "events",
        "reviews", "mentions", "community"}
POST = re.compile(r"/(?:posts|videos|reel|permalink)/|/(?:permalink|story|photo|video)\.php|/photo/?\?|/photos/"
                  r"|/watch/?\?v=|/share/[pvr]/")
PHOTO = re.compile(r"/photo(?:\.php|/)|/photos/")
KEEP = ("story_fbid", "fbid", "id", "v", "set")  # query keys that identify a post; the rest is tracking


def account(url: str | None) -> tuple[str, str | None] | None:
    """(canonical profile URL, numeric ID or None) for a link to a Facebook profile or Page, else None."""
    u = urlparse(url or "")
    if not (u.hostname or "").endswith("facebook.com"):
        return None
    parts = [p for p in u.path.split("/") if p]
    if parts == ["profile.php"]:
        uid = parse_qs(u.query).get("id", [""])[0]
        return (f"{FB}/profile.php?id={uid}", uid) if uid.isdigit() else None
    if len(parts) >= 3 and parts[0] in ("people", "pages") and parts[2].isdigit():
        return f"{FB}/{parts[0]}/{parts[1]}/{parts[2]}", parts[2]
    if len(parts) >= 4 and parts[0] == "groups" and parts[2] == "user" and parts[3].isdigit():
        return f"{FB}/profile.php?id={parts[3]}", parts[3]
    if (len(parts) == 1 or len(parts) == 2 and parts[1] in TABS) and not parts[0].endswith(".php") \
            and parts[0].lower() not in NOT_ACCOUNT:
        return f"{FB}/{parts[0]}", parts[0] if parts[0].isdigit() else None
    return None


def _canon(url: str) -> str:
    u = urlparse(url)
    if not (u.hostname or "").endswith("facebook.com"):
        return url
    q = parse_qs(u.query)
    query = "&".join(f"{k}={q[k][0]}" for k in KEEP if k in q)
    return FB + u.path + (f"?{query}" if query else "")


def _is_post(url: str | None) -> bool:
    u = urlparse(url or "")
    return (u.hostname or "").endswith("facebook.com") and bool(POST.search(u.path + "?" + u.query))


def _post_id(url: str | None) -> str | None:
    u = urlparse(url or "")
    q = parse_qs(u.query)
    for k in ("story_fbid", "fbid", "v"):
        if k in q:
            return q[k][0]
    m = re.search(r"/(?:posts|videos|reel|permalink|photos/[^/]+)/([\w-]+)", u.path)
    return m[1] if m else None


def _owner(url: str | None):
    """The profile in a post URL's first segment (facebook.com/dorian.vell/posts/...), if any."""
    parts = [p for p in urlparse(url or "").path.split("/") if p]
    return account(f"{FB}/{parts[0]}") if len(parts) > 1 else None


# --- dates ---

MONTHS = {}
for _i, _names in enumerate(["january jan enero ene janvier janv", "february feb febrero fevrier fevr fev",
                             "march mar marzo mars", "april apr abril abr avril avr", "may mayo mai",
                             "june jun junio juin", "july jul julio juillet juil", "august aug agosto ago aout",
                             "september sep sept septiembre setiembre septembre", "october oct octubre octobre",
                             "november nov noviembre novembre", "december dec diciembre dic decembre"], 1):
    MONTHS |= dict.fromkeys(_names.split(), _i)
WEEKDAYS = {}
for _i, _names in enumerate(["monday mon lunes lundi", "tuesday tue martes mardi", "wednesday wed miercoles mercredi",
                             "thursday thu jueves jeudi", "friday fri viernes vendredi", "saturday sat sabado samedi",
                             "sunday sun domingo dimanche"]):
    WEEKDAYS |= dict.fromkeys(_names.split(), _i)
UNITS = {}  # relative-time unit -> (seconds, precision)
for _names, _secs, _prec in [("s sec secs second seconds seg segundo segundos seconde secondes", 1, "minute"),
                             ("m min mins minute minutes minuto minutos mn", 60, "minute"),
                             ("h hr hrs hour hours hora horas heure heures", 3600, "hour"),
                             ("d day days dia dias j jour jours", 86400, "day"),
                             ("w wk wks week weeks sem semana semanas semaine semaines", 7 * 86400, "week"),
                             ("mo mos month months mes meses mois", 30 * 86400, "month"),
                             ("y yr yrs year years a ano anos an ans", 365 * 86400, "year")]:
    UNITS |= dict.fromkeys(_names.split(), (_secs, _prec))
_alt = lambda names: "|".join(sorted(map(re.escape, names), key=len, reverse=True))
M, W = _alt(MONTHS), _alt(WEEKDAYS)
TIME = r"(?:,? (?:at|a las|a la|a) (\d{1,2})[:h.](\d{2})(?: ?([ap])\.? ?m\.?)?)?"
DMY = re.compile(rf"(\d{{1,2}})(?: de)? ({M})\.?(?:,?(?: de)? (\d{{4}}))?{TIME}")
MDY = re.compile(rf"({M})\.? (\d{{1,2}})(?:,? (\d{{4}}))?{TIME}")
MY = re.compile(rf"({M})(?: de)? (\d{{4}})")
NEAR = re.compile(rf"(yesterday|today|ayer|hoy|hier|aujourd'hui|{W}){TIME}")
REL = re.compile(rf"(?:hace |il y a )?(\d+) ?({_alt(UNITS)})\.?(?: ago)?")
JUST_NOW = {"just now", "now", "justo ahora", "ahora", "a l'instant", "maintenant"}
RANK = {"second": 0, "minute": 1, "hour": 2, "day": 3, "week": 4, "month": 5, "year": 6, None: 9}


def parse_date(text: str, ref: datetime | None = None) -> tuple[str, str] | None:
    """Facebook's date text -> (ISO date or date-time, precision) or None. Precision is "minute", "hour",
    "day", "week", "month" or "year" (a relative "3d" is "day": it only says which day). Relative forms
    ("3d", "Yesterday at 21:15", "Tuesday at 14:05") count back from `ref` (default now), and a date
    without a year is the latest one not after `ref`. Times are as Facebook displayed them, in the
    saving browser's time zone, so they carry no offset."""
    ref = ref or datetime.now()
    s = re.sub(r"\s+", " ", _fold(text)).strip(" ·•.,")
    s = re.sub(rf"^(?:{W}),? (?=\d|{M})", "", s)  # tooltip form: "Friday, 12 April 2024 at 09:41"
    if s in JUST_NOW:
        return _iso(ref, "minute"), "minute"
    if m := REL.fullmatch(s):
        secs, prec = UNITS[m[2]]
        return _iso(ref - timedelta(seconds=int(m[1]) * secs), prec), prec
    try:
        if m := NEAR.fullmatch(s):
            word = m[1]
            back = (1 if word in ("yesterday", "ayer", "hier") else 0 if word in ("today", "hoy", "aujourd'hui")
                    else (ref.weekday() - WEEKDAYS[word]) % 7 or 7)
            return _at(ref.date() - timedelta(days=back), *m.groups()[1:])
        if m := DMY.fullmatch(s) or MDY.fullmatch(s):
            day, month = (m[1], m[2]) if m.re is DMY else (m[2], m[1])
            when = date(int(m[3] or ref.year), MONTHS[month], int(day))
            if not m[3] and when > ref.date() + timedelta(days=1):
                when = when.replace(year=ref.year - 1)
            return _at(when, *m.groups()[3:])
        if m := MY.fullmatch(s):
            return date(int(m[2]), MONTHS[m[1]], 1).isoformat(), "month"
    except ValueError:  # 30 February and the like
        return None
    return None


def _at(day: date, hour, minute, ampm):
    if hour is None:
        return day.isoformat(), "day"
    h = int(hour) % 12 + (12 if ampm == "p" else 0) if ampm else int(hour)
    return f"{day.isoformat()}T{h:02d}:{int(minute):02d}", "minute"


def _iso(when: datetime, prec: str) -> str:
    return when.strftime("%Y-%m-%dT%H:%M") if prec in ("minute", "hour") else when.date().isoformat()


def _unix(t) -> str:
    return datetime.fromtimestamp(int(t), UTC).isoformat()


# --- what a post header, a body line or a count says (folded text, English / Spanish / French) ---

LIFE = re.compile(
    r"(?:started (?:a )?new job|started working|new job at|left (?:a |my |his |her )?job|retired from|moved to|"
    r"got engaged|got married|bought a (?:new )?(?:home|house|car|truck)|got a new (?:car|truck)|graduated from|"
    r"broke (?:my|his|her|their|a) \w+|had surgery|ran (?:a|the|his|her) (?:half )?marathon|travell?ed to|"
    r"empezo a trabajar|comenzo a trabajar|nuevo (?:trabajo|empleo)|se mudo a|se comprometio|se caso|"
    r"compro (?:una casa|un coche|un auto|un carro)|se graduo|a commence (?:a travailler|un nouveau travail)|"
    r"nouvel emploi|nouveau travail|a demenage|a emmenage|s'est installee? a|s'est fiancee?|s'est mariee?|"
    r"a achete une? (?:maison|voiture)|est diplomee? de)\b")
# WITH and AT run on lower-cased, not folded, text: folding turns French "à" into English "a"
WITH = re.compile(r"(?:\b(?:is|está|esta|est) )?\b(?:with|con|avec) .+?(?= (?:at|in|en|à|au) |$)")
AT = re.compile(r"(?:^| )(?:(?:is|está|esta|est) )?(?:at|in|en|à|au) (.+)$")
ACTIVITY = re.compile(
    r"(?:feeling|celebrating|watching|eating|drinking|travell?ing|listening|reading|playing|thinking|looking for|"
    r"attending|getting|making|meeting|remembering|supporting|exercising|going|working|se siente|sintiendose|"
    r"celebrando|viendo|comiendo|bebiendo|tomando|viajando|escuchando|leyendo|jugando|pensando|buscando|asistiendo|"
    r"haciendo|recordando|apoyando|trabajando|entrenando|se sent|fete|celebre|regarde|mange|boit|voyage|ecoute|"
    r"lit|joue|pense a|cherche|assiste|participe|fait|se souvient|soutient|travaille|s'entraine)\b")
CONNECT = re.compile(r" (?=(?:is|esta|est|se|updated|shared|added|was|actualizo|compartio|agrego|a partage|a mis|"
                     r"a ajoute)\b)| ?[—–] ")
UI = re.compile(  # lines of Facebook chrome, never post text
    r"like|comment|share|send|reply|follow|following|join|facebook|search|home|see translation|see original|"
    r"write a (?:public )?comment.*|most relevant|newest|all comments|top comments|view (?:\d+ )?more comments?|"
    r"all reactions:?|see more|see less|edited|public|friends|sponsored|"
    r"me gusta|comentar|compartir|enviar|responder|seguir|ver traduccion|escribe un comentario.*|mas relevantes|"
    r"todas las reacciones:?|ver mas|j'aime|commenter|partager|envoyer|repondre|suivre|voir la traduction|"
    r"(?:ecrivez|ecrire) un commentaire.*|les plus pertinents|toutes les reactions ?:?|voir plus|afficher la suite|"
    r"[^\w]{0,3}|\d[\d.,]*\s?[km]?|\W*\w\W*")
SEE_MORE = re.compile(r"(?:…|\.\.\.)\s*(?:more|mas|plus)$|(?:…|\.\.\.)?\s*(?:see more|ver mas|voir plus|afficher la suite)$")
COMMENT_LABEL = re.compile(r"^(?:comment|reply|comentario|respuesta|commentaire|reponse)\b")
NUM = r"(\d(?:[\d.,]|[\xa0\N{NARROW NO-BREAK SPACE}])*\d(?: ?[km]\b)?|\d(?: ?[km]\b)?)"  # 1,234 · 1.2K · French 1 234 (no-break space; a plain space would join two counts)
COUNTS = {
    "reactions": [re.compile(rf"(?:all reactions|todas las reacciones|toutes les reactions)\s*:?\s*{NUM}"),
                  re.compile(rf"(?:like|me gusta|j'aime)\s*:\s*{NUM} (?:people|personas|personnes)"),
                  re.compile(rf"{NUM} (?:reactions?|reacciones|reactions|j'aime|me gusta|likes?)(?![^\W\d_])")],
    "comments": [re.compile(rf"{NUM} (?:comments?|comentarios?|commentaires?)(?![^\W\d_])")],
    "shares": [re.compile(rf"{NUM} (?:shares?|veces compartido|vez compartido|compartid[oa]s?|partages?)(?![^\W\d_])")],
}


def _header(rest: str) -> tuple[str | None, str | None, str | None]:
    """(activity, place, life event) from the words after the author's name in a post's header line:
    "is feeling adventurous at Cedar Ridge Trailhead", "— at Port Alder Marina", "está en Gimnasio Hierro",
    "se sent motivé à Salle de sport Fer Rouge", "started a new job at Harbor Freight Movers"."""
    rest = re.sub(r"^[\s—–-]+|[\s.。]+$", "", rest)
    if m := LIFE.search(_fold(rest)):
        return None, None, rest[m.start():]
    if m := WITH.search(rest.lower()):  # "is with Mara Quill and 2 others"
        rest = rest[:m.start()] + rest[m.end():]
    place = None
    if m := AT.search(rest.lower()):
        place, rest = rest[m.start(1):].strip() or None, rest[:m.start()]
    rest = re.sub(r"^\s*(?:is|está|esta|est)\s+", "", rest, flags=re.I).strip()
    return (rest if ACTIVITY.match(_fold(rest)) else None), place, None


def _num(s: str) -> int:
    s = re.sub(r"\s", "", s.lower())
    if s[-1] in "km":
        return round(float(s[:-1].replace(",", ".")) * (1000 if s[-1] == "k" else 1_000_000))
    return int(re.sub(r"\D", "", s))


def _counts(text: str) -> dict:
    folded, out = _fold(text), {}
    for key, rxs in COUNTS.items():
        m = next((m for rx in rxs if (m := rx.search(folded))), None)
        out[key] = _num(m[1]) if m else None
    return out


def _post(**fields) -> dict:
    blank = dict.fromkeys(["url", "post_id", "posted_at", "posted_at_precision", "posted_at_text", "author",
                           "account_url", "fb_id", "text", "place", "activity", "life_event", "reactions", "comments",
                           "shares"])
    return {"source": "Facebook"} | blank | {"truncated": False, "media": []} | fields


# --- saved pages ---

def parse_saved(path, saved_at: datetime | None = None, media_dir=None) -> list[dict]:
    """Posts from a page the investigator saved while browsing Facebook: "Save Page As, complete" (the
    .html and its _files folder), single-file MHTML (.mhtml/.mht), Safari .webarchive, or plain HTML.
    `saved_at` anchors relative times ("3d"); by default the MHTML Date header, else the file's
    modification time. Pictures inside an MHTML or .webarchive are written to `media_dir` (a new
    temporary folder by default) so every media entry is a local file."""
    page = _load(Path(path), saved_at, media_dir)
    return _posts(**page)


def parse_profile(path) -> dict:
    """parse_public() on a saved profile or Page (any format parse_saved reads)."""
    page = _load(Path(path), None, None)
    return parse_public(page["html"], page["page_url"])


def _load(path: Path, saved_at, media_dir) -> dict:
    page = {"html": "", "page_url": None, "resources": {}, "base_dir": path.parent}
    ext, data = path.suffix.lower(), path.read_bytes()
    if ext in (".mhtml", ".mht"):
        msg = email.message_from_bytes(data, policy=email.policy.default)
        page["page_url"] = msg.get("Snapshot-Content-Location")
        for part in msg.walk():
            ctype, loc = part.get_content_type(), part.get("Content-Location") or ""
            if ctype == "text/html" and not page["html"]:  # Chrome omits the charset; the page itself is UTF-8
                page["html"] = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "replace")
                page["page_url"] = page["page_url"] or loc
            elif ctype.startswith(("image/", "video/")) and loc:
                media_dir = _store(page, loc, part.get_payload(decode=True), ctype, media_dir)
        if not saved_at and msg.get("Date"):
            saved_at = parsedate_to_datetime(msg["Date"]).astimezone().replace(tzinfo=None)
    elif ext == ".webarchive":
        archive = plistlib.loads(data)
        main = archive["WebMainResource"]
        page["html"] = main["WebResourceData"].decode(main.get("WebResourceTextEncodingName") or "utf-8", "replace")
        page["page_url"] = main.get("WebResourceURL")
        for res in archive.get("WebSubresources", []):
            ctype = res.get("WebResourceMIMEType", "")
            if ctype.startswith(("image/", "video/")):
                media_dir = _store(page, res["WebResourceURL"], res["WebResourceData"], ctype, media_dir)
    else:
        page["html"] = data.decode("utf-8", "replace")
    page["ref"] = saved_at or datetime.fromtimestamp(path.stat().st_mtime)
    return page


def _store(page, url, data, ctype, media_dir):
    media_dir = Path(media_dir or tempfile.mkdtemp(prefix="hunt-facebook-"))
    media_dir.mkdir(parents=True, exist_ok=True)
    ext = {"image/jpeg": ".jpg"}.get(ctype) or mimetypes.guess_extension(ctype) or ".bin"
    out = media_dir / (hashlib.sha256(url.encode()).hexdigest()[:20] + ext)
    out.write_bytes(data)
    page["resources"][url] = str(out)
    return media_dir


def _posts(html, page_url, resources, base_dir, ref) -> list[dict]:
    tree = _Tree(html)
    root, meta = tree.root, _meta(tree.root)
    saved_from = next((m[1] for c in tree.comments if (m := re.search(r"saved from url=\(\d+\)(\S+)", c))), None)
    page_url = page_url or saved_from or meta.get("og:url")
    ctx = {"base": page_url or FB + "/", "resources": resources, "dir": base_dir, "ref": ref,
           "parents": {c: p for p in root.iter() for c in p}}
    posts = [p for el in _containers(root, ctx["parents"]) if (p := _one(el, ctx))]
    _merge(posts, _stories(root))
    if not posts and (url := meta.get("og:url")) and _is_post(url) and meta.get("og:description"):
        # a single public post saved logged-out: only its link-preview tags are certain
        url = _canon(url)
        image = _local(meta.get("og:image"), ctx)
        owner = _owner(url)
        uid = re.search(r"fb://(?:profile|page)/(\d+)", meta.get("al:android:url", ""))
        posts.append(_post(url=url, post_id=_post_id(url), author=meta.get("og:title"), text=meta["og:description"],
                           account_url=owner and owner[0], fb_id=owner and owner[1] or uid and uid[1],
                           media=[image] if image else [],
                           **_when(list(root.iter()), None, ctx)))
    page_owner = account(page_url)
    for p in posts:
        if not p["account_url"] and (owner := _owner(p["url"]) or page_owner):
            p["account_url"], p["fb_id"] = owner
    known = {p["account_url"]: p["fb_id"] for p in posts if p["fb_id"]}
    for p in posts:
        p["fb_id"] = p["fb_id"] or known.get(p["account_url"])
    return posts


def _meta(root) -> dict:
    out = {}
    for m in root.iter("meta"):
        key = m.get("property") or m.get("name")
        if key and "content" in m.attrib:
            out.setdefault(key, m.get("content"))
    return out


def _containers(root, parents) -> list:
    """Outermost post elements: feed units (aria-posinset), role=article, <article>, mobile data-ft stories."""
    found = [e for e in root.iter() if not COMMENT_LABEL.match(_fold(e.get("aria-label", ""))) and (
        e.get("aria-posinset") is not None or e.get("role") == "article" or e.tag == "article"
        or "top_level_post_id" in e.get("data-ft", "") or e.get("data-testid") == "post_container")]
    inside = set(found)

    def nested(e):
        while (e := parents.get(e)) is not None:
            if e in inside:
                return True
        return False

    return [e for e in found if not nested(e)]


def _one(el, ctx) -> dict | None:
    # comments are articles inside the post; never read their text, dates or pictures as the post's
    skip = {d for d in el.iter() if d is not el and (d.get("role") == "article"
                                                    or COMMENT_LABEL.match(_fold(d.get("aria-label", ""))))}
    nodes = list(_descendants(el, skip))
    p = _post()
    # `is not None` throughout: an ElementTree element with no children is falsy
    header = None
    for tags in (("h2", "h3", "h4", "h5", "h6"), ("header",), ("strong",)):  # <header> may hold the date line too
        header = next((n for n in nodes if n.tag in tags and _author(n, ctx) is not None), None)
        if header is not None:
            break
    if header is not None:
        link = _author(header, ctx)
        p["author"] = _text(link).replace("\n", " ")
        p["account_url"], p["fb_id"] = account(_abs(link.get("href"), ctx))
        if not p["fb_id"] and (m := re.search(r"[?&]id=(\d+)", link.get("data-hovercard", ""))):
            p["fb_id"] = m[1]
        if header.tag == "strong":
            header = ctx["parents"].get(header, header)
        line = _text(header).replace("\n", " ")
        rest = line[len(p["author"]):] if line.startswith(p["author"]) else line.replace(p["author"], "", 1)
        p["activity"], p["place"], p["life_event"] = _header(rest)
    ft = _data_ft(el)
    p["fb_id"] = p["fb_id"] or ft.get("content_owner_id_new")

    stamps = {n: u for n in nodes if n.tag == "a" and _is_post(u := _abs(n.get("href"), ctx))}  # timestamp, photo links
    links = list(stamps.values())
    url = next((u for u in links if not PHOTO.search(urlparse(u).path)), links[0] if links else None)
    if url:
        p["url"] = _canon(url)
        p["post_id"] = _post_id(url)
    p["post_id"] = p["post_id"] or ft.get("top_level_post_id")

    msg = next((n for n in nodes if "message" in (n.get("data-ad-preview"), n.get("data-ad-comet-preview"))
                or n.get("data-testid") == "post_message" or "userContent" in n.get("class", "").split()
                or '"tn":"*s"' in n.get("data-ft", "").replace(" ", "")), None)
    hset = set(header.iter()) if header is not None else set()
    others = _text(el, skip | hset | set(stamps) | ({msg} if msg is not None else set())).split("\n")
    if msg is not None:
        text = _text(msg, skip)
    else:  # no message element: everything that isn't chrome, a date, a count or a life event
        text = "\n".join(line for line in others if not UI.fullmatch(_fold(line)) and not parse_date(line, ctx["ref"])
                         and not any(v for v in _counts(line).values()) and not LIFE.match(_fold(line))
                         and line != p["author"])
    folded = _fold(text)
    if m := SEE_MORE.search(folded):
        text, p["truncated"] = text[:m.start()].rstrip(), True
    p["truncated"] = p["truncated"] or any(SEE_MORE.fullmatch(_fold(line)) for line in others)
    p["text"] = text or None
    p["life_event"] = p["life_event"] or next((line for line in others if len(line) < 120
                                               and LIFE.match(_fold(line))), None)

    p |= _when(nodes, ft, ctx, prefer=[n for n in nodes if n.tag == "a" and _abs(n.get("href"), ctx) == url])
    media = []
    for n in nodes:
        if n.tag == "img" and n not in hset and _photo(n):
            media.append(_local(n.get("src"), ctx))
        elif n.tag == "video":
            media += [_local(s, ctx) for s in (n.get("src"), *(c.get("src") for c in n.iter("source")), n.get("poster"))]
    p["media"] = list(dict.fromkeys(m for m in media if m))
    p["audience"] = _audience(nodes, p["url"])
    labels = "\n".join(n.get("aria-label") for n in nodes if n.get("aria-label"))
    p |= _counts("\n".join(others) + "\n" + labels)
    return p if p["text"] or p["url"] or p["media"] or p["life_event"] else None


AUDIENCES = {"public": "Public", "publico": "Public", "friends of friends": "Friends of friends",
             "amigos de amigos": "Friends of friends", "amis d'amis": "Friends of friends", "friends": "Friends",
             "amigos": "Friends", "amis": "Friends", "custom": "Custom", "personalizado": "Custom",
             "personnalise": "Custom", "only me": "Only me", "solo yo": "Only me", "moi uniquement": "Only me"}
AUDIENCE = re.compile(r"(?:(?:shared with|compartido con|partage avec)\s*:?\s*)?(" + "|".join(
    sorted(map(re.escape, AUDIENCES), key=len, reverse=True)) + r")\.?")


def _audience(nodes, url) -> str | None:
    """The audience Facebook shows on a post (its globe or people icon's label), or "Group: <name>" in a group."""
    if m := re.search(r"/groups/([^/?#]+)", url or ""):
        return f"Group: {m[1]}"
    for n in nodes:
        label = _fold(n.get("aria-label") or n.get("title") or "").strip()
        if label and (m := AUDIENCE.fullmatch(label)):
            return AUDIENCES[m[1]]
    return None


def _author(header, ctx):
    return next((a for a in header.iter("a") if account(_abs(a.get("href"), ctx))), None)


def _abs(href, ctx) -> str | None:
    return urljoin(ctx["base"], href) if href else None


def _data_ft(el) -> dict:
    """The mobile site's data-ft JSON, flattened to the keys Hunt uses."""
    try:
        ft = json.loads(el.get("data-ft") or "{}")
    except ValueError:
        return {}
    out = {k: str(ft[k]) for k in ("top_level_post_id", "content_owner_id_new") if ft.get(k)}
    if (t := next((d["publish_time"] for d in _dicts(ft) if isinstance(d.get("publish_time"), int)), None)) is not None:
        out["publish_time"] = t
    return out


def _when(nodes, ft, ctx, prefer=()) -> dict:
    """The most precise post time in reach: data-utime, mobile publish_time, then date text on the post link,
    <abbr>, tooltips and short spans (comments already excluded)."""
    for n in nodes:
        if n.get("data-utime", "").isdigit():
            return {"posted_at": _unix(n.get("data-utime")), "posted_at_precision": "second",
                    "posted_at_text": n.get("title") or _text(n) or None}
    if ft and "publish_time" in ft:
        return {"posted_at": _unix(ft["publish_time"]), "posted_at_precision": "second", "posted_at_text": None}
    best = {"posted_at": None, "posted_at_precision": None, "posted_at_text": None}
    for n in [*prefer, *(n for n in nodes if n.tag in ("abbr", "time")), *(n for n in nodes if n.tag in ("a", "span"))]:
        for s in (n.get("aria-label"), n.get("title"), _text(n).replace("\n", " ")):
            if s and len(s) <= 60 and (d := parse_date(s, ctx["ref"])) and RANK[d[1]] < RANK[best["posted_at_precision"]]:
                best = {"posted_at": d[0], "posted_at_precision": d[1], "posted_at_text": s}
    return best


def _photo(img) -> bool:
    """A post picture, not an emoji, reaction icon or avatar."""
    src = img.get("src", "")
    size = [int(v) for v in (img.get("width"), img.get("height")) if v and v.isdigit()]
    return not (any(v < 64 for v in size) or "emoji" in src or "rsrc.php" in src or "/images/" in src)


def _local(src, ctx) -> str | None:
    """A media reference -> a local file: the saved _files folder, or a part of the MHTML / .webarchive."""
    if not src or src.startswith(("data:", "blob:")):
        return None
    if found := ctx["resources"].get(src) or ctx["resources"].get(urljoin(ctx["base"], src)):
        return found
    if "://" in src or src.startswith("//"):
        return None  # never saved; Hunt doesn't fetch it
    # only the page's own folder: a crafted page must not pull other files on this computer into evidence
    folder = Path(ctx["dir"]).resolve()
    path = (folder / unquote(src.split("?")[0])).resolve()
    return str(path) if path.is_relative_to(folder) and path.suffix.lower() in MEDIA and path.is_file() else None


def _dicts(data):
    stack = [data]
    while stack:
        o = stack.pop()
        if isinstance(o, dict):
            yield o
            stack.extend(o.values())
        elif isinstance(o, list):
            stack.extend(o)


def _stories(root) -> list[dict]:
    """Posts in the page's embedded JSON (Facebook's Relay payloads in <script type="application/json">):
    any object with a post_id, with the nearest creation_time, post URL, message text and actor inside it."""
    stories = {}
    for script in root.iter("script"):
        raw = (script.text or "").strip()
        if not raw.startswith(("{", "[")):
            continue
        try:
            data = json.loads(raw)
        except (ValueError, RecursionError):
            continue
        for d in _dicts(data):
            if not (isinstance(d.get("post_id"), str) and d["post_id"]):
                continue
            s = stories.setdefault(d["post_id"], {"post_id": d["post_id"]})
            queue = [d]
            while queue:  # breadth first, so the story's own fields win over a shared post's
                o = queue.pop(0)
                if isinstance(o, list):
                    queue.extend(o)
                    continue
                if not isinstance(o, dict):
                    continue
                if isinstance(o.get("creation_time"), int):
                    s.setdefault("creation_time", o["creation_time"])
                if _is_post(o.get("url")):
                    s.setdefault("url", _canon(o["url"]))
                if isinstance(o.get("message"), dict) and isinstance(o["message"].get("text"), str):
                    s.setdefault("text", o["message"]["text"])
                if isinstance(o.get("actors"), list) and o["actors"] and isinstance(o["actors"][0], dict):
                    s.setdefault("actor", o["actors"][0])
                queue.extend(v for v in o.values() if isinstance(v, (dict, list)))
    return list(stories.values())


def _merge(posts, stories):
    """Fill what the page's DOM hides (exact times, text behind "See more", IDs) from its embedded JSON;
    stories the DOM never rendered become posts of their own."""
    norm = lambda t: re.sub(r"\W+", "", (t or "").lower())[:60]
    for s in stories:
        p = next((p for p in posts if s["post_id"] == p["post_id"] or s.get("url") and s["url"] == p["url"]
                  or s.get("text") and norm(s["text"]) == norm(p["text"])), None)
        if p is None:
            if not (s.get("text") or s.get("url")):
                continue
            p = _post()
            posts.append(p)
        actor = s.get("actor") or {}
        acct = account(actor.get("url"))
        p["post_id"] = p["post_id"] or s["post_id"]
        p["url"] = p["url"] or s.get("url")
        p["author"] = p["author"] or actor.get("name")
        p["account_url"] = p["account_url"] or (acct and acct[0])
        p["fb_id"] = p["fb_id"] or actor.get("id")
        if "creation_time" in s and RANK[p["posted_at_precision"]] > 0:
            p["posted_at"], p["posted_at_precision"] = _unix(s["creation_time"]), "second"
        if s.get("text") and (not p["text"] or p["truncated"] and len(s["text"]) > len(p["text"])):
            p["text"], p["truncated"] = s["text"], False


# --- screenshots ---

def parse_screenshot(path, lines: list[str] | None = None, taken: datetime | None = None) -> dict:
    """One post from a screenshot of it. `lines` defaults to Apple Vision OCR (hunt.photo.read_text,
    macOS). Relative times ("3d", "Yesterday at 21:15") count back from `taken`: by default the time in
    a macOS screenshot's file name, else the file's EXIF time, else its modification time."""
    if lines is None:
        from . import photo
        lines = photo.read_text(str(path))
    ref = taken or _shot_time(Path(path))
    lines = [line.strip() for line in lines if line.strip()]
    p = _post(media=[str(path)])
    found = next(((i, d) for i, line in enumerate(lines) if not UI.fullmatch(_fold(line))
                  and (d := _shot_date(line, ref))), None)
    if found:
        i, (p["posted_at"], p["posted_at_precision"], p["posted_at_text"]) = found
        above = [line for line in lines[:i] if not UI.fullmatch(_fold(line))][-2:]
        header = " ".join(above) if len(above) == 2 and CONNECT.search(_fold(above[0])) else (above[-1] if above else "")
        start = i + 1
    else:  # no date read (OCR can miss the faint date line): the first header-like or name-like line
        j = next((j for j, line in enumerate(lines) if not UI.fullmatch(_fold(line)) and (CONNECT.search(_fold(line))
                  or re.fullmatch(r"[^\W\d_]+(?:[ .'-]+[^\W\d_]+)+\.?", line))), None)
        header, start = (lines[j], j + 1) if j is not None else ("", 0)
    header = re.sub(r"\s*(?:[·•]\s*)?(?:follow|seguir|suivre)$", "", header, flags=re.I)
    if m := CONNECT.search(_fold(header)):
        p["author"], rest = header[:m.start()].strip(" ✓"), header[m.start():]
        p["activity"], p["place"], p["life_event"] = _header(rest)
    else:
        p["author"] = header.strip(" ✓") or None
    body, tail = [], []
    for k, line in enumerate(lines[start:]):
        folded = _fold(line)
        if SEE_MORE.fullmatch(folded.strip()):
            p["truncated"] = True
        elif UI.fullmatch(folded) or any(v for v in _counts(line).values()):
            tail = lines[start + k:]
            break
        else:
            body.append(line)
    text = " ".join(body)  # OCR can't tell a wrapped line from a new paragraph
    if m := SEE_MORE.search(_fold(text)):
        text, p["truncated"] = text[:m.start()].rstrip(), True
    p["text"] = text or None
    p["life_event"] = p["life_event"] or next((line for line in body if LIFE.match(_fold(line))), None)
    p |= _counts("\n".join(tail))
    if p["reactions"] is None and (bare := next((x for x in tail if re.fullmatch(NUM, _fold(x))), None)):
        p["reactions"] = _num(bare)  # the reaction icons' count sits alone at the left of the counts row
    return p


def _shot_date(line, ref):
    """Facebook's date line under the author, read by OCR: "12 April at 09:41 · 🌐" comes out as
    "12 April at 09:41 • ©" or similar, so try the part before the separator."""
    for cand in (re.split(r"\s*[·•‧∙・]\s*", line)[0], re.sub(r"\s+\W{1,2}$", "", line), line):
        if cand and (d := parse_date(cand, ref)):
            return d[0], d[1], cand
    return None


def _shot_time(path: Path) -> datetime:
    m = re.search(r"(\d{4})-(\d\d)-(\d\d)\D{1,12}?(\d{1,2})[.:](\d\d)[.:](\d\d)(?:\s*([AaPp])\.?\s?[Mm])?", path.name)
    if m:
        h = int(m[4]) % 12 + (12 if m[7].lower() == "p" else 0) if m[7] else int(m[4])
        return datetime(int(m[1]), int(m[2]), int(m[3]), h, int(m[5]), int(m[6]))
    if not path.is_file():
        return datetime.now()
    try:
        from PIL import Image
        exif = Image.open(path).getexif()
        raw = exif.get_ifd(0x8769).get(36867) or exif.get(306)  # DateTimeOriginal, DateTime
        if raw:
            return datetime.strptime(str(raw).strip(), "%Y:%m:%d %H:%M:%S")
    except (OSError, ValueError):
        pass
    return datetime.fromtimestamp(path.stat().st_mtime)


# --- logged-out public profile ---

INTRO = {  # folded line or description segment -> attr
    "location": re.compile(r"^(?:lives in|vive en|habite a) (.+)"),
    "hometown": re.compile(r"^(?:from|es de|originaire de) (.+)"),
    "works_at": re.compile(r"^(?:works at|worked at|trabaja en|trabajo en|travaille (?:chez|a)|a travaille chez) (.+)"),
    "studied_at": re.compile(r"^(?:studies at|studied at|went to|estudia en|estudio en|etudie a|a etudie a) (.+)"),
}
LOGIN_TITLE = re.compile(r"^(?:log ?in(?:to| to)? facebook|facebook ?[-–] ?(?:log in or sign up|inicia sesion o "
                         r"registrate|connexion ou inscription)|inicia sesion en facebook|se connecter a facebook)")
REFUSED = re.compile(r"sorry, something went wrong|lo sentimos, se produjo un error|desole, une erreur s'est produite")
UNAVAILABLE = re.compile(r"(?:this|ce|cette) (?:content|page|contenu) (?:isn't|is not|n'est pas) (?:available|disponible)"
                         r"|este contenido no esta disponible|esta pagina no esta disponible")


def parse_public(html: str, url: str | None = None, status: int = 200) -> dict:
    """What Facebook serves to someone who isn't logged in: {state, attrs}. state is "found", "login wall"
    (sent to a login page), "refused" (Facebook's bot error page) or "unavailable" (no such profile, or
    not public). attrs uses match.py's keys: fullname, description, image, uid, url, followers, likes,
    talking_about, category, location (lives in), hometown, works_at, studied_at."""
    tree = _Tree(html)
    meta = _meta(tree.root)
    title = next((re.sub(r"\s+", " ", t.text or "").strip() for t in tree.root.iter("title")), "")
    name = meta.get("og:title") or re.sub(r"^\(\d+\)\s*|\s*[|·–-]\s*Facebook$", "", title)
    name = "" if name.lower() == "facebook" else name
    lines = _text(tree.root).split("\n")
    body = _fold(" ".join(lines))
    if status in (400, 403, 429) or title.lower() == "error" or REFUSED.search(body) and not meta.get("og:title"):
        return {"state": "refused", "attrs": {}}
    if re.match(r"/(?:login|checkpoint)\b|/login\.php", urlparse(url or "").path) or LOGIN_TITLE.match(_fold(name)) \
            or LOGIN_TITLE.match(_fold(title)) or not name and tree.root.find(".//form[@id='login_form']") is not None:
        return {"state": "login wall", "attrs": {}}
    if status == 404 or not name:
        return {"state": "unavailable" if status == 404 or UNAVAILABLE.search(body) or not body else "login wall",
                "attrs": {}}
    desc = meta.get("og:description") or meta.get("description") or ""
    attrs = {"fullname": name, "description": desc, "image": meta.get("og:image"), "url": meta.get("og:url") or url}
    uid = next((m[1] for k in ("al:android:url", "al:ios:url", "apple-itunes-app")
                if (m := re.search(r"fb://(?:profile|page)/(?:\?id=)?(\d+)", meta.get(k, "")))), None)
    attrs["uid"] = uid or next((m[1] for rx in (r'"userID":"([1-9]\d+)"', r'"pageID":"([1-9]\d+)"',
                                                r'"entity_id":"?([1-9]\d+)') if (m := re.search(rx, html))), None)
    if m := re.search(r'"category_name":"([^"]+)"', html):
        attrs["category"] = m[1]
    folded = _fold(desc)
    for key, rx in (("followers", rf"{NUM} (?:followers|seguidores|abonnes)"),
                    ("likes", rf"{NUM} (?:likes|me gusta|j'aime|mentions j'aime)"),
                    ("talking_about", rf"{NUM} (?:talking about this|personas estan hablando de esto|en parlent)")):
        if m := re.search(rx, folded):
            attrs[key] = _num(m[1])
    segments = [s.strip() for s in re.split(r" · |\. ", desc) + lines]  # og description, then a saved page's Intro
    for key, rx in INTRO.items():
        if hit := next(((s, m) for s in segments if len(s) < 120 and (m := rx.match(_fold(s)))), None):
            attrs[key] = hit[0][hit[1].start(1):].strip(" .")
    return {"state": "found", "attrs": {k: v for k, v in attrs.items() if v not in (None, "")}}


# --- investigator links ---

def search_links(seeds) -> list[dict]:
    """[{label, url}] for the investigator to open in their own browser, under their own Facebook access:
    Facebook's people/posts/photos search and search-engine dorks for each name, email, phone or username,
    plus a known profile's tabs. Hunt itself never requests any of these."""
    seeds = [seeds] if isinstance(seeds, Seed) else list(seeds)
    places = [s.value.strip() for s in seeds if s.kind == "location"]
    links = []

    def add(label, url):
        if all(link["url"] != url for link in links):
            links.append({"label": label, "url": url})

    def dork(terms):
        q = f"site:facebook.com {terms}"
        add(f"Google: {q}", "https://www.google.com/search?q=" + quote_plus(q))
        add(f"Bing: {q}", "https://www.bing.com/search?q=" + quote_plus(q))

    for s in seeds:
        v = s.value.strip()
        if s.kind == "name":
            for tab in ("people", "posts", "photos", "videos"):
                add(f"Facebook {tab}: {v}", f"{FB}/search/{tab}/?q={quote_plus(v)}")
            for place in places:
                for tab in ("people", "posts"):
                    add(f"Facebook {tab}: {v}, {place}", f"{FB}/search/{tab}/?q={quote_plus(f'{v} {place}')}")
            dork(f'"{v}"')
            for place in places:
                dork(f'"{v}" "{place}"')
        elif s.kind in ("email", "phone"):
            forms = _phone_forms(v) if s.kind == "phone" else [v]
            add(f"Facebook search: {forms[0]}", f"{FB}/search/top/?q={quote_plus(forms[0])}")
            dork(" OR ".join(f'"{f}"' for f in forms))
        elif s.kind == "username":
            if USERNAME.fullmatch(v):
                add(f"Facebook profile: {v}", f"{FB}/{v}")
            add(f"Facebook search: {v}", f"{FB}/search/top/?q={quote_plus(v)}")
            dork(f'"{v}"')
        elif s.kind == "url" and (acct := account(v)):
            url, sep = acct[0], "&sk=" if "?" in acct[0] else "/"
            add("Facebook profile", url)
            for tab in ("about", "photos", "videos", "friends"):
                add(f"Facebook profile: {tab}", url + sep + tab)
    return links


def _phone_forms(value: str) -> list[str]:
    try:
        n = phonenumbers.parse(value, "US")
    except phonenumbers.NumberParseException:
        return [value]
    fmt = phonenumbers.PhoneNumberFormat
    national = phonenumbers.format_number(n, fmt.NATIONAL)
    return list(dict.fromkeys([national, phonenumbers.format_number(n, fmt.INTERNATIONAL),
                               re.sub(r"\D", "", national), phonenumbers.format_number(n, fmt.E164)]))


# --- scan categories ---

_c = lambda rx: re.compile(rf"\b(?:{rx})")
WORDS = {  # folded activity tags and life events, English / Spanish / French, in the wizard's order
    "activity": _c(r"danc\w*|garden\w*|diy\b|renovat\w*|climb\w*|kayak\w*|surf\w*|ski\b|skiing|snowboard\w*|yoga|"
                   r"fishing|camping|mow\w*|moved to|moving\b|bail\w*|jardin\w*|escala\w*|esqui\w*|pesca\w*|acampa\w*|"
                   r"mudanza|me mude|se mudo|danse\w*|bricol\w*|peche\b|demenag\w*|emmenag\w*|s'est installe"),
    "lifting": _c(r"lift\w*|weights?\b|deadlift\w*|bench press|squat\w*|powerlift\w*|carry\w*|carrie\w*|hauling|"
                  r"pesas|levant\w*|cargando|halter\w*|soulev\w*|muscu\w*"),
    "sport": _c(r"gym\w*|work(?:ing)? ?out|training|crossfit|football|soccer|rugby|tennis|golf|basketball|baseball|"
                r"softball|hockey|volleyball|cricket|marathon|race\b|running|jogging|swim\w*|cycling|boxing|exercis\w*|"
                r"gimnasio|entren\w*|futbol|baloncesto|correr|corriendo|carrera|maraton|natacion|nadando|ciclismo|"
                r"boxeo|ejercicio|salle de sport|muscu\w*|s'entrain\w*|entrainement|foot\b|basket\b|course\b|courir|"
                r"natation|velo\b|boxe\b"),
    "walks": _c(r"hik\w*|trail\w*|trek\w*|walk\w*|ramble|mountain|summit|senderismo|caminata|caminando|sendero|"
                r"montana|paseo|randonn\w*|rando\b|balade|sentier|montagne"),
    "travel": _c(r"travel\w*|trip to|vacation|holiday|flight|flying|airport|cruise|abroad|viaj\w*|vacaciones|vuelo|"
                 r"aeropuerto|crucero|voyag\w*|vacances|aeroport|croisiere|en vol\b"),
    "other_job": _c(r"new job|new position|started (?:a )?(?:new )?job|started working|working(?! ?out)|at work|shift\b|promot\w*|"
                    r"first day at|nuevo (?:trabajo|empleo)|empezo a trabajar|comenzo a trabajar|trabaj\w*|primer dia|"
                    r"nouvel emploi|nouveau travail|a commence a travailler|travaill\w*|premier jour"),
    "driving": _c(r"driv\w*|road ?trip|new (?:car|truck)|bought a (?:new )?(?:car|truck)|behind the wheel|manej\w*|"
                  r"conduc\w*|viaje por carretera|(?:coche|auto|carro) nuevo|compro un (?:coche|auto|carro)|condui\w*|"
                  r"au volant|en voiture|nouvelle voiture|a achete une voiture"),
    "injury": _c(r"injur\w*|hurt\w*|broke (?:my|a|his|her|their)\b|broken|surgery|hospital\w*|physio\w*|rehab\w*|"
                 r"recover\w*|in pain|sore\b|crutches|lesion\w*|herid\w*|cirugia|operacion|operad\w*|fisioterap\w*|"
                 r"rehabilit\w*|recuper\w*|me rompi|dolor\w*|blessee?s?\b|blessure\w*|operation|opere\w*|chirurg\w*|"
                 r"hopital|kine\w*|reeducation|je me suis casse|douleur\w*"),
}
PLACES = {  # folded check-in place names
    "activity": _c(r"climbing|bouldering|ski (?:resort|area)|escalada|rocodromo|estacion de esqui|escalade|"
                   r"station de ski"),
    "sport": _c(r"gym\w*|fitness|crossfit|stadium|arena|sports? (?:center|centre|complex|club)|golf|tennis|pool\b|"
                r"leisure cent\w*|gimnasio|estadio|polideportivo|piscina|club deportivo|salle de sport|stade|piscine|"
                r"complexe sportif"),
    "walks": _c(r"trail\w*|national park|state park|mountain|peak\b|summit|canyon|forest|sendero|parque nacional|"
                r"montana|pico\b|bosque|sentier|parc national|montagne|foret|randonnee"),
    "travel": _c(r"airport|terminal|hotel|resort|cruise|aeropuerto|crucero|aeroport|gare\b"),
    "driving": _c(r"dmv\b|car dealer\w*|dealership|gas station|race ?track|concesionario|gasolinera|concessionnaire|"
                  r"station[- ]service"),
    "injury": _c(r"hospital|clinic|medical cent\w*|physio\w*|physical therapy|urgent care|emergency|clinica|"
                 r"fisioterap\w*|urgencias|hopital|clinique|kine\w*|urgences"),
}


def categories(post: dict) -> list[tuple[str, str]]:
    """[(scan category key, why)] that a post's own tags point to: its feeling/activity tag, life event and check-in,
    and Instagram's automatic image description ("May be an image of 1 person, lifting weights and gym"). The scan's
    keyword pass already reads the post text, so text isn't used."""
    out = {}
    for field, label, table in (("activity", "feeling/activity", WORDS), ("life_event", "life event", WORDS),
                                ("place", "check-in", PLACES), ("alt", "image description", WORDS)):
        if value := post.get(field):
            folded = _fold(value)
            for key, rx in table.items():
                if key not in out and rx.search(folded):
                    out[key] = f'{post.get("source") or "Facebook"} {label}: "{value}"'
    return list(out.items())
