"""Shared harness for the public-profile source self-checks (test_reddit.py, test_snapchat.py, …).

Each check serves hand-written, fictional pages through httpx.MockTransport, so nothing leaves the machine, and asserts
the read stays honest: GET only, Hunt's own User-Agent, no cookie sent, and a stop at the first refusal (legal.md C6).
"""

import asyncio
import os
import tempfile

os.environ.setdefault("HUNT_HOME", tempfile.mkdtemp())  # before hunt.case reads it

import httpx

from hunt.seed import Seed
from hunt.sources import _api, _page

_page.GAP = 0


def serve(mod, routes: dict) -> list[httpx.Request]:
    """Point `mod`'s client at fixtures. routes: {substring of the URL: (status, str | dict | list[, headers])}; first
    match wins, else 404. Returns the requests made."""
    seen = []

    def answer(request):
        seen.append(request)
        for key, (status, body, *headers) in routes.items():
            if key in str(request.url):
                kw = {"json": body} if isinstance(body, (dict, list)) else {"text": body}
                return httpx.Response(status, headers=headers[0] if headers else None, **kw)
        return httpx.Response(404, text="<html>not here</html>")

    mod.client = lambda timeout=20, **h: httpx.AsyncClient(transport=httpx.MockTransport(answer), follow_redirects=True,
                                                          headers={"User-Agent": _api.UA, **h})
    _page._last.clear()
    return seen


def run(mod, value: str, kind: str = "username"):
    return asyncio.run(mod.search(Seed(kind, value)))


def refused(mod, value: str) -> str:
    try:
        run(mod, value)
    except _page.Refused as e:
        return str(e)
    raise AssertionError(f"{mod.NAME} didn't stop at the refusal")


def honest(seen: list[httpx.Request]):
    """Every request a plain logged-out GET under Hunt's own name."""
    assert seen and all(r.method == "GET" and r.headers["user-agent"] == _api.UA and "cookie" not in r.headers
                        for r in seen), seen


def walls(mod, value: str, url_part: str):
    """The common refusals all stop the source: 403, 429, a login redirect, a bot wall."""
    for answer in ((403, "<html>Forbidden</html>"), (429, "slow down"),
                   (302, "", {"location": "https://example.test/login?next=/x"}),
                   (200, "<html><head><title>Just a moment...</title></head></html>")):
        serve(mod, {url_part: answer, "example.test/login": (200, "<html>Log in</html>")})
        assert refused(mod, value), answer
