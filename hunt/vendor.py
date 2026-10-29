"""Instagram and Facebook public posts through Apify, on the investigator's own key: an opt-in vendor connector.

Hunt runs free by default. Without a key nothing here runs, and the note says where those posts come from instead
(the Hunt Browser). With one, Apify's own pay-per-event Actors fetch a public account's posts and Hunt stores them
like any other posts, marked origin 'vendor', with vendor, Actor, build, run id and cost in the audit log, so the
report can say "N posts obtained through Apify under the investigator's own account". Built to live inside the
free plan's $5 a month: results_limit newest posts an account on the first read and only newer ones after that
(the Actors' onlyPostsNewerThan), no re-read of an account fetched within fresh_days unless asked, the estimate
and the credit left shown before a run (plan()), a hard per-run charge cap (Apify's maxTotalChargeUsd) and a
monthly cap. Prices, terms and the date they were checked: docs/research/vendors.md.

Settings live in HUNT_HOME/vendor.json, never in a case, mode 600:
  apify_key        the investigator's token (HUNT_APIFY_KEY overrides); never shipped, never shown back
  actors           {"instagram": "apify~instagram-post-scraper", "facebook": "apify~facebook-posts-scraper"}
                   (HUNT_APIFY_ACTORS, a JSON object, overrides): any Actor taking the same inputs can be swapped in
  price_per_post   per-post prices used for estimates and the per-run cap; they change, so they're settings
  monthly_cap_usd  Hunt's own ceiling, under the plan's; results_limit; fresh_days
Only the accounts the investigator marked as the subject's are passed in, as for every collector.
"""

import asyncio
import json
import os
from datetime import UTC, datetime
from urllib.parse import urlparse

import httpx

from . import posts
from .case import HOME
from .seed import Seed, now

API = "https://api.apify.com/v2"
NAMES = {"instagram": "Instagram (via Apify)", "facebook": "Facebook (via Apify)"}
DEFAULTS = {"apify_key": "", "actors": {"instagram": "apify~instagram-post-scraper", "facebook": "apify~facebook-posts-scraper"},
            "price_per_post": {"instagram": 0.0017, "facebook": 0.007},  # free-plan prices on 2026-10-29 (FB: $5 + $2 date filter per 1,000)
            "monthly_cap_usd": 5.0, "results_limit": 100, "fresh_days": 7}
POLL = 60  # seconds the API waits per status call (its maximum)
SETTLE = 10  # seconds before the final cost read: the first figures after a run are preliminary
TIMEOUT = 900  # one run, in seconds
HEADROOM = 1.25  # the per-run charge cap, over the estimate
NO_KEY = "Apify key not set; Instagram and Facebook posts come from the Hunt Browser"


def settings() -> dict:
    s = json.loads(json.dumps(DEFAULTS))
    try:
        saved = json.loads((HOME / "vendor.json").read_text())
    except (OSError, ValueError):
        saved = {}
    for k, v in saved.items():
        if k in DEFAULTS:
            s[k] = s[k] | v if isinstance(DEFAULTS[k], dict) else v
    if os.environ.get("HUNT_APIFY_KEY"):
        s["apify_key"] = os.environ["HUNT_APIFY_KEY"]
    if os.environ.get("HUNT_APIFY_ACTORS"):
        s["actors"] |= json.loads(os.environ["HUNT_APIFY_ACTORS"])
    return s


def save_settings(**changes) -> dict:
    """Store settings under HUNT_HOME (apify_key "" removes the key). Returns them as shown() does."""
    file = HOME / "vendor.json"
    saved = json.loads(file.read_text()) if file.exists() else {}
    for k, v in changes.items():
        if k not in DEFAULTS:
            raise ValueError(f"unknown setting {k}")
        saved[k] = (saved.get(k) or {}) | v if isinstance(DEFAULTS[k], dict) else v
    HOME.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps(saved, indent=1))
    file.chmod(0o600)
    return shown()


def shown() -> dict:
    """The settings for the app: whether a key is set, never the key itself."""
    return settings() | {"apify_key": bool(settings()["apify_key"])}


def site(url: str) -> str | None:
    host = urlparse(url).netloc.lower()
    return next((k for k in NAMES if host == f"{k}.com" or host.endswith(f".{k}.com")), None)


async def plan(case, accounts: list[dict], since: str | None = None, force: bool = False) -> dict:
    """What a run would do and cost, for the app to show before it starts:
    {key_set, run: [account + newer_than + estimate_usd], skipped: [account + why], estimate_usd, spent_usd,
     credit_left_usd, plan_max_usd, cap_usd, cycle_ends, ok, why}. ok is False, with the reason in why, when nothing may run."""
    s = settings()
    out = {"key_set": bool(s["apify_key"]), "run": [], "skipped": [], "estimate_usd": 0.0, "spent_usd": None, "credit_left_usd": None,
           "plan_max_usd": None, "cap_usd": s["monthly_cap_usd"], "cycle_ends": None, "ok": False, "why": ""}
    for a in accounts:
        k = site(a["url"])
        if not k:
            continue
        if not s["apify_key"]:
            out["skipped"].append(a | {"why": NO_KEY})
            continue
        last = _last_read(case, k, a["url"])
        if last and not force and (datetime.now(UTC) - datetime.fromisoformat(last)).days < s["fresh_days"]:
            out["skipped"].append(a | {"why": f"read on {last[:10]}; not run again within {s['fresh_days']} days unless you ask"})
            continue
        cost = round(s["results_limit"] * s["price_per_post"][k], 3)
        out["run"].append(a | {"newer_than": since or last, "estimate_usd": cost})
        out["estimate_usd"] = round(out["estimate_usd"] + cost, 3)
    if not out["run"]:
        out["why"] = "nothing to run"
        return out
    try:
        out |= await _usage(s)
    except (httpx.HTTPError, ValueError) as e:
        out["why"] = f"Apify usage check failed: {e}"
        return out
    left = round(min(out["cap_usd"], out["plan_max_usd"]) - out["spent_usd"], 2)
    out["ok"] = out["estimate_usd"] <= left
    out["why"] = (f"this run ≈ ${out['estimate_usd']:.2f} · about ${out['credit_left_usd']:.2f} of this month's credit left"
                  f" (${left:.2f} under Hunt's ${out['cap_usd']:.2f} cap)" if out["ok"] else
                  f"this run ≈ ${out['estimate_usd']:.2f} would pass the cap: ${out['spent_usd']:.2f} spent of ${out['cap_usd']:.2f}"
                  f" (${out['credit_left_usd']:.2f} credit left until {out['cycle_ends'][:10]})")
    return out


async def collect(case, accounts: list[dict], since: str | None, emit, force: bool = False) -> int:
    """Read the accounts' public posts through Apify into the case, origin 'vendor'. Returns posts added.
    Runs only what plan() allows; every run's cost is audited. Same events as posts.collect."""
    case.db.executescript(posts.SCHEMA)
    s, p, added = settings(), await plan(case, accounts, since, force), 0
    for a in p["skipped"]:
        emit({"type": "source", "source": NAMES[site(a["url"])], "seed": a["url"], "status": "failed" if not p["key_set"] else "nothing found",
              "found": 0, "checked": 0, "note": a["why"]})
    if not p["run"]:
        return 0
    spent = p["spent_usd"]  # None only when the usage check failed; the cap is checked per account below
    async with _client() as client:
        for a in p["run"]:
            k, url = site(a["url"]), a["url"]
            emit({"type": "source", "source": NAMES[k], "seed": url, "status": "running", "found": 0, "checked": 0, "note": ""})
            found, items, run = 0, [], {}
            try:
                if spent is None:  # the usage check failed: nothing starts
                    raise ValueError(p["why"])
                if spent + a["estimate_usd"] > min(s["monthly_cap_usd"], p["plan_max_usd"]):
                    raise ValueError(f"monthly cap: ${spent:.2f} spent, this run ≈ ${a['estimate_usd']:.2f}, cap ${s['monthly_cap_usd']:.2f}")
                items, run = await _fetch(client, s, k, url, a["newer_than"])
                spent += run.get("usageTotalUsd") or 0
                for item in items:
                    found += await _save(case, client, k, url, item)
                posts._seen(case, NAMES[k], items)
                status, note = "found" if found else "nothing found", _note(k, s, items, a["newer_than"], run)
                if run.get("status") != "SUCCEEDED":
                    raise ValueError(f"Apify run {run.get('id')} ended {run.get('status')}: {run.get('statusMessage') or ''}")
            except (httpx.HTTPError, ValueError, KeyError) as e:
                status, note = "failed", f"{type(e).__name__}: {str(e)[:300]}"
            if run:
                case.audit("vendor run", {"vendor": "Apify", "actor": s["actors"][k], "build": run.get("buildNumber"), "run_id": run.get("id"),
                                          "status": run.get("status"), "cost_usd": run.get("usageTotalUsd"), "account": url,
                                          "newer_than": a["newer_than"], "posts": len(items), "started": run.get("startedAt"),
                                          "finished": run.get("finishedAt")})
            case.add_run(f"apify-{k}", Seed("url", url), status, found, len(items), note)
            emit({"type": "source", "source": NAMES[k], "seed": url, "status": status, "found": found, "checked": len(items), "note": note})
            added += found
    case.audit("vendor posts collected", {"vendor": "Apify", "accounts": [a["url"] for a in p["run"]], "added": added, "spent_usd": spent})
    return added


async def _fetch(client, s, k, url, newer_than) -> tuple[list[dict], dict]:
    """Start the Actor, wait for it, read its dataset: (items, the settled run record)."""
    actor, limit, auth = s["actors"][k], s["results_limit"], _auth(s)
    body = {"instagram": {"username": [url], "resultsLimit": limit}, "facebook": {"startUrls": [{"url": url}], "resultsLimit": limit}}[k]
    if newer_than:
        body["onlyPostsNewerThan"] = newer_than[:19]
    cap = round(limit * s["price_per_post"][k] * HEADROOM + 0.01, 2)  # Apify stops the run at this charge
    r = await client.post(f"{API}/acts/{actor}/runs", params={"maxTotalChargeUsd": cap, "timeout": TIMEOUT}, json=body, headers=auth)
    if r.status_code != 201:
        raise ValueError(f"Apify wouldn't start {actor}: HTTP {r.status_code} {_error(r)}")
    run, started = r.json()["data"], asyncio.get_running_loop().time()
    while run["status"] in ("READY", "RUNNING", "TIMING-OUT", "ABORTING"):
        if asyncio.get_running_loop().time() - started > TIMEOUT + 120:
            await client.post(f"{API}/actor-runs/{run['id']}/abort", headers=auth)
            raise ValueError(f"Apify run {run['id']} took longer than {TIMEOUT} s; aborted")
        run = (await client.get(f"{API}/actor-runs/{run['id']}", params={"waitForFinish": POLL}, headers=auth)).json()["data"]
    await asyncio.sleep(SETTLE)
    run = (await client.get(f"{API}/actor-runs/{run['id']}", headers=auth)).json()["data"]
    r = await client.get(f"{API}/datasets/{run['defaultDatasetId']}/items", params={"clean": "true", "format": "json"}, headers=auth)
    if r.status_code != 200:
        raise ValueError(f"Apify dataset of run {run['id']}: HTTP {r.status_code} {_error(r)}")
    return [_item(k, x) for x in r.json()], run


def _item(k: str, x: dict) -> dict:
    """An Actor's dataset item → the posts.py fetcher shape."""
    if k == "instagram":
        nodes = x.get("childPosts") or [x]
        media = [("video", n["videoUrl"]) if n.get("videoUrl") else ("image", n.get("displayUrl")) for n in nodes]
        return {"url": x.get("url") or f"https://www.instagram.com/p/{x.get('shortCode')}/", "posted_at": x.get("timestamp"),
                "text": x.get("caption") or "", "media": [m for m in media if m[1]]}
    media = []
    for m in x.get("media") or []:
        if video := next((m[f] for f in ("playable_url", "video_url", "videoUrl") if m.get(f)), None):
            media.append(("video", video))
        elif uri := ((m.get("photo_image") or {}).get("uri") or m.get("thumbnail")):
            media.append(("image", uri))
    return {"url": x["url"], "posted_at": x.get("time"), "text": x.get("text") or "", "media": media}


async def _save(case, client, k, account_url, item) -> int:
    """Store one vendor post and fetch its media from the platform's CDN. 0 if the post was already in the case."""
    cur = case.db.execute("insert or ignore into posts values (null, ?, ?, ?, ?, ?, 'vendor', ?)",
                          (NAMES[k], account_url, item["url"], item["posted_at"], item["text"], now()))
    if not cur.rowcount:
        return 0
    for kind, src in item["media"]:
        try:
            file, sha = await posts._download(case, client, src)
        except (httpx.HTTPError, ValueError) as e:
            case.audit("media not saved", {"url": src, "error": f"{type(e).__name__}: {str(e)[:200]}"})
            continue
        case.db.execute("insert into media values (null, ?, ?, ?, ?, ?, ?)",
                        (cur.lastrowid, kind, file, sha, posts.duration(case.dir / file) if kind == "video" else None, src))
    return 1


async def _usage(s) -> dict:
    """This month's spend and credit, from the account's limits endpoint."""
    async with _client() as client:
        r = await client.get(f"{API}/users/me/limits", headers=_auth(s))
    if r.status_code != 200:
        raise ValueError(f"HTTP {r.status_code} from Apify ({_error(r) or 'check the key'})")
    d = r.json()["data"]
    spent, plan_max = d["current"]["monthlyUsageUsd"], d["limits"]["maxMonthlyUsageUsd"]
    return {"spent_usd": spent, "credit_left_usd": round(plan_max - spent, 2), "plan_max_usd": plan_max,
            "cycle_ends": d["monthlyUsageCycle"]["endAt"]}


def _note(k, s, items, newer_than, run) -> str:
    return (f"{NAMES[k]}: {len(items)} posts" + (f" newer than {newer_than[:10]}" if newer_than else f" (the newest {s['results_limit']})")
            + f", fetched by Actor {s['actors'][k]} build {run.get('buildNumber')} (run {run.get('id')}, "
            f"${run.get('usageTotalUsd') or 0:.3f} charged to the investigator's own Apify account). Media are fetched from the "
            "platform's CDN and hashed here")


def _last_read(case, k, url) -> str | None:
    row = case.db.execute("select max(ts) from runs where source = ? and seed = ? and status in ('found', 'nothing found')",
                          (f"apify-{k}", url)).fetchone()
    return row[0] if row else None


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=120, follow_redirects=True, headers={"User-Agent": posts.UA}, proxy=os.environ.get("HUNT_PROXY"))


def _auth(s) -> dict:
    return {"Authorization": f"Bearer {s['apify_key']}"}  # a header, so the key is never in a URL, a log or an error


def _error(r) -> str:
    try:
        return r.json()["error"]["message"]
    except (ValueError, KeyError, TypeError):
        return ""
