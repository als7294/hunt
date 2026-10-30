"""Offline self-check for the API sources and their health check. Run: uv run python test_sources.py  (--live adds a few real calls)

Responses are hand-written fixtures served by httpx.MockTransport; the proxy check uses a
fake proxy on localhost, so nothing leaves the machine. The people here are fictional.
"""

import asyncio
import base64
import hashlib
import os
import shutil
import sys
import tempfile
import time
from urllib.parse import unquote

os.environ["HUNT_HOME"] = tempfile.mkdtemp()  # before hunt.case reads it
for var in ("HUNT_PROXY", "HUNT_GITHUB_TOKEN", "HUNT_GRAVATAR_KEY", "HUNT_FEC_KEY", "HUNT_SEC_UA", "HUNT_COURTLISTENER_TOKEN",
            "HUNT_SOCRATA_TOKEN"):
    os.environ.pop(var, None)

import httpx

from hunt.match import score
from hunt.seed import KINDS, Seed
import hunt.sources as registry
from hunt.sources import (SOURCES, _api, _socrata, bluesky, businesses, courtlistener, courts, edgar, fec, fmcsa, github,
                          gravatar, keybase, licences, mastodon, npi, openpgp, stackexchange, wayback)

NEW = [github, gravatar, keybase, bluesky, mastodon, stackexchange, openpgp, wayback, fec, edgar, npi, courtlistener,
       licences, businesses, fmcsa, courts]
CLIENTS = [m for m in NEW if hasattr(m, "client")] + [_socrata, registry]  # every module that opens a client
REAL_CLIENT = _api.client
wayback.PAUSE = 0
EMAIL = "rv@example.com"
MD5 = hashlib.md5(EMAIL.encode()).hexdigest()


def serve(routes):
    """Point every new source at a MockTransport and return the requests it sees.

    routes: {substring of the decoded URL: (status, json or text[, headers])}, or an exception to raise;
    first match wins, else 404. A key may start with "HEAD " to match only HEAD requests.
    """
    shutil.rmtree(github.CACHE, ignore_errors=True)
    seen = []

    def answer(request):
        seen.append(request)
        for key, answer_ in routes.items():
            method, _, part = key.rpartition(" ") if key.startswith("HEAD ") else ("", "", key)
            if part in unquote(str(request.url)) and (not method or method == request.method):
                if isinstance(answer_, Exception):
                    raise answer_
                status, payload, *headers = answer_
                body = {"text": payload} if isinstance(payload, str) else {"json": payload}
                return httpx.Response(status, headers=headers[0] if headers else None, **body)
        return httpx.Response(404, json={})

    def fake(timeout=None, **headers):
        return httpx.AsyncClient(transport=httpx.MockTransport(answer), headers={"User-Agent": _api.UA, **headers})

    for m in CLIENTS:
        m.client = fake
    return seen


def run(mod, kind, value):
    return asyncio.run(mod.search(Seed(kind, value)))


def raises(exc, mod, kind, value) -> str:
    try:
        run(mod, kind, value)
    except exc as e:
        return str(e)
    raise AssertionError(f"{mod.NAME}: expected {exc.__name__}")


# Registry: every source keeps the contract
assert set(NEW) <= set(SOURCES) and len({s.NAME for s in SOURCES}) == len(SOURCES)
assert all(set(s.KINDS) <= set(KINDS) and asyncio.iscoroutinefunction(s.search) for s in SOURCES)

# GitHub: profile + social links, cached; impossible handles cost nothing
PROFILE = {"login": "kestrel-vane", "html_url": "https://github.com/kestrel-vane", "name": "Robert Vance",
           "location": "Tucson, AZ", "blog": "https://kvane.example", "twitter_username": "kvane_tw", "email": None,
           "avatar_url": "https://avatars.githubusercontent.com/u/1?v=4", "type": "User"}
seen = serve({"/users/kestrel-vane/social_accounts": (200, [{"provider": "twitter", "url": "https://twitter.com/kvane_tw"},
                                                           {"provider": "generic", "url": "https://kvane.example"}]),
              "/users/kestrel-vane": (200, PROFILE)})
found, checked, note = run(github, "username", "kestrel-vane")
f = found[0]
assert (f.url, f.attrs["fullname"], f.attrs["location"], checked) == ("https://github.com/kestrel-vane", "Robert Vance",
                                                                      "Tucson, AZ", 1), f
assert f.attrs["other_usernames"] == ["kvane_tw"] and f.attrs["links"] == ["https://kvane.example", "https://twitter.com/kvane_tw"]
assert "email" not in f.attrs and f.body
asked = len(seen)
run(github, "username", "kestrel-vane")
assert len(seen) == asked == 2, "second run should come from the cache"
assert run(github, "username", "nobody-here")[0] == []
asked = len(seen)
assert run(github, "username", "kestrel_vane88")[:2] == ([], 0) and len(seen) == asked  # underscores: not a GitHub login

# GitHub name search: reads profiles until the hourly quota runs out, and says so
seen = serve({"/search/users": (200, {"total_count": 3, "items": [{"login": "rvance"}, {"login": "bobv"}, {"login": "vr"}]}),
              "/users/rvance": (200, PROFILE | {"login": "rvance", "html_url": "https://github.com/rvance"}),
              "/users/bobv": (403, {"message": "API rate limit exceeded"}, {"x-ratelimit-remaining": "0"})})
found, _, note = run(github, "name", "Robert Vance")
assert len(found) == 1 and "found 3 users named 'Robert Vance'" in note and "rate-limited after 1" in note, note
assert seen[0].url.params["q"] == 'fullname:"Robert Vance" type:user'
seen = serve({"/search/users": (200, {"total_count": 0, "items": []})})
assert run(github, "email", EMAIL)[0] == [] and seen[0].url.params["q"] == f'"{EMAIL}" in:email type:user'

# Gravatar: profile by SHA-256 of the normalised email; hidden accounts stay hidden
SHA = hashlib.sha256(EMAIL.encode()).hexdigest()
seen = serve({SHA: (200, {"hash": SHA, "display_name": "Bob Vance", "profile_url": "https://gravatar.com/bobvance",
                          "avatar_url": f"https://0.gravatar.com/avatar/{SHA}", "location": "Tucson, AZ", "job_title": "",
                          "verified_accounts": [
                              {"service_label": "GitHub", "url": "https://github.com/kestrel-vane", "is_hidden": False},
                              {"service_label": "Mastodon", "url": "https://mastodon.example/@kv", "is_hidden": True}]})})
found, _, note = run(gravatar, "email", "RV@Example.com")
f = found[0]
assert (f.url, f.attrs["fullname"], f.attrs["other_usernames"]) == ("https://gravatar.com/bobvance", "Bob Vance", ["kestrel-vane"])
assert f.attrs["links"] == ["https://github.com/kestrel-vane"] and "job_title" not in f.attrs
assert f.attrs["gravatar_email_md5_hash"] == MD5 and "at most 4" in note
assert any("Gravatar hash matches" in r for r in score(Seed("email", EMAIL), f.url, f.attrs, [Seed("email", EMAIL)])[2])
serve({})
assert run(gravatar, "email", EMAIL)[0] == []
serve({SHA: (429, {"error": "Rate limit exceeded"}, {"retry-after": "3600"})})
assert "retry after 3600s" in raises(_api.Limited, gravatar, "email", EMAIL)

# Keybase: only live proofs of handles become linked usernames; one person found two ways is one finding
KB = {"basics": {"username": "kvane"}, "profile": {"full_name": "Bob Vance", "location": "Tucson"},
      "proofs_summary": {"all": [
          {"proof_type": "github", "nametag": "kestrel-vane", "state": 1, "service_url": "https://github.com/kestrel-vane"},
          {"proof_type": "twitter", "nametag": "kvane_old", "state": 7, "service_url": "https://twitter.com/kvane_old"},
          {"proof_type": "generic_web_site", "nametag": "kvane.example", "state": 1, "service_url": "https://kvane.example"}]}}
seen = serve({"usernames=kvane": (200, {"them": [KB]}), "github=kvane": (200, {"them": [KB]}),
              "twitter=kvane": (200, {"them": [None]})})
found, _, _ = run(keybase, "username", "kvane")
assert len(found) == 1 and len(seen) == 3, found
f = found[0]
assert f.attrs["other_usernames"] == ["kestrel-vane"] and f.attrs["matched_as"] == "Keybase username"
assert f.attrs["proofs"] == ["github: kestrel-vane", "generic_web_site: kvane.example"] and f.url == "https://keybase.io/kvane"
serve({})
assert run(keybase, "username", "kvane")[0] == []

# Bluesky: bare handles live under .bsky.social; a custom-domain handle is the owner's website
seen = serve({"getProfile": (200, {"did": "did:plc:abc", "handle": "kvane.example", "displayName": "Bob Vance",
                                   "description": "Birder"}),
              "searchActors": (200, {"actors": [{"did": "did:plc:1", "handle": "bob.bsky.social", "displayName": "Bob Vance"},
                                                {"did": "did:plc:2", "handle": "rv.bsky.social", "displayName": "R Vance"}]})})
f = run(bluesky, "username", "kvane.example")[0][0]
assert (f.url, f.attrs["website"], f.attrs["fullname"]) == ("https://bsky.app/profile/kvane.example", "https://kvane.example", "Bob Vance")
run(bluesky, "username", "KVane")
assert seen[-1].url.params["actor"] == "kvane.bsky.social"
found, _, _ = run(bluesky, "name", "Bob Vance")
assert len(found) == 2 and "website" not in found[0].attrs
serve({"getProfile": (400, {"error": "InvalidRequest", "message": "Profile not found"})})
assert run(bluesky, "username", "kvane")[0] == []


def account(user, host):
    return {"username": user, "acct": f"{user}@{host}", "display_name": "Bob Vance", "url": f"https://{host}/@{user}",
            "note": "<p>Birds &amp; maps</p>", "avatar": f"https://{host}/avatars/original/missing.png", "bot": False,
            "fields": [{"name": "Location", "value": "Tucson, AZ", "verified_at": None},
                       {"name": "Site", "value": '<a href="https://kvane.example" rel="me">kvane.example</a>',
                        "verified_at": "2026-01-01T00:00:00Z"},
                       {"name": "Code", "value": '<a href="https://github.com/kestrel-vane">github</a>', "verified_at": None}]}


# Mastodon: exact handles across instances; full handles go to their own instance only
seen = serve({"api/v2/search": (200, {"accounts": [account("kvane", "mastodon.social"), account("KVane", "fosstodon.org"),
                                                   account("kvane_fan", "mastodon.social")]})})
found, _, _ = run(mastodon, "username", "kvane")
assert [f.site for f in found] == ["Mastodon (mastodon.social)", "Mastodon (fosstodon.org)"], found
f = found[0]
assert (f.attrs["location"], f.attrs["bio"], f.attrs["verified_links"]) == ("Tucson, AZ", "Birds & maps", ["https://kvane.example"])
assert f.attrs["other_usernames"] == ["kestrel-vane"] and "image" not in f.attrs  # missing.png is the default avatar
assert seen[0].url.params["resolve"] == "false"
assert len(run(mastodon, "name", "Bob Vance")[0]) == 3
seen = serve({"/.well-known/webfinger": (200, {"links": [{"rel": "http://webfinger.net/rel/profile-page",
                                                          "href": "https://social.example/@kvane"}]}),
              "accounts/lookup": (200, account("kvane", "social.example"))})
found, _, _ = run(mastodon, "username", "kvane@social.example")
assert found[0].url == "https://social.example/@kvane" and {r.url.host for r in seen} == {"social.example"}
serve({"/.well-known/webfinger": (200, {"links": [{"rel": "http://webfinger.net/rel/profile-page",
                                                   "href": "https://social.example/@kvane"}]}),
       "accounts/lookup": (401, {"error": "This API requires an authenticated user"})})
f = run(mastodon, "username", "kvane@social.example")[0][0]
assert (f.site, f.url, f.attrs) == ("Fediverse (social.example)", "https://social.example/@kvane", {"acct": "kvane@social.example"})
serve({})
assert run(mastodon, "username", "kvane@social.example")[0] == []
serve({"api/v2/search": (429, {"error": "Too many requests"})})
raises(_api.Limited, mastodon, "name", "Bob Vance")


def se_user(name):
    return {"display_name": name, "link": "https://stackoverflow.com/users/1/x", "location": "Tucson, AZ",
            "profile_image": f"https://www.gravatar.com/avatar/{MD5}?s=256&d=identicon&r=PG", "reputation": 10,
            "creation_date": 1337166213}


# Stack Exchange: substring search for names, exact match for handles; Gravatar hash recovered from the picture
serve({"api.stackexchange.com": (200, {"items": [se_user("Bob Vance"), se_user("Bob Vance&#39;s Alt")],
                                       "quota_max": 300, "quota_remaining": 297})})
found, _, note = run(stackexchange, "name", "Bob Vance")
assert [f.attrs["fullname"] for f in found] == ["Bob Vance", "Bob Vance's Alt"] and "297 of 300" in note
assert found[0].attrs["gravatar_email_md5_hash"] == MD5 and found[0].attrs["created_at"] == "2012-05-16"
why = score(Seed("name", "Bob Vance"), found[0].url, found[0].attrs, [Seed("name", "Bob Vance"), Seed("email", EMAIL)])[2]
assert any(f"Gravatar hash matches {EMAIL}" in r for r in why), why
serve({"api.stackexchange.com": (200, {"items": [se_user("kvane"), se_user("kvane88")], "backoff": 0.2})})
assert [f.attrs["fullname"] for f in run(stackexchange, "username", "KVANE")[0]] == ["kvane"]
start = time.monotonic()
run(stackexchange, "username", "kvane")
assert time.monotonic() - start >= 0.15, "backoff not obeyed"
serve({"api.stackexchange.com": (400, {"error_id": 502, "error_name": "throttle_violation",
                                       "error_message": "too many requests from this IP"})})
assert "too many requests" in raises(_api.Limited, stackexchange, "name", "Bob Vance")

# keys.openpgp.org: RFC 9580's sample v4 key (fingerprint C959…5A9A) plus user IDs in both packet formats
RFC_KEY = base64.b64decode("xjMEU/NfCxYJKwYBBAHaRw8BAQdAPwmJlL3ZFu1AUxl5NOSofIBzOhKA1i+AEJkuQ+47JAY=")
new_uid = lambda t: bytes([0xC0 | 13, len(t)]) + t.encode()
old_uid = lambda t: bytes([0x80 | 13 << 2, len(t)]) + t.encode()
b64 = base64.b64encode(RFC_KEY + new_uid(f"Bob Vance (home) <{EMAIL}>") + old_uid("bob@work.example")).decode()
ARMOR = ("-----BEGIN PGP PUBLIC KEY BLOCK-----\nComment: fixture\n\n" + "\n".join(b64[i:i + 64] for i in range(0, len(b64), 64))
         + "\n=AbCd\n-----END PGP PUBLIC KEY BLOCK-----\n")
serve({"by-email/": (200, ARMOR)})
f = run(openpgp, "email", EMAIL)[0][0]
assert f.attrs["fingerprint"] == "C959BDBAFA32A2F89A153B678CFDE12197965A9A" and f.attrs["key_created"] == "2014-08-19", f.attrs
assert (f.attrs["fullname"], f.attrs["emails"]) == ("Bob Vance", ["bob@work.example", EMAIL])
assert f.url.endswith("/by-fingerprint/C959BDBAFA32A2F89A153B678CFDE12197965A9A")
long = "x" * 300  # two-octet new-format length
assert list(openpgp.packets(bytes([0xC0 | 13, 192 + (300 - 192 >> 8), 300 - 192 & 0xFF]) + long.encode())) == [(13, long.encode())]
serve({})
assert run(openpgp, "email", EMAIL)[0] == []

# Wayback: a username's big-platform profiles; only ever-working ones count; stops at a 429
CDX = [["timestamp", "statuscode"], ["20190105000000", "200"], ["20220301000000", "200"], ["20240101000000", "404"]]
seen = serve({"url=https://twitter.com/kvane&": (200, CDX),
              "url=https://www.instagram.com/kvane/": (200, [["timestamp", "statuscode"], ["20200101000000", "404"]]),
              "url=https://x.com/kvane": (200, [])})
found, checked, note = run(wayback, "username", "kvane")
assert len(found) == 1 and len(seen) == len(wayback.PROFILES) and checked == 0, (found, note)
assert found[0].attrs == {"archived_first": "2019-01-05", "archived_last": "2024-01-01", "last_status": "404",
                          "months_archived_working": 2, "archive": "https://web.archive.org/web/*/https://twitter.com/kvane",
                          "last_working_snapshot": "https://web.archive.org/web/20220301000000/https://twitter.com/kvane"}
seen = serve({"url=https://x.com/kvane": (429, "")})
found, _, note = run(wayback, "username", "kvane")
assert found == [] and len(seen) == 2 and f"1 of {len(wayback.PROFILES)}" in note and "rate-limited" in note, note
serve({"web.archive.org": (200, CDX)})
f = run(wayback, "url", "https://kvane.example/about")[0][0]
assert (f.site, f.url) == ("Wayback Machine", "https://kvane.example/about")


def contribution(**kw):
    return {"contributor_name": "VANCE, ROBERT J", "contributor_city": "TUCSON", "contributor_state": "AZ",
            "contributor_zip": "857011234", "contributor_employer": "SELF-EMPLOYED", "contributor_occupation": "CONSULTANT",
            "contribution_receipt_date": "2024-03-01T00:00:00", "contribution_receipt_amount": 250.0,
            "committee": {"name": "FRIENDS OF EXAMPLE"}, "pdf_url": "https://docquery.fec.gov/cgi-bin/fecimg/?1"} | kw


# FEC: one candidate per distinct donor record; DEMO_KEY unless the investigator supplies a key
seen = serve({"schedule_a": (200, {"pagination": {"count": 3}, "results": [
    contribution(), contribution(contribution_receipt_date="2022-10-01T00:00:00", contributor_zip="85701"),
    contribution(contributor_employer="UNIVERSITY OF EXAMPLE", contributor_occupation="PROFESSOR")]})})
found, _, note = run(fec, "name", "Robert Vance")
assert len(found) == 2 and len({f.url for f in found}) == 2 and "DEMO_KEY" in note, found
f = found[0]
assert (f.attrs["fullname"], f.attrs["location"], f.attrs["contributions"], f.attrs["total_usd"]) == \
       ("Robert J Vance", "Tucson, AZ", 2, 500.0)
assert (f.attrs["first_date"], f.attrs["last_date"]) == ("2022-10-01", "2024-03-01") and "contributor_zip=85701" in f.url
assert seen[0].url.params["api_key"] == "DEMO_KEY" and len(seen[0].url.params.get_list("two_year_transaction_period")) == 4
os.environ["HUNT_FEC_KEY"] = "my-own-key"
seen = serve({"schedule_a": (200, {"pagination": {"count": 0}, "results": []})})
assert run(fec, "name", "Robert Vance")[0] == [] and seen[0].url.params["api_key"] == "my-own-key"
del os.environ["HUNT_FEC_KEY"]
serve({"schedule_a": (429, {"error": {"code": "OVER_RATE_LIMIT"}})})
raises(_api.Limited, fec, "name", "Robert Vance")


def filing(cik, adsh, form):
    return {"_id": f"{adsh}:doc.htm", "_source": {"ciks": [cik], "display_names": [f"EXAMPLE {cik} CORP  (CIK {cik})"],
                                                  "form": form, "file_date": "2024-02-22", "adsh": adsh,
                                                  "biz_locations": ["Tucson, AZ"]}}


# EDGAR: the person as a filer ('Last First'), plus companies whose filings name them; declared User-Agent
seen = serve({"keysTyped": (200, {"hits": {"hits": [{"_id": "1234567", "_source": {"entity": "Vance Robert J"}}]}}),
              "submissions/CIK0001234567.json": (200, {"addresses": {"mailing": {"city": "TUCSON", "stateOrCountry": "AZ"}},
                                                       "filings": {"recent": {"form": ["4", "4", "3"]}}}),
              "search-index?q=": (200, {"hits": {"total": {"value": 3}, "hits": [
                  filing("0000820736", "0000950133-24-000742", "10-K"), filing("0000820736", "0000950133-24-000900", "DEF 14A"),
                  filing("0000999999", "0000999999-24-000001", "8-K")]}})})
found, _, note = run(edgar, "name", "Robert Vance")
assert seen[0].url.params["keysTyped"] == "Vance Robert" and len(found) == 3, (found, note)
assert (found[0].attrs["fullname"], found[0].attrs["location"], found[0].attrs["forms"]) == ("Vance Robert J", "Tucson, AZ", ["3", "4"])
assert "CIK=0001234567" in found[0].url and len(found[1].attrs["filings"]) == 2 and "ciks=0000820736" in found[1].url
assert found[1].attrs["filings"][0] == "10-K 2024-02-22: https://www.sec.gov/Archives/edgar/data/820736/000095013324000742/doc.htm"
assert all(r.headers["user-agent"] == edgar.UA for r in seen) and "github.com" not in edgar.UA  # SEC's firewall blocks it
os.environ["HUNT_SEC_UA"] = "Example PI LLC research@example.com"
seen = serve({"search-index": (200, {"hits": {"total": {"value": 0}, "hits": []}})})
assert run(edgar, "name", "Robert Vance")[0] == [] and seen[0].headers["user-agent"] == "Example PI LLC research@example.com"
del os.environ["HUNT_SEC_UA"]

# NPI registry: practice location, licences and former names; one-word names aren't searched
seen = serve({"npiregistry": (200, {"result_count": 1, "results": [{
    "number": "1234567890", "basic": {"first_name": "ROBERT", "middle_name": "J", "last_name": "VANCE", "credential": "PT"},
    "addresses": [{"address_purpose": "MAILING", "city": "PHOENIX", "state": "AZ"},
                  {"address_purpose": "LOCATION", "address_1": "1 EXAMPLE WAY", "city": "TUCSON", "state": "AZ",
                   "country_name": "United States", "telephone_number": "520-555-0143"}],
    "taxonomies": [{"desc": "Physical Therapist", "primary": True, "state": "AZ", "license": "PT0000"}],
    "other_names": [{"type": "Former Name", "first_name": "ROBERT", "last_name": "VANCEY"}]}]})})
f = run(npi, "name", "Robert J. Vance Jr.")[0][0]
assert (seen[0].url.params["first_name"], seen[0].url.params["last_name"]) == ("Robert", "Vance")
assert (f.attrs["fullname"], f.attrs["location"], f.attrs["licenses"], f.attrs["former_names"]) == \
       ("Robert J Vance", "Tucson, AZ", ["AZ PT0000"], ["Robert Vancey"])
assert f.url == "https://npiregistry.cms.hhs.gov/provider-view/1234567890"
asked = len(seen)
assert run(npi, "name", "Cher")[:2] == ([], 0) and len(seen) == asked
serve({"npiregistry": (200, {"Errors": [{"description": "No valid search criteria"}]})})
raises(ValueError, npi, "name", "Robert Vance")

# CourtListener: opt-in; with a token, RECAP dockets by party name and case law by caption
seen = serve({})
assert run(courtlistener, "name", "Robert Vance")[0] == [] and seen == []
os.environ["HUNT_COURTLISTENER_TOKEN"] = "test-token"
seen = serve({"type=r": (200, {"count": 1, "next": None, "results": [{
    "caseName": "Vance v. Example Corp", "court": "District Court, D. Arizona", "docketNumber": "4:24-cv-00001",
    "dateFiled": "2024-01-02", "docket_absolute_url": "/docket/1/vance-v-example-corp/", "party": ["Robert Vance", "Example Corp"]}]}),
              "type=o": (200, {"count": 30, "next": "https://www.courtlistener.com/api/rest/v4/search/?cursor=x", "results": [{
    "caseName": "State v. Vance", "court": "Court of Appeals of Arizona", "docketNumber": "2 CA-CR 2023-0001",
    "dateFiled": "2024-03-04", "citation": ["256 Ariz. 1"], "status": "Published", "absolute_url": "/opinion/2/state-v-vance/"}]})})
found, checked, note = run(courtlistener, "name", "Robert Vance")
docket, opinion = found
assert docket.url == "https://www.courtlistener.com/docket/1/vance-v-example-corp/" and docket.attrs["parties"] == ["Robert Vance", "Example Corp"]
assert (opinion.url, opinion.attrs["parties"], opinion.attrs["citation"], opinion.attrs["court"]) == \
       ("https://www.courtlistener.com/opinion/2/state-v-vance/", ["State", "Vance"], ["256 Ariz. 1"], "Court of Appeals of Arizona")
assert checked == 2 and "dockets with party 'Robert Vance': 1;" in note and "case law with 'Robert Vance' in the caption: 30, read the first page" in note, note
assert seen[0].headers["authorization"] == "Token test-token" and seen[0].url.params["q"] == 'party:"Robert Vance"'
assert dict(seen[1].url.params) == {"type": "o", "q": 'caseName:"Robert Vance"'}


def licence_rows(request):
    """Rows by dataset id, as each portal would answer the name query."""
    return {"7358-krk7": [{"owner_name": "VANCE, ROBERT J", "license_type": "A/C Technician", "license_number": "TACLA1",
                           "license_expiration_date_mmddccyy": "01312027", "business_city_state_zip": "TUCSON AZ 85701"},
                          {"owner_name": "VANCEY, ROBERT", "license_number": "TACLA2"}],  # not a VANCE: dropped
            "s7ft-44qi": [{"first_name": "ROBERT", "last_name": "VANCE", "full_name": "Vance, Robert J",
                           "license_type": "SALE", "license_number": "700001", "status": "Active", "county": "PIMA",
                           "original_license_date": "2019-04-01T00:00:00.000", "related_license_full_name": "Example Realty"}],
            "7s5z-vewr": [{"firstname": "Robert", "lastname": "Vance", "licensetype": "Plumber", "licensenumber": "PL.1",
                           "city": "DENVER", "state": "CO", "licensestatusdescription": "Active",
                           "linktoverifylicense": {"url": "https://apps.colorado.gov/dora/licensing/Lookup/1"}}],
            "m8qx-ubtq": [{"primaryprincipalname": "VANCE, ROBERT", "businessname": "VANCE BIRDING LLC",
                           "contractorlicensenumber": "VANCEBL001", "city": "SPOKANE", "state": "WA"}],
            "4xk5-x9j6": [{"principalname": "VANCE, ROBERT", "businessname": "VANCE BIRDING LLC",
                           "contractorlicensenumber": "VANCEBL001", "startdate": "2020-01-01T00:00:00.000"}]}


# Licences: one query per dataset; whole-name columns filtered to whole words; both WA tables share a record page
rows = licence_rows(None)
seen = serve({**{f"resource/{k}.json": (200, v) for k, v in rows.items()}, "pzzh-kp68": (500, {"message": "down"}),
              "data.delaware.gov": (429, {"message": "slow down"}), "/resource/": (200, [])})
found, checked, note = run(licences, "name", "Robert J. Vance Jr.")
by = {f.site: f for f in found}
assert len(found) == 5 and checked == 9, (len(found), checked, note)
tx = by["Texas TDLR licence"]
assert (tx.attrs["fullname"], tx.attrs["expires"], tx.attrs["roles"]) == ("VANCE, ROBERT J", "2027-01-31", ["licence holder"])
assert tx.url == "https://data.texas.gov/resource/7358-krk7.json?license_number=TACLA1"
trec = by["Texas real estate licence (TREC)"].attrs
assert (trec["location"], trec["sponsor"], trec["issued"]) == ("Pima County, TX", "Example Realty", "2019-04-01")
assert by["Colorado licence (DORA)"].attrs["verify"] == "https://apps.colorado.gov/dora/licensing/Lookup/1"
wa = [f for f in found if f.site == "Washington contractor licence (L&I)"]
assert len(wa) == 2 and wa[0].url == wa[1].url  # the scorer's URL grouping makes them one candidate
assert "Illinois licence (IDFPR) failed (HTTPStatusError)" in note and "Delaware licence rate-limited" in note, note
where = {r.url.path.split("/")[-1]: r.url.params["$where"] for r in seen}
assert where["s7ft-44qi.json"] == "(upper(last_name) = 'VANCE' and upper(first_name) like 'ROBERT%')", where
assert where["7358-krk7.json"] == "(upper(owner_name) like '%VANCE%' and upper(owner_name) like '%ROBERT%')"
assert all(r.url.params["$limit"] == str(_socrata.LIMIT) for r in seen)
seen = serve({"/resource/": (200, [])})
run(licences, "name", "Siobhan O'Vance")
assert "upper(last_name) = 'O''VANCE'" in seen[1].url.params["$where"]  # quotes escaped for SoQL
asked = len(seen)
assert run(licences, "name", "Cher")[:2] == ([], 0) and len(seen) == asked
os.environ["HUNT_SOCRATA_TOKEN"] = "app-token"
seen = serve({"/resource/": (200, [])})
run(fmcsa, "name", "Robert Vance")
assert seen[0].headers["x-app-token"] == "app-token"
del os.environ["HUNT_SOCRATA_TOKEN"]

# Businesses: a role from the row; one person in two roles is one record; CT business names joined in
seen = serve({"tckn-sxa6": (200, [{"first_name": "ROBERT", "last_name": "VANCE", "associated_name_type": "PRESIDENT",
                                   "business_name": "VANCE BIRDING INC", "registry_number": "123456-78", "city": "BEND",
                                   "state": "OR"},
                                  {"first_name": "ROBERT", "last_name": "VANCE", "associated_name_type": "SECRETARY",
                                   "business_name": "VANCE BIRDING INC", "registry_number": "123456-78"}]),
              "resource/ka36-64k6": (200, [{"firstname": "Robert", "lastname": "Vance", "designation": "Manager",
                                            "business_id": "B1", "residence_city": "HARTFORD", "residence_state": "CT"}]),
              "resource/n7gp-d28j": (200, [{"id": "B1", "name": "VANCE MAPS LLC", "status": "Active",
                                            "date_registration": "2021-05-01T00:00:00.000"}]),
              "n9v6-gdp6": (200, [{"chairman_name": "ROBERT VANCE", "current_entity_name": "VANCE HOLDINGS CORP",
                                   "dos_id": "999", "chairman_city": "ALBANY", "chairman_state": "NY",
                                   "location_city": "NEW YORK", "location_state": "NY"}]),
              "/resource/": (200, [])})
found, _, note = run(businesses, "name", "Robert Vance")
by = {f.site: f for f in found}
assert len(found) == 3, (found, note)
assert by["Oregon business (SOS)"].attrs["roles"] == ["president", "secretary"]
ct = by["Connecticut business (SOTS)"].attrs
assert (ct["business"], ct["location"], ct["registered"], ct["roles"]) == ("VANCE MAPS LLC", "Hartford, CT", "2021-05-01",
                                                                            ["manager"])
assert any(r.url.params.get("$where") == "id in ('B1')" for r in seen)
ny = by["New York corporation (DOS)"].attrs
assert (ny["fullname"], ny["location"], ny["business_location"], ny["roles"]) == ("ROBERT VANCE", "Albany, NY",
                                                                                  "New York, NY", ["chief executive"])

# FMCSA: an owner-operator under their own name, and an officer of someone else's carrier
serve({"az4n-8mr2": (200, [{"legal_name": "ROBERT J VANCE", "dot_number": "1234567", "status_code": "A",
                            "carrier_operation": "A", "power_units": "1", "total_drivers": "1", "phy_city": "TUCSON",
                            "phy_state": "AZ", "email_address": "RV@EXAMPLE.COM", "mcs150_date": "2026-03-02T00:00:00.000"},
                           {"legal_name": "EXAMPLE FREIGHT LLC", "company_officer_1": "ROBERT VANCE",
                            "company_officer_2": "DANA HOLT", "dot_number": "7654321", "status_code": "I"}])})
found, _, _ = run(fmcsa, "name", "Robert Vance")
own, officer = found
assert own.url == fmcsa.SAFER + "1234567" and own.attrs["roles"] == ["carrier (legal name)"]
assert (own.attrs["operation"], own.attrs["status"], own.attrs["email"], own.attrs["last_update"]) == \
       ("interstate", "active", EMAIL, "2026-03-02")
assert (officer.attrs["fullname"], officer.attrs["carrier"], officer.attrs["officers"], officer.attrs["status"]) == \
       ("ROBERT VANCE", "EXAMPLE FREIGHT LLC", ["ROBERT VANCE", "DANA HOLT"], "inactive")
assert any(f"profile lists {EMAIL}" in r for r in score(Seed("name", "Robert Vance"), own.url, own.attrs,
                                                         [Seed("name", "Robert Vance"), Seed("email", EMAIL)])[2])

# Courts: the person's side of a caption and their role; Chicago's respondent list and "C/O"; dates in DOB's shape;
# a tax warrant's own PDF is the record page; the matcher gets a city from each
seen = serve({"59kj-x8nc": (200, [{"litigationid": "L1", "respondent": "VANCE, ROBERT", "casetype": "Tenant Action", "boroid": "3",
                                   "housenumber": "100", "streetname": "EXAMPLE ST", "zip": "11201", "caseopendate": "2023-04-05T00:00:00.000",
                                   "casestatus": "CLOSED", "casejudgement": "YES", "penalty": "2500"}]),
              "pjgc-h7uv": (200, [{"matter_name": "VANCE, ROBERT VS CITY OF NEW YORK", "court_name": "Supreme Court - Kings",
                                   "docket_index": "001234/2022", "lit_start": "2022-01-02T00:00:00.000", "disposition": "Settlement"},
                                  {"matter_name": "DOE, JANE VS VANCE, ROBERT", "court_name": "US District Court - EDNY",
                                   "docket_index": "1:22-cv-9", "lit_start": "2022-03-04T00:00:00.000"}]),
              "y3hw-z6bm": (200, [{"case_number": "T1", "name": "Department of Sanitation v. Vance, Robert (01/02/2026)",
                                   "type": "Personnel", "category": "Section 75", "opened": "2025-11-27T00:00:00.000",
                                   "dispo_code": "32 - Sec 75 --Suspended"}]),
              "6bgk-3dad": (200, [{"ecb_violation_number": "E1", "respondent_name": "VANCE ROBERT", "respondent_house_number": "100",
                                   "respondent_street": "EXAMPLE ST", "respondent_city": "BROOKLYN", "respondent_zip": "11201", "issue_date": "20250922",
                                   "hearing_date": "20251103", "hearing_status": "IN VIOLATION", "ecb_violation_status": "ACTIVE",
                                   "penality_imposed": "800", "severity": "CLASS - 1"}]),
              "v7ua-z23v": (200, [{"warrant_id": "W1", "debtor_name_1": "ROBERT J VANCE", "debtor_name_2": "and/or",
                                   "debtor_name_3": "VANCE BIRDING LLC", "debtor_address_1": "1 STATE ST", "city": "ALBANY", "state": "NY", "zip_code": "12207", "county_code": "ALBANY",
                                   "status_code": "Added", "warrant_filed_amount": "1234.56",
                                   "warrant_filed_date": "2026-10-01T00:00:00.000",
                                   "url": {"url": "https://www.tax.ny.gov/warrants/lookup.html?document=e-1-w001.pdf"}}]),
              "etc6-cwcf": (200, [{"casenbr": "2026-00001AD", "style": "ROBERT VANCE Plaintiff v. OHIO DEPARTMENT OF TRANSPORTATION Defendant",
                                   "utypename": "Administrative Determination", "fileddate": "2026-10-28T00:00:00.000",
                                   "casestatdesc": "ACTIVE PENDING"},
                                  {"casenbr": "2026-00001AD", "style": "ROBERT VANCE Plaintiff v. OHIO DEPARTMENT OF TRANSPORTATION Defendant",
                                   "utypename": "Administrative Determination"}]),  # the portal repeats a case per party
              "6br9-quuz": (200, [{"docket_number": "26BT1", "respondents": "VANCE HOLDINGS LLC C/O VANCE, ROBERT | DANA HOLT",
                                   "issuing_department": "Buildings", "hearing_date": "2026-10-29T00:00:00.000",
                                   "case_disposition": "Liable", "imposed_fine": "1500", "address": "100 S EXAMPLE AVE"}]),
              "7ift-kbgd": (200, [{"case_no": "C1", "respondent_name": "Robert Vance dba Vance Trucking",
                                   "district_court_docket_no": "D-1-GN-26-000001", "county": "TRAVIS",
                                   "order_date": "2026-02-03T00:00:00.000", "penalty_assessed": "5000"}])})
found, checked, note = run(courts, "name", "Robert J. Vance Jr.")
by = {f.site: f for f in found}
assert len(found) == 9 and checked == 8, (len(found), checked, note)
hpd = by["New York City Housing Court case (HPD)"].attrs
assert (hpd["fullname"], hpd["roles"], hpd["location"], hpd["address"], hpd["filed"], hpd["judgment"]) == \
       ("VANCE, ROBERT", ["respondent"], "Brooklyn, NY", "100 Example St, Brooklyn, NY 11201", "2023-04-05", "YES")
law = [f for f in found if f.site == "New York City civil litigation (Law Department)"]
assert [(f.attrs["fullname"], f.attrs["roles"], f.attrs.get("location")) for f in law] == \
       [("VANCE, ROBERT", ["plaintiff"], "Brooklyn, NY"), ("VANCE, ROBERT", ["defendant"], None)]
assert law[0].url == "https://data.cityofnewyork.us/resource/pjgc-h7uv.json?docket_index=001234%2F2022&court_name=Supreme+Court+-+Kings"
oath = by["New York City OATH trial"].attrs
assert (oath["fullname"], oath["roles"], oath["case_type"], oath["docket_number"], oath["employer"]) == ("Vance, Robert", ["respondent"], "Personnel Section 75", "T1", "Department of Sanitation")
ecb = by["New York City OATH/ECB summons (DOB)"].attrs
assert (ecb["issued"], ecb["hearing"], ecb["location"], ecb["address"], ecb["penalty"]) == ("2025-09-22", "2025-11-03", "Brooklyn, NY", "100 Example St, Brooklyn, NY 11201", "800")
tax = by["New York State tax warrant"]
assert tax.url == "https://www.tax.ny.gov/warrants/lookup.html?document=e-1-w001.pdf"
assert (tax.attrs["fullname"], tax.attrs["roles"], tax.attrs["co_debtors"], tax.attrs["location"], tax.attrs["amount"], tax.attrs["address"]) == \
       ("ROBERT J VANCE", ["debtor"], ["VANCE BIRDING LLC"], "Albany, NY", "1234.56", "1 State St, Albany, NY 12207")
ohio = by["Ohio Court of Claims case"].attrs
assert (ohio["fullname"], ohio["roles"], ohio["docket_number"], ohio["case_type"]) == ("ROBERT VANCE", ["plaintiff"], "2026-00001AD", "Administrative Determination")
chi = by["Chicago administrative hearing"].attrs
assert (chi["fullname"], chi["business"], chi["respondents"], chi["disposition"], chi["address"]) == \
       ("VANCE, ROBERT", "VANCE HOLDINGS LLC", ["VANCE HOLDINGS LLC C/O VANCE, ROBERT", "DANA HOLT"], "Liable", "100 S Example Ave, Chicago, IL")
assert "employer" not in hpd and all(k not in f.attrs for f in found for k in ("dob", "age"))  # no open court table shows a birth date
tceq = by["Texas TCEQ civil judgment"].attrs
assert (tceq["fullname"], tceq["location"], tceq["docket_number"], tceq["ordered"]) == ("Robert Vance dba Vance Trucking", "Travis County, TX", "D-1-GN-26-000001", "2026-02-03")
assert "searched 8 of 8 datasets" in note and "New York State tax warrant 1" in note, note
assert "debtor_name_4" in next(r.url.params["$where"] for r in seen if "v7ua-z23v" in str(r.url))
assert all("caption" not in f.attrs for f in found)
assert any("name 'VANCE, ROBERT' matches" in r for r in score(Seed("name", "Robert Vance"), law[0].url, law[0].attrs, [Seed("name", "Robert Vance")])[2])
assert courts._party("Doe v. Vance, Robert", "VANCE") == ("Vance, Robert", None, 1)
assert courts._party("JOHN RITTER Requester v. VILLAGE Respondent", "RITTER") == ("JOHN RITTER", "requester", 0)

# Court portals the investigator opens by hand: national links for every name, state portals from location seeds
links = courts.search_links([Seed("name", "Robert Vance"), Seed("location", "Houston, TX"), Seed("address", "1 Main St, Tucson Arizona 85701")])
assert links[0] == {"label": 'CourtListener: federal dockets (RECAP) with party "Robert Vance"',
                    "url": "https://www.courtlistener.com/?type=r&q=party%3A%22Robert+Vance%22", "state": None}
assert [l["state"] for l in links] == [None] * 3 + ["TX"] * len(courts.PORTALS["TX"]) + ["AZ"] * len(courts.PORTALS["AZ"])
assert any(l["label"] == "Harris County district courts" for l in links)
assert courts.search_links([Seed("location", "Houston, TX")]) == []  # nothing to search without a name
assert [l["state"] for l in courts.search_links([Seed("name", "Robert Vance")])] == [None] * 3
ok = courts.search_links([Seed("name", "Robert Vance"), Seed("location", "Tulsa, OK")])[-1]
assert ok["url"] == "https://www.oscn.net/dockets/Results.aspx?db=all&lname=Vance&fname=Robert", ok
assert courts.states_in([Seed("location", "Washington, DC"), Seed("location", "Seattle, Washington"), Seed("location", "Portland OR 97201"),
                         Seed("location", "Office in Denver"), Seed("username", "or"), Seed("location", "Hartford, Connecticut"),
                         Seed("address", "1 Main St, Memphis TN 38103")]) == ["DC", "WA", "OR", "CT", "TN"]
assert len(courts.PORTALS) == 47 and {"NH", "VT", "WV", "WY"}.isdisjoint(courts.PORTALS)  # not yet: no live portal URL found
assert all(u.startswith("https://") for ps in courts.PORTALS.values() for _, u in ps) and set(courts.PORTALS) <= set(courts.STATES)

# Health: HEAD, GET when HEAD isn't served, throttling and outages reported, keys reported (never their values)
seen = serve({"HEAD api.github.com/rate_limit": (404, {}), "api.github.com/rate_limit": (200, {}),
              "mastodon.social": (429, {}), "keys.openpgp.org": httpx.ConnectError("no route"),
              "npiregistry": (503, ""), "data.texas.gov/api/views/7358-krk7": (404, {}), "": (200, {})})
os.environ["HUNT_GITHUB_TOKEN"] = "secret-value"
court_token = os.environ.pop("HUNT_COURTLISTENER_TOKEN")
rows = {r["source"]: r for r in asyncio.run(registry.health())}
del os.environ["HUNT_GITHUB_TOKEN"]
os.environ["HUNT_COURTLISTENER_TOKEN"] = court_token  # the proxy check below needs it
assert list(rows) == [s.NAME for s in SOURCES]
assert rows["github"]["ready"] and rows["github"]["key_set"] and "secret-value" not in str(rows)
assert [r.method for r in seen if r.url.host == "api.github.com"] == ["HEAD", "GET"]
assert rows["mastodon"]["detail"].endswith("rate-limited right now") and not rows["mastodon"]["ready"]
assert rows["openpgp"]["detail"].endswith("unreachable (ConnectError)") and rows["openpgp"]["reachable"] is False
assert rows["npi"]["detail"].endswith("server error 503")
assert not rows["licences"]["reachable"] and "7358-krk7.json: not found (404)" in rows["licences"]["detail"]
assert rows["businesses"]["ready"] and len(rows["businesses"]["checks"]) == len(businesses.DATASETS)
assert rows["courtlistener"]["reachable"] and not rows["courtlistener"]["ready"]  # its key is required and unset
assert rows["phonenumbers"]["reachable"] is None and rows["phonenumbers"]["ready"]
assert {k: rows[k]["key_status"] for k in ("github", "courtlistener", "fec", "edgar", "phonenumbers")} == {
    "github": "set", "courtlistener": "not set (required)", "fec": "not set (free key available)",
    "edgar": "not set (optional)", "phonenumbers": "none needed"}
assert rows["fec"]["key_url"] == fec.KEY_URL and rows["licences"]["key_free"] == _socrata.KEY_FREE
assert all(r["key_url"].startswith("https://") for r in rows.values() if r["key_status"].endswith("free key available)"))
assert next(r for r in seen if r.url.host == "efts.sec.gov").headers["user-agent"] == edgar.UA


# Proxy: every new source's first connection goes to HUNT_PROXY (a fake one here that refuses everything)
async def proxy_lines(make):
    """Run make() with HUNT_PROXY pointing at a fake proxy; return the first line of each connection it got."""
    lines = []

    async def refuse(reader, writer):
        lines.append((await reader.readline()).decode().strip())
        writer.write(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n\r\n")
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(refuse, "127.0.0.1", 0)
    os.environ["HUNT_PROXY"] = f"http://127.0.0.1:{server.sockets[0].getsockname()[1]}"
    try:
        await make()
    except httpx.HTTPError:
        pass
    finally:
        del os.environ["HUNT_PROXY"]
        server.close()
    return lines


for m in CLIENTS:
    m.client = REAL_CLIENT
name, handle = Seed("name", "Robert Vance"), Seed("username", "kvane")
for mod, seed, host in [(github, Seed("username", "proxy-check"), "api.github.com"),
                        (gravatar, Seed("email", EMAIL), "api.gravatar.com"), (keybase, handle, "keybase.io"),
                        (bluesky, handle, "public.api.bsky.app"), (mastodon, name, "mastodon.social"),
                        (mastodon, Seed("username", "kvane@social.example"), "social.example"),
                        (stackexchange, name, "api.stackexchange.com"), (openpgp, Seed("email", EMAIL), "keys.openpgp.org"),
                        (wayback, Seed("url", "https://kvane.example"), "web.archive.org"), (fec, name, "api.open.fec.gov"),
                        (edgar, name, "efts.sec.gov"), (npi, name, "npiregistry.cms.hhs.gov"),
                        (courtlistener, name, "www.courtlistener.com"), (fmcsa, name, "data.transportation.gov")]:
    lines = asyncio.run(proxy_lines(lambda: mod.search(seed)))
    assert lines and lines[0].startswith(f"CONNECT {host}:443 "), (mod.NAME, lines)
for mod in (licences, businesses, courts):  # every dataset's portal, all through the proxy
    lines = asyncio.run(proxy_lines(lambda: mod.search(name)))
    assert sorted(lines) == sorted(f"CONNECT {d.domain}:443 HTTP/1.1" for d in mod.DATASETS), (mod.NAME, lines)
lines = asyncio.run(proxy_lines(registry.health))
probed = {u for s in SOURCES for u in ([s.HEALTH] if isinstance(getattr(s, "HEALTH", None), str) else getattr(s, "HEALTH", []))}
assert len(lines) >= len(probed) and all(l.startswith("CONNECT ") for l in lines), lines
del os.environ["HUNT_COURTLISTENER_TOKEN"]

if "--live" in sys.argv:  # a few real logged-out calls: public organisations, example.com, or nobody's name
    for mod, kind, value in [(github, "username", "nasa"), (bluesky, "username", "bsky.app"),
                             (mastodon, "username", "Mastodon@mastodon.social"), (wayback, "url", "https://github.com/nasa"),
                             (gravatar, "email", "test@example.com"), (openpgp, "email", "test@example.com"),
                             (keybase, "username", "zzyzxquuxington"), (stackexchange, "name", "Zzyzx Quuxington"),
                             (fec, "name", "Zzyzx Quuxington"), (edgar, "name", "Zzyzx Quuxington"),
                             (npi, "name", "Zzyzx Quuxington"), (courts, "name", "Zzyzx Quuxington")]:  # not Bluesky: its search matches any one word
        found, checked, note = run(mod, kind, value)
        print(f"{mod.NAME:>14}  {kind}={value}: {len(found)} found; {note}")

print("ok")
