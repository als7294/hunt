"""Offline self-check for hunt/enrich.py: which profile pages get read, and what is kept. Run: uv run python test_enrich.py

Pages and robots files are served by httpx.MockTransport, nothing leaves the machine, and the people are fictional.
"""

import asyncio
import json
import os
import tempfile

os.environ["HUNT_HOME"] = tempfile.mkdtemp()  # before hunt.case reads it

import httpx

from hunt import enrich, search
from hunt.case import Case
from hunt.enrich import fields, is_profile, meta, parsed
from hunt.seed import Finding, Seed

H = "kvane88"  # a handle that is not just the name squashed together

# Metadata parsing: entities, quoting styles, first value wins, only the preview keys
page = ('<html><head><title> Kestrel  Vane (@kvane88) &middot; Example </title><meta property="og:title" content="Kestrel Vane">'
        "<meta name='twitter:image' content='/pics/kv.png'><meta property=\"og:description\" content=\"Maps &amp; birds\">"
        '<meta property="og:title" content="second"><meta name="viewport" content="width=device-width"></head></html>')
assert meta(page) == {"title": "Kestrel Vane (@kvane88) · Example", "og:title": "Kestrel Vane", "twitter:image": "/pics/kv.png",
                      "og:description": "Maps & birds"}, meta(page)
assert fields(meta(page), f"https://www.example.com/{H}", H) == {"fullname": "Kestrel Vane", "bio": "Maps & birds",
                                                                 "image": "https://www.example.com/pics/kv.png"}
# A title that only echoes the handle or the site gives no name; the picture still counts
for title in (f"{H} (@{H}) · GitHub", f"{H} - YouTube", f"{H} | Flipboard", f"{H}'s Profile - Chess.com", "Chess.com", "kvane_88",
              f"@{H}", f"{H} on Twitch", "Profile", "Just a moment..."):
    site = {"GitHub": "github.com", "YouTube": "www.youtube.com", "Flipboard": "flipboard.com", "Twitch": "www.twitch.tv"}
    host = next((v for k, v in site.items() if k in title), "www.chess.com")
    assert "fullname" not in fields({"title": title, "og:image": "https://cdn.test/p.jpg"}, f"https://{host}/member/{H}", H), title
assert fields({"og:title": "Kestrel Vane (@kvane88) · GitHub"}, f"https://github.com/{H}", H) == {"fullname": "Kestrel Vane"}
assert fields({"title": "Kestrel Vane on Twitch"}, f"https://www.twitch.tv/{H}", H) == {"fullname": "Kestrel Vane"}
assert fields({"og:description": H, "twitter:description": "x"}, f"https://a.test/{H}", H) == {}  # a bio that is just the handle
assert fields({"og:image": "data:image/png;base64,AAAA"}, f"https://a.test/{H}", H) == {}
# A site's furniture is not a name, its logo or share card is not a photo, and its own line about the page is not a bio
for title in ("Overview", "Streamer Overview & Stats", "The Techie Teacher", "Be Animated", "Trading Ideas and Scripts",
              f"{H}’s gists", "Group Chat That’s All Fun & Games", "Imagine, Program, Share", "chevron-down", "kvane88 Live Stream"):
    assert "fullname" not in fields({"og:title": title}, f"https://a.test/{H}", H), title
for title in ("Ana de la Cruz", "Jean-Luc O'Neil", "Иван Петров", "Smitty"):
    assert fields({"og:title": title}, f"https://a.test/{H}", H) == {"fullname": title}, title
for img in ("https://github.com/opengraph.png", "https://cdn.test/x/Discord-OG-image.png", "https://a.test/share/user/kvane88",
            "https://a.test/og/user/kvane88.png", "https://s.a.test/static/images/logo-preview.png",
            "https://a.test/default-avatar-2.webp"):
    assert "image" not in fields({"og:image": img}, f"https://a.test/{H}", H), img
assert fields({"og:image": "https://pics.a.test/43ed76a4?width=460"}, f"https://a.test/{H}", H) == \
    {"image": "https://pics.a.test/43ed76a4?width=460"}
assert fields({"og:description": f"Follow {H} on A for charts"}, f"https://a.test/u/{H}", H) == {}
assert fields({"og:description": "A is the world's leading platform"}, f"https://www.a.test/{H}", H) == {}

# Tags before the <title> are read too (the title's closing tag once swallowed them), an inline SVG's <title> in the body
# is an icon's name, "handle (Real Name)" gives the name, and a title naming the site is the site's own
HUB = ('<html><head><meta charset="utf-8"><meta name="description" content="x"><meta property="og:title" content="kvane88 (Kestrel Vane)">'
       '<meta property="og:image" content="https://cdn.hub.test/u/kv.png"><title>kvane88 (Kestrel Vane)</title></head>'
       '<body><svg><title>chevron-down</title></svg></body></html>')
assert meta(HUB) == {"og:title": "kvane88 (Kestrel Vane)", "og:image": "https://cdn.hub.test/u/kv.png", "title": "kvane88 (Kestrel Vane)"}
assert fields(meta(HUB), f"https://hub.test/{H}", H) == {"fullname": "Kestrel Vane", "image": "https://cdn.hub.test/u/kv.png"}
assert meta("<html><head></head><body><svg><title>linux</title></svg></body></html>") == {}
for title, host in (("Watch Snapchat Stories", "www.snapchat.com"), ("Sign In", "a.test"), ("Not Found", "a.test"), ("Log In", "a.test")):
    assert "fullname" not in fields({"title": title}, f"https://{host}/add/{H}", H), title
assert fields({"og:title": "Dorian Vell (@kvane88) on Flipboard"}, f"https://flipboard.com/@{H}", H) == {"fullname": "Dorian Vell"}

# A site's own door is not a profile: an email-registration hit is the site's homepage, whose og:title is a headline
for url in ("https://foxnews.com", "https://tv.apple.com/", "https://site.test/login", "https://site.test/account/",
            "https://site.test/signin/", "https://site.test/home/index.html", "https://news.example/", "https://site.test/accounts/login/",
            f"https://api.site.test/users/profiles/{H}", "https://site.test/api/v9/unique-username/attempt"):  # an engine's check URL
    assert not is_profile(url, "kestrel@example.com") and not is_profile(url, H), url
for url in (f"https://site.test/{H}", f"https://site.test/login/{H}", f"https://news.test/user?id={H}", f"https://{H}.blog.example/",
            "https://site.test/u/12345", f"https://site.test/account/{H}/", "https://kestrel-vane.weebly.com/"):
    assert is_profile(url, H if "kestrel-vane" not in url else "kestrel.vane"), url

# socid_extractor reads the sites it knows (here: a Chess.com-shaped page) and wins over the preview tags
CHESS = ('<html><head><meta property="og:site_name" content="Chess.com">'
         '<title>Kestrel Vane (kvane88) - Chess Profile - Chess.com</title>'
         '<meta property="og:title" content="Kestrel Vane (kvane88) - Chess Profile">'
         '<meta property="og:image" content="https://images.chess.test/uploads/v1/user/41.200x200o.jpeg"></head></html>')
assert parsed(CHESS) == {"fullname": "Kestrel Vane", "image": "https://images.chess.test/uploads/v1/user/41.200x200o.jpeg"}, parsed(CHESS)
assert parsed("<html>nothing</html>") == {} and parsed("") == {}

# A search: which hosts get read, and what each answer does
seed = Seed("username", H)
case = Case("Kestrel Vane", purpose="test")
pages = {
    "open.test": '<title>Kestrel Vane (@kvane88) · Open</title><meta property="og:image" content="https://cdn.open.test/kv.jpg">',
    "closed.test": '<title>Kestrel Vane</title>',  # robots.txt disallows /u/: read logged out all the same, and noted (D2)
    "wall.test": "<title>Just a moment...</title><p>Verify you are human</p>",
    "dark.test": "<title>Kestrel Vane</title>",  # robots.txt unreachable: read, and noted
    "refuse.test": "",  # 403
    "echo.test": '<title>kvane88 - Echo</title><meta property="og:description" content="Birds &amp; maps">',
    "gate.test": "<title>Log in to Gate</title>",  # the profile URL redirects to a login page
    "parsed.test": CHESS,  # a site socid_extractor knows
}
robots = {"open.test": "User-agent: *\nDisallow: /private/\n", "closed.test": "User-agent: *\nDisallow: /u/\n",
          "wall.test": "", "refuse.test": "", "echo.test": "User-agent: Hunt\nAllow: /\n\nUser-agent: *\nDisallow: /\n", "gate.test": "", "parsed.test": ""}
served = []


def answer(request):
    host, path = request.url.host, request.url.path
    served.append(f"{host}{path}")
    assert request.headers["user-agent"].startswith("Hunt/"), request.headers["user-agent"]
    if path == "/robots.txt":
        if host == "dark.test":
            raise httpx.ConnectError("no route")
        return httpx.Response(200 if robots[host] else 404, text=robots[host])
    if host == "refuse.test":
        return httpx.Response(403, text="forbidden")
    if host == "gate.test" and path != "/login":
        return httpx.Response(302, headers={"Location": "/login?next=" + path})
    return httpx.Response(200, text=pages[host], headers={"Content-Type": "text/html"})


urls = [f"https://open.test/{H}", f"https://closed.test/u/{H}", f"https://wall.test/{H}", f"https://wall.test/{H}/second",
        f"https://dark.test/{H}", f"https://refuse.test/{H}", f"https://refuse.test/{H}2", f"https://echo.test/{H}",
        f"https://gate.test/{H}", f"https://gate.test/{H}2", f"https://parsed.test/member/{H}", f"https://www.instagram.com/{H}",
        f"https://www.whitepages.com/name/{H}"]
doors = ["https://foxnews.test", "https://tv.apple.test/", "https://site.test/login"]
for u in urls:
    case.add_finding(Finding("maigret", seed, u.split("/")[2], u, {"tags": ["x"]}))
for u in doors:  # email-registration hits: the site's own door, never read
    case.add_finding(Finding("user-scanner", Seed("email", "kestrel@example.com"), u.split("/")[2], u, {"category": "news"}))
case.add_finding(Finding("maigret", Seed("name", "Kestrel Vane"), "names.test", f"https://names.test/{H}", {}))  # a name-only hit: not read
case.add_finding(Finding("bluesky", seed, "Bluesky", f"https://bsky.app/profile/{H}", {"fullname": "Kestrel Vane"}))  # described already
real_client = enrich.httpx.AsyncClient
enrich.httpx.AsyncClient = lambda **kw: real_client(transport=httpx.MockTransport(answer), headers=kw["headers"],
                                                    follow_redirects=kw["follow_redirects"])
log = []
out = asyncio.run(enrich.run(case, search.build(case)["candidates"], log.append))
# closed and dark are read all the same and noted; the second pages of the stopped hosts are never fetched
assert out["read"] == 8 and out["enriched"] == 5 and out["skipped"] == 2, out
assert out["robots"] == {"closed.test": "robots.txt disallows; read logged out under D2",
                         "dark.test": "robots.txt unreadable; read logged out under D2"}, out["robots"]
assert out["stopped"] == {"wall.test": "CAPTCHA or bot wall (Just a moment...)", "refuse.test": "HTTP 403",
                          "gate.test": "login wall (Log in to Gate)"}, out["stopped"]
hosts = ("open.test", "closed.test", "wall.test", "dark.test", "refuse.test", "echo.test", "gate.test", "parsed.test")
first = [f"open.test/{H}", f"closed.test/u/{H}", f"wall.test/{H}", f"dark.test/{H}", f"refuse.test/{H}", f"echo.test/{H}",
         f"gate.test/{H}", f"parsed.test/member/{H}"]
assert sorted(served) == sorted([f"{h}/robots.txt" for h in hosts] + first + ["gate.test/login"]), served
got = {c["url"]: c["attrs"] for c in search.build(case)["candidates"]}
assert got[f"https://open.test/{H}"] == {"tags": ["x"], "fullname": "Kestrel Vane", "image": "https://cdn.open.test/kv.jpg",
                                         "enriched_from": f"https://open.test/{H}"}, got[f"https://open.test/{H}"]
assert got[f"https://echo.test/{H}"] == {"tags": ["x"], "bio": "Birds & maps", "enriched_from": f"https://echo.test/{H}"}
assert got[f"https://closed.test/u/{H}"]["fullname"] == got[f"https://dark.test/{H}"]["fullname"] == "Kestrel Vane"
assert got[f"https://parsed.test/member/{H}"] == {"tags": ["x"], "fullname": "Kestrel Vane", "image": "https://images.chess.test/uploads/v1/user/41.200x200o.jpeg",
                                                 "enriched_from": f"https://parsed.test/member/{H}"}
assert all("enriched_from" not in got[u] for u in urls + doors
           if not any(h in u for h in ("open", "echo", "closed", "dark", "parsed")))
audit = [json.loads(r["detail"]) for r in case.rows("select detail from audit where action = 'enrich stopped'")]
assert sorted(a["host"] for a in audit) == ["gate.test", "refuse.test", "wall.test"]
assert json.loads(case.rows("select detail from audit where action = 'enrich'")[0]["detail"])["robots"] == out["robots"]
assert any("5 of 8 profile pages read" in e["message"] for e in log), log

# The same day: robots files and pages already read aren't asked for again; a new account on a read host is, and so are
# the pages a stop left unread (a stop holds for one search, not for the day)
served.clear()
case.add_finding(Finding("whatsmyname", seed, "open.test", f"https://open.test/{H}-two", {}))
out = asyncio.run(enrich.run(case, search.build(case)["candidates"], log.append))
assert sorted(served) == sorted([f"open.test/{H}-two", f"wall.test/{H}/second", f"refuse.test/{H}2", f"gate.test/{H}2",
                                 "gate.test/login"]) and out["read"] == 4 and out["skipped"] == 6, (served, out)  # the described ones are out of scope now
assert enrich.CACHE.stat().st_mode & 0o777 == 0o600

# A page an engine already fetched (its body is in the case's evidence) is read from that copy, never requested again:
# an HTML profile page, or an API's JSON that socid_extractor knows. A body that says nothing and isn't a page isn't it.
served.clear()
case.add_finding(Finding("whatsmyname", seed, "hub.test", f"https://hub.test/{H}", {"category": "tech"}, body=HUB))
case.add_finding(Finding("whatsmyname", seed, "json.test", f"https://json.test/{H}", {}, body='{"taken": true}'))
case.add_finding(Finding("whatsmyname", seed, "bare.test", f"https://bare.test/{H}", {}, body="<html><head><title>kvane88</title></head></html>"))
pages["json.test"], robots["json.test"] = "<title>Kestrel Vane</title>", ""
out = asyncio.run(enrich.run(case, search.build(case)["candidates"], log.append))
got = {c["url"]: c["attrs"] for c in search.build(case)["candidates"]}
assert got[f"https://hub.test/{H}"] == {"category": "tech", "fullname": "Kestrel Vane", "image": "https://cdn.hub.test/u/kv.png",
                                        "enriched_from": f"https://hub.test/{H}"}, got[f"https://hub.test/{H}"]
assert out["held"] == 1 and out["read"] == 1 and sorted(served) == ["json.test/kvane88", "json.test/robots.txt"], (out, served)
assert got[f"https://json.test/{H}"]["fullname"] == "Kestrel Vane" and "enriched_from" not in got[f"https://bare.test/{H}"]
enrich.httpx.AsyncClient = real_client
print("ok")
