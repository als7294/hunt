"""Shared plumbing for sources that read public HTML pages logged out (legal.md C6, revised D2).

Every reader: Hunt's own User-Agent, no cookies carried in, a polite gap, and a hard stop at the first refusal.
`walled()` names a CAPTCHA, bot wall or login wall in a page; `get()`/`post()` raise `Limited` on a 403, a 429 or a
wall, so search.fan_out holds the host for the rest of the run and the note says why. Nothing here retries, rotates
or disguises anything (C7). Parsing is stdlib only: a small element tree, `text()`, `tables()` and `forms()`.
"""

import asyncio
import os
import re
import ssl
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from urllib.parse import urljoin

import httpx

from . import _api
from ._api import Limited

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
BLOCK = {"div", "p", "br", "h1", "h2", "h3", "h4", "h5", "h6", "li", "ul", "ol", "tr", "td", "th", "table", "form", "section",
         "article", "header", "footer", "dd", "dt", "option"}
SKIP = {"script", "style", "noscript", "template", "svg", "title", "head"}
# What a refusal looks like in a 200 page: a CAPTCHA widget or its answer field (not a site-wide script include: many
# court sites load reCAPTCHA for a contact form), a bot-wall page, or a password field. Matched against the HTML itself.
WALLS = (("CAPTCHA", r"class=[\"']?(?:g-recaptcha|h-captcha|cf-turnstile)\b|data-sitekey=|g-recaptcha-response|h-captcha-response|"
                     r"botdetect|captchaimage|LBD_VCT|name=[\"']?captcha\b|verify (?:that )?you are (?:a )?human|verify your humanity|"
                     r"i'm not a robot|not a robot box"),
         ("bot wall", r"_incapsula_|incapsula|imperva|akamai.*bot|cf-chl|cf-mitigated|just a moment\.\.\.|attention required|access denied|"
                      r"request unsuccessful|the requested url was rejected|distil_r|px-captcha|perimeterx|datadome|security check"),
         ("login wall", r"<input[^>]+type=[\"']?password"))
PAUSE = 1.0  # seconds between requests to one host


def walled(html: str) -> str | None:
    """"CAPTCHA", "bot wall" or "login wall" when the page is one, else None."""
    sample = html[:400_000]
    return next((name for name, rx in WALLS if re.search(rx, sample, re.I | re.S)), None)


class _Tree(HTMLParser):
    def __init__(self, html: str):
        super().__init__(convert_charrefs=True)
        self.root = ET.Element("document")
        self.stack = [self.root]
        self.feed(html)
        self.close()

    def handle_starttag(self, tag, attrs):
        el = ET.SubElement(self.stack[-1], tag, {k: v or "" for k, v in attrs})
        if tag not in VOID and len(self.stack) < 200:
            self.stack.append(el)

    def handle_startendtag(self, tag, attrs):
        ET.SubElement(self.stack[-1], tag, {k: v or "" for k, v in attrs})

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        top = self.stack[-1]
        if len(top):
            top[-1].tail = (top[-1].tail or "") + data
        else:
            top.text = (top.text or "") + data


def tree(html: str) -> ET.Element:
    return _Tree(html).root


def text(e, sep: str = " ") -> str:
    """Visible text of an element, whitespace folded; block elements separated by `sep`."""
    parts = []

    def walk(n):
        if n.tag in SKIP:
            return
        block = "\n" if n.tag in BLOCK else ""
        parts.append(block + (n.text or ""))
        for c in n:
            walk(c)
            parts.append(c.tail or "")
        parts.append(block)

    walk(e)
    lines = (re.sub(r"\s+", " ", line).strip() for line in "".join(parts).split("\n"))
    return sep.join(line for line in lines if line)


def tables(root, header_words=(), cell_sep: str = " ") -> list[list[dict]]:
    """Each <table> as a list of row dicts keyed by header text (or col0, col1… without headers). With
    `header_words`, only tables whose headers mention every word. Links in a cell are kept as `<key> href`;
    `cell_sep` joins a cell's lines (a <br>-separated list reads back with "\n")."""
    out = []
    for t in root.iter("table"):
        rows = [tr for tr in t.iter("tr") if any(c.tag in ("td", "th") for c in tr)]
        if not rows:
            continue
        hdr = next((i for i, tr in enumerate(rows[:3]) if all(c.tag == "th" for c in tr if c.tag in ("td", "th"))), None)
        if hdr is None:  # no <th> row (a pager row may sit above one): positional keys, every row is a body row
            heads = [f"col{i}" for i in range(len([c for c in rows[0] if c.tag in ("td", "th")]))]
            body = rows
        else:
            heads = [text(c) for c in rows[hdr] if c.tag in ("td", "th")]
            body = rows[hdr + 1:]
        if header_words and not all(any(w.lower() in h.lower() for h in heads) for w in header_words):
            continue
        parsed = []
        for tr in body:
            cells = [c for c in tr if c.tag in ("td", "th")]
            row = {}
            for i, c in enumerate(cells):
                key = heads[i] if i < len(heads) and heads[i] else f"col{i}"
                row[key] = text(c, cell_sep)
                a = next(c.iter("a"), None)
                if a is not None and a.get("href"):
                    row[f"{key} href"] = a.get("href")
            if any(v for v in row.values()):
                parsed.append(row)
        out.append(parsed)
    return out


def forms(root, base: str = "") -> list[dict]:
    """Each <form>: {action, method, fields} with every input/select's current value (hidden ones included), so a
    reader echoes back what the page gave it, as a browser would."""
    out = []
    for f in root.iter("form"):
        fields = {}
        for i in f.iter("input"):
            if i.get("name") and i.get("type", "text").lower() not in ("submit", "button", "image", "checkbox", "radio"):
                fields[i.get("name")] = i.get("value", "")
            elif i.get("name") and i.get("type", "").lower() in ("checkbox", "radio") and i.get("checked") is not None:
                fields[i.get("name")] = i.get("value", "on")
        for s in f.iter("select"):
            if s.get("name"):
                chosen = next((o for o in s.iter("option") if o.get("selected") is not None), next(s.iter("option"), None))
                fields[s.get("name")] = (chosen.get("value") if chosen is not None and chosen.get("value") is not None
                                         else text(chosen) if chosen is not None else "")
        for t in f.iter("textarea"):
            if t.get("name"):
                fields[t.get("name")] = t.text or ""
        out.append({"action": urljoin(base, f.get("action", "")) if base else f.get("action", ""),
                    "method": f.get("method", "get").lower(), "id": f.get("id", ""), "fields": fields})
    return out


ACCEPT = "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8"


def client(timeout: float = 30, legacy_tls: bool = False) -> httpx.AsyncClient:
    """_api.client (Hunt's UA, HUNT_PROXY, redirects) accepting HTML: one session's own cookies only. `legacy_tls` lets
    a server that offers only an RSA-key-exchange cipher (no forward secrecy; some court hosts) complete the handshake,
    with the certificate still verified: Hunt accepts the server's own cipher, it never imitates a browser's (C7)."""
    if not legacy_tls:
        return _api.client(timeout, Accept=ACCEPT)
    ctx = ssl.create_default_context()
    ctx.set_ciphers("DEFAULT:@SECLEVEL=1")
    return httpx.AsyncClient(timeout=timeout, follow_redirects=True, proxy=os.environ.get("HUNT_PROXY"), verify=ctx,
                             headers={"User-Agent": _api.UA, "Accept": ACCEPT})


def _check(r: httpx.Response) -> httpx.Response:
    if r.status_code in (401, 403, 429):
        raise Limited(f"{r.url.host} refused ({r.status_code}); stopped for this run")
    r.raise_for_status()
    if ("html" in r.headers.get("content-type", "") or r.text[:300].lstrip().startswith("<")) and (w := walled(r.text)):
        raise Limited(f"{r.url.host} showed a {w}; stopped for this run")
    return r


async def get(c: httpx.AsyncClient, url: str, **kw) -> httpx.Response:
    """GET, then a polite pause. Limited on a refusal or a wall (never retried, never worked around)."""
    r = _check(await c.get(url, **kw))
    await asyncio.sleep(PAUSE)
    return r


async def post(c: httpx.AsyncClient, url: str, **kw) -> httpx.Response:
    r = _check(await c.post(url, **kw))
    await asyncio.sleep(PAUSE)
    return r
