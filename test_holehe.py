"""Offline self-check for hunt/sources/holehe.py. Run: uv run python test_holehe.py

The audit sets are checked against the installed holehe release; one real module and one fake run against an
httpx.MockTransport, so nothing leaves the machine. The address is fictional.
"""

import asyncio
import os
import tempfile

os.environ["HUNT_HOME"] = tempfile.mkdtemp()  # before hunt.case reads it

import httpx
from holehe import localuseragent

from hunt.seed import Seed
from hunt.sources import _api, holehe as src, user_scanner

# The audit covers every module of the pinned release, and no module is both silent and noisy
fns = src._functions()
noisy = set().union(*src.NOISY.values())
assert len(fns) == 121 and not src.SILENT & noisy and not (src.SILENT | noisy) - set(fns) and not set(fns) - src.SILENT - noisy
elsewhere = {m.__name__ for m in user_scanner._modules() if not user_scanner._skip(m)}
why = {n: src._skip(n, f, elsewhere) for n, f in fns.items()}
assert why["replit"] is None and why["mybb"] is None and why["github"] is None
assert why["amazon"] == "login attempt" and why["mail_ru"] == "password recovery" and why["discord"] == "sign-up"
assert why["quora"] == "unclear" and why["twitter"] == "unclear"  # never run: the deny list is checked only for the silent set
assert why["xvideos"] == why["spotify"] == "user-scanner checks it", (why["xvideos"], why["spotify"])
assert sum(w is None for w in why.values()) == 58 and all(w in src.REASONS for w in why.values() if w)
real_version = src.version
src.version = lambda dist: "9.9"
assert all(src._skip(n, f, elsewhere) == "unaudited" for n, f in fns.items())
src.version = real_version

# A search: a real module (Replit's email-exists lookup) and a fake one, both through Hunt's client and User-Agent
seen = []


def answer(request):
    seen.append(request)
    assert request.headers["user-agent"] == _api.UA, request.headers["user-agent"]
    if request.url.host == "replit.com":
        assert request.method == "POST" and b"kestrel@example.com" in request.content
        return httpx.Response(200, json={"exists": True})
    return httpx.Response(200, json={"taken": False})


async def quietforum(email, client, out):
    assert localuseragent.ua["browsers"]["chrome"] == [_api.UA]  # every module's random.choice lands on Hunt's own UA
    r = await client.get("https://forum.example/xmlhttp.php", params={"action": "email_availability", "email": email})
    out.append({"name": "quietforum", "domain": "forum.example", "method": "register", "rateLimit": False, "exists": r.json()["taken"]})


async def broken(email, client, out):
    raise KeyError("the page changed")


quietforum.__module__ = broken.__module__ = "holehe.modules.forum.fake"
real_functions, real_client = src._functions, src.httpx.AsyncClient
src._functions = lambda: {"replit": fns["replit"], "quietforum": quietforum, "broken": broken, "mail_ru": fns["mail_ru"]}
src.SILENT = src.SILENT | {"quietforum", "broken"}
src.httpx.AsyncClient = lambda **kw: real_client(transport=httpx.MockTransport(answer), headers=kw["headers"])
found, checked, note = asyncio.run(src.search(Seed("email", "kestrel@example.com")))
src._functions, src.httpx.AsyncClient = real_functions, real_client
assert sorted(str(r.url.host) for r in seen) == ["forum.example", "replit.com"], seen  # mail_ru never ran
assert [(f.source, f.site, f.url, f.attrs) for f in found] == [("holehe", "replit", "https://replit.com",
                                                                 {"category": "programing", "method": "register"})]
assert checked == 2 and note.startswith("checked 3 sites, 1 errors; skipped 1: 0 login attempts, 1 password recoveries"), note
print("ok")
