"""The demo case: a finished, fictional investigation anyone opening Hunt can look through in thirty seconds.

`hunt demo` (or the first-run screen's "Open the demo case") builds case `demo-dorian-vell` from fixtures/demo/
alone, with no network. It's an insurance claim against Dorian Vell, a mover who reported a back injury. It has:
  - the search: every source run, accounts with verdicts and reasons, two namesakes set aside, public records
    (one a namesake the record's own birth year rules out), and screenshots
  - the confirmed person
  - posts read automatically and captured in the Hunt Browser, with photos and a short video
  - flags from the scan, reviewed: in the report, kept, not relevant
  - a Check-again change (a post deleted, a bio rewritten), notes and a corrected note
  - a finished report and evidence bundle in its exports/ folder

Every person, account, post, employer and record in it is invented, and it says DEMO everywhere: the label,
purpose, client, reference and file number, meta 'demo', every picture ("DEMO · generated illustration"), the
report (made with DEMO report settings, so no real investigator's name or licence is on it) and the bundle.
Accounts live on .example hosts, which never resolve, so no click can reach a real person who shares a handle.
The case is closed when built (no search, scan or re-check runs on it); `hunt demo --reset` moves it to the
Trash and builds it again.
"""

import json
from pathlib import Path

from PIL import Image

from . import bundle, inbox, notes, photo, posts, recheck, report, scan, search
from .case import HOME, Case
from .seed import Finding, Seed, now

SLUG = "demo-dorian-vell"
LABEL = "DEMO · Dorian Vell claim (fictional)"
PURPOSE = ("DEMO: a fictional workers' compensation claim, made to show how Hunt works. Every person, account, post "
           "and record in it is invented.")
DETAILS = {"label": LABEL, "kind": "insurance", "reference": "DEMO-0001", "client": "DEMO Mutual (fictional insurer)",
           "adjuster": "A. Example (fictional)", "file_number": "DEMO-0001", "assignment_date": "2026-04-01",
           "injury_date": "2026-03-02", "subject_dob": "1988-05-14",
           "limits": "No lifting over 10 lb and no repeated bending, from the injury date (fictional)",
           "look_for": ["lifting", "sport", "walks", "injury"], "tool": "person",
           "recommendations": "DEMO: fictional. In a real case, the investigator's recommendations would go here."}
PREFS = {"firm": "DEMO Investigations (fictional)", "investigator": "A. Demo (fictional investigator)",
         "licence": "DEMO-0000", "contact": "demo@example.com", "timezone": "America/Phoenix", "logo": False,
         "confidentiality": "DEMO: a fictional case made to show Hunt. Not a real investigation; every person, "
                            "account and record in it is invented."}
MEDIA = next((p for p in (Path(__file__).parent / "demo_media", Path(__file__).resolve().parent.parent / "fixtures" / "demo")
              if p.is_dir()), None)
BSKY, IG, TT = "https://bsky.example/profile/dorianvell", "https://instagram.example/dorianvell/", "https://tiktok.example/@dorianvell"


def build(reset: bool = False) -> Case:
    """The demo case, built if it isn't here (or again, with `reset`: the old one goes to the Trash)."""
    folder = HOME / "cases" / SLUG
    if (folder / "case.db").exists():
        if not reset:
            return Case.open(SLUG)
        inbox._trash(folder)
    if not MEDIA:
        raise FileNotFoundError("the demo's pictures aren't installed with this copy of Hunt (fixtures/demo)")
    case = Case(SLUG, PURPOSE)
    case.db.execute("insert or replace into meta values ('demo', ?)", (now(),))
    case.set_details(**DETAILS)
    seeds = [Seed("name", "Dorian Vell"), Seed("username", "dorianvell"), Seed("email", "dorian.vell@example.com"),
             Seed("dob", "1988-05-14"), Seed("employer", "Vell Moving & Hauling")]
    case.add_seeds(seeds)
    case.audit("case details", {k: v for k, v in DETAILS.items()} | {"seeds": [s.__dict__ for s in seeds]})
    _search(case, seeds)
    _decide(case)
    shot_posts = _posts(case)
    _scan(case, shot_posts)
    _check_again(case, shot_posts)
    _notes(case)
    _hand_over(case)
    case.close("DEMO: a fictional case, read-only. `hunt demo --reset` builds it again.")
    return case


def is_demo(case) -> bool:
    return bool(case.meta("demo"))


def compose(case) -> dict:
    """The demo's report, with DEMO report settings in place of the investigator's own."""
    labels = {k: v["label"] for k, v in scan.CATEGORIES.items()}
    return report.compose(case, search.build(case), posts.list_posts(case), scan.hits(case), case.verify(),
                          labels=labels, prefs=PREFS)


def _search(case, seeds):
    name, user, email = seeds[0], seeds[1], seeds[2]
    case.audit("search", {"seeds": [s.__dict__ for s in seeds]})
    avatar = (MEDIA / "avatar.png").read_bytes()
    page = lambda site: f"<html><title>DEMO · {site} · Dorian Vell</title><body>DEMO: fictional profile page</body></html>"
    found = [
        Finding("maigret", user, "Instagram", IG, {"fullname": "Dorian Vell", "bio": "Vell Moving & Hauling",
                                                   "image": f"{IG}avatar.jpg"}, body=page("Instagram")),
        Finding("maigret", user, "TikTok", TT, {"fullname": "Dorian Vell", "bio": "moving day vlogs"}, body=page("TikTok")),
        Finding("bluesky", user, "Bluesky", BSKY, {"fullname": "Dorian Vell", "bio": "Mover. Lifting heavy things since 2009.",
                                                   "image": f"{BSKY}/avatar.jpg", "links": [IG]}, body=page("Bluesky")),
        Finding("user_scanner", email, "Strava", "https://strava.example", {}),
        Finding("github", name, "GitHub", "https://github.example/dvell",
                {"fullname": "Dorian Vell", "bio": "Rust and embedded systems. Lisbon."}, body=page("GitHub")),
        Finding("mastodon", name, "Mastodon (mastodon.example)", "https://mastodon.example/@dvell_art",
                {"fullname": "Dorian Vell", "bio": "Painter. Watercolours, mostly coasts."}),
        Finding("licences", name, "Contractor licences (DEMO)", "https://records.example/licences/ROC-000000",
                {"fullname": "Dorian Vell", "employer": "Vell Moving & Hauling", "licence": "ROC-000000 (fictional)",
                 "status": "Active", "issued": "2019-06-03"}),
        Finding("fmcsa", name, "Motor carriers (DEMO)", "https://records.example/fmcsa/USDOT-0000000",
                {"fullname": "Dorian Vell", "company": "Vell Moving & Hauling", "usdot": "0000000 (fictional)",
                 "power_units": 2}),
        Finding("courtlistener", name, "Court records (DEMO)", "https://records.example/courts/CV-2003-0000",
                {"fullname": "Dorian Vell", "case": "Vell v. Sunset Storage LLC (fictional), small claims",
                 "dob": "1961-02-03", "filed": "2003-07-21"}),
    ]
    for f in found:
        case.add_finding(f)
    runs = [("maigret", user, "found", 2, 500, "checked the top 500 sites"),
            ("whatsmyname", user, "nothing found", 0, 690, "checked 690 sites"),
            ("user_scanner", email, "found", 1, 127, "127 passive email checks; none can notify the person"),
            ("bluesky", user, "found", 1, 1, "looked up the Bluesky handle"),
            ("github", name, "found", 1, 1, "GitHub user search for 'Dorian Vell'"),
            ("mastodon", name, "found", 1, 1, "searched accounts mastodon.social knows"),
            ("stackexchange", user, "failed", 0, 0, "ReadTimeout (DEMO: a source that didn't answer)"),
            ("licences", name, "found", 1, 1, "state contractor licences (DEMO)"),
            ("fmcsa", name, "found", 1, 1, "FMCSA motor-carrier census (DEMO)"),
            ("courtlistener", name, "found", 1, 1, "federal and state dockets (DEMO)"),
            ("fec", name, "nothing found", 0, 1, "OpenFEC itemized contributions")]
    for source, seed, status, n, checked, note in runs:
        case.add_run(source, seed, status, n, checked, note)
    with Image.open(MEDIA / "avatar.png") as img:
        hash_ = photo.dhash(img)
    for url in (f"{IG}avatar.jpg", f"{BSKY}/avatar.jpg"):  # the same picture on both: a second identifier
        case.add_avatar(url, avatar, hash_)
    for finding_id, site in ((1, "instagram"), (2, "tiktok"), (3, "bluesky")):
        case.add_capture(finding_id, (MEDIA / f"profile-{site}.png").read_bytes(), page(site))
    case.audit("capture", {"attempted": 3, "saved": 3})
    case.audit("search finished", {"accounts": len(found)})


def _decide(case):
    # TikTok's display name only repeats its handle, so the handle is its one identifier ("roughly even
    # chance"): the investigator confirms it by hand, from what she saw
    case.decide(TT, "him", "DEMO: the same VELL MOVING van appears in its videos")
    snap = search.build(case)
    for c in snap["candidates"]:
        if search.in_person(c):
            case.decide(c["url"], "him", "DEMO: same name, handle and profile photo")
        elif c["probability"] < 0.2:
            case.decide(c["url"], "not him", "DEMO: a namesake; different handle, work or birth year")
    case.decide("", "him", "DEMO: the same person across Instagram, TikTok and Bluesky")


def _posts(case) -> dict:
    """Bluesky's posts as posts.collect reads them, and an Instagram video captured in the Hunt Browser."""
    case.db.executescript(posts.SCHEMA)
    out = {}
    fetched = [("hike", "2025-09-14T07:12:00+00:00", "Summit at sunrise. Last big hike before the season.", "hike.jpg"),
               ("moving", "2026-04-18T16:40:00+00:00", "Moving day for a client. Carried the sofa down three flights.",
                "moving-day.jpg"),
               ("coffee", "2026-04-25T08:05:00+00:00", "Coffee before the long drive.", "coffee.jpg"),
               ("gym", "2026-05-02T18:30:00+00:00", "Back at it. New deadlift PR.", "gym.jpg"),
               ("solo", "2026-05-20T12:00:00+00:00", "Loaded the whole van solo today.", None)]
    for key, when, text, picture in fetched:
        url = f"{BSKY}/post/demo-{key}"
        pid = case.db.execute("insert into posts (source, account_url, url, posted_at, text, origin, fetched_at) "
                              "values ('Bluesky', ?, ?, ?, ?, 'fetched', ?)", (BSKY, url, when, text, now())).lastrowid
        case.db.execute("insert or replace into post_seen values (?, ?)", (pid, now()))
        media = None
        if picture:
            file, sha = posts.store(case, MEDIA / picture)
            media = case.db.execute("insert into media values (null, ?, 'image', ?, ?, null, ?)",
                                    (pid, file, sha, f"https://cdn.bsky.example/{picture}")).lastrowid
        out[key] = {"id": pid, "posted_at": when, "media": media and {"id": media, "file": file}}
    case.add_run("bluesky", Seed("url", BSKY), "found", len(fetched), len(fetched), "Bluesky public API, logged out (DEMO)")
    case.audit("posts collected", {"accounts": [BSKY], "since": None, "added": len(fetched)})
    [vid] = posts.add_posts(case, [{
        "source": "Instagram", "url": "https://instagram.example/p/DEMO0001/", "account_url": IG,
        "posted_at": "2026-05-10T15:00:00+00:00", "text": "Two-man lift? Not today.",
        "media": [str(MEDIA / "van-loading.mp4")], "viewed_url": IG, "viewed_at": "2026-06-02T17:20:00+00:00",
        "viewed_as": "logged in as investigator.demo", "audience": "Public", "hunt_version": "0.1.0",
        "capture_version": "DEMO"}], origin="captured")
    m = case.rows("select id, file from media where post_id = ?", vid)[0]
    out["video"] = {"id": vid, "posted_at": "2026-05-10T15:00:00+00:00", "media": m}
    return out


def _scan(case, p: dict):
    case.db.executescript(scan.SCHEMA)
    injury = DETAILS["injury_date"]
    case.audit("scan started", {"look_for": DETAILS["look_for"], "injury_date": injury, "posts": 6, "media": 5,
                                "check_everything": False})
    frame = case._store((MEDIA / "van-loading-frame.jpg").read_bytes(), "jpg")[1]
    flags = [  # post, with its media?, category, what the scan saw, seconds, how sure, the investigator's call
        ("moving", False, "lifting", "Caption: “Carried the sofa down three flights”", None, 0.85, "in report"),
        ("moving", True, "lifting", "A person carrying a box beside a moving van", None, 0.8, "in report"),
        ("video", True, "lifting", "A person lifting a box into a van", (3.0, 8.0), 0.85, "in report"),
        ("gym", True, "sport", "A person lifting a barbell overhead", None, 0.8, "kept"),
        ("coffee", True, "lifting", "A person holding a cup", None, 0.5, "not relevant"),
        ("hike", True, "walks", "A person on a mountain trail", None, 0.8, "kept"),
    ]
    for key, with_media, category, what, at, sure, call in flags:
        post, media = p[key], p[key]["media"]
        file = frame if at else media["file"]
        scan._hit(case, lambda e: None, post, media if with_media else None, category, what,
                  *(at or (None, None)), sure, injury, file)
        hit = case.db.execute("select max(id) from hits").fetchone()[0]
        scan.set_status(case, hit, call)
    case.db.executemany("insert or ignore into scanned values (?, ?)",
                        [(m["id"], c) for m in case.rows("select id from media") for c in DETAILS["look_for"]])
    case.audit("scan finished", {"hits": len(flags), "vision_model": "DEMO: readings written by hand, not by a model"})
    case.audit("scan", {"accounts": 3, "posts_collected": 6, "check_everything": False})


def _check_again(case, p: dict):
    """A month later: one Bluesky post gone, and the bio rewritten (as recheck.run would record them)."""
    case.db.executescript(recheck.SCHEMA)
    gone = {"account": BSKY, "none_left": False, "posts": [
        {"id": p["solo"]["id"], "url": f"{BSKY}/post/demo-solo", "posted_at": p["solo"]["posted_at"],
         "last_seen": "2026-06-01T09:00:00+00:00"}]}
    case.audit("posts gone", gone)
    case.db.execute("insert or ignore into post_gone values (?, ?)", (p["solo"]["id"], now()))
    case.audit("profile changed", {"account": BSKY, "field": "bio", "before": "Mover. Lifting heavy things since 2009.",
                                   "after": "Taking it easy these days.", "before_seen": "2026-06-01T09:00:00+00:00"})
    case.audit("recheck", {"accounts": 3, "new_posts": 0, "changes": 2, "captured": 1, "worklist": 2})


def _notes(case):
    first = notes.add(case, "Client (fictional) confirmed the restriction by phone: no lifting over 12 lb.")
    notes.add(case, "Client (fictional) confirmed the restriction by phone: no lifting over 10 lb, from the injury date.",
              replaces=first["id"])
    video_hit = case.rows("select id from hits where t0 is not null")[0]["id"]
    notes.add(case, "The van in the video carries the company name on the contractor licence record.", "hit", video_hit)


def _hand_over(case):
    """The finished report (DEMO report settings) and the evidence bundle, in the case's exports/ folder."""
    out = case.dir / "exports"
    out.mkdir(exist_ok=True)
    rep = compose(case)
    (out / f"{SLUG}-report.html").write_text(report.to_html(case, rep))
    (out / f"{SLUG}-report.json").write_text(json.dumps(report.to_json(case, rep), indent=1, ensure_ascii=False, default=str))
    case.audit("report exported", {"format": "html", "screening": False, "tampered": rep["checks"]["tampered"]})
    bundle.make(case, out)
