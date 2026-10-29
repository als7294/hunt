"""Self-check for the Facebook importers, logged-out read, links and clue mapping. Run: uv run python test_facebook.py

Offline; every person, place and post in fixtures/facebook is fictional. HUNT_LIVE=1 also reads one
public organisation's Page (NASA) logged out.
"""

import asyncio
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from hunt import facebook as fb
from hunt.seed import Seed
from hunt.sources import facebook as source

FIX = Path(__file__).parent / "fixtures" / "facebook"
REF = datetime(2026, 10, 28, 15, 0)  # "saved" Wednesday 28 October 2026, 15:00

# Dates: absolute, tooltip, relative and partial forms in English, Spanish and French
for text, want in [
    ("12 April at 09:41", ("2026-04-12T09:41", "minute")),
    ("April 12 at 9:41 PM", ("2026-04-12T21:41", "minute")),
    ("Friday, 12 April 2024 at 09:41", ("2024-04-12T09:41", "minute")),
    ("Friday, April 12, 2024 at 9:41 AM", ("2024-04-12T09:41", "minute")),
    ("Apr 12, 2023", ("2023-04-12", "day")),
    ("December 3", ("2025-12-03", "day")),  # no year and in the future: last year
    ("Yesterday at 21:15", ("2026-10-27T21:15", "minute")),
    ("Monday at 8:05 AM", ("2026-10-26T08:05", "minute")),
    ("Wednesday at 10:00", ("2026-10-21T10:00", "minute")),  # today's weekday means a week ago
    ("Just now", ("2026-10-28T15:00", "minute")),
    ("5m", ("2026-10-28T14:55", "minute")),
    ("2 hrs", ("2026-10-28T13:00", "hour")),
    ("3d", ("2026-10-25", "day")),
    ("3 days ago", ("2026-10-25", "day")),
    ("2w", ("2026-10-14", "week")),
    ("1y", ("2025-10-28", "year")),
    ("April 2024", ("2024-04-01", "month")),
    ("12 de abril a las 9:41", ("2026-04-12T09:41", "minute")),
    ("viernes, 12 de abril de 2024 a las 9:41 p. m.", ("2024-04-12T21:41", "minute")),
    ("Ayer a las 21:15", ("2026-10-27T21:15", "minute")),
    ("hace 2 horas", ("2026-10-28T13:00", "hour")),
    ("3 d", ("2026-10-25", "day")),
    ("abril de 2024", ("2024-04-01", "month")),
    ("14 avril à 08:00", ("2026-04-14T08:00", "minute")),
    ("vendredi 12 avril 2024 à 09:41", ("2024-04-12T09:41", "minute")),
    ("Hier à 21:15", ("2026-10-27T21:15", "minute")),
    ("Aujourd’hui à 07:30", ("2026-10-28T07:30", "minute")),
    ("3 j", ("2026-10-25", "day")),
    ("il y a 2 semaines", ("2026-10-14", "week")),
    ("12 avr. 2023", ("2023-04-12", "day")),
]:
    assert fb.parse_date(text, REF) == want, (text, fb.parse_date(text, REF))
for junk in ["5 comments", "180 kg", "Leg day done", "30 February 2024", "Public", ""]:
    assert fb.parse_date(junk, REF) is None, junk

# Header lines
assert fb._header("is feeling adventurous at Cedar Ridge Trailhead.") == ("feeling adventurous", "Cedar Ridge Trailhead", None)
assert fb._header(" — at Port Alder Marina.") == (None, "Port Alder Marina", None)
assert fb._header("is with Mara Quill and 2 others at Iron Harbor Gym.") == (None, "Iron Harbor Gym", None)
assert fb._header("is feeling a bit tired.") == ("feeling a bit tired", None, None)  # English "a" isn't French "à"
assert fb._header("updated his profile picture.") == (None, None, None)
assert fb._header("started a new job at Harbor Freight Movers.")[2] == "started a new job at Harbor Freight Movers"
assert fb._header("está en Gimnasio Hierro.") == (None, "Gimnasio Hierro", None)
assert fb._header("se sent motivé à Salle de sport Fer Rouge.") == ("se sent motivé", "Salle de sport Fer Rouge", None)
assert fb._counts("All reactions:\n1.2K\n48 comments") == {"reactions": 1200, "comments": 48, "shares": None}
assert fb._counts("23 J’aime 12 commentaires2 partages") == {"reactions": 23, "comments": 12, "shares": 2}
assert fb._counts("Me gusta: 17 personas\n1 vez compartido")["reactions"] == 17

# Saved page 1: modern desktop profile, "Save Page As, complete" (HTML + _files folder) with Relay JSON
posts = fb.parse_saved(FIX / "Dorian Vell _ Facebook.html", saved_at=REF)
assert len(posts) == 5, [p["url"] for p in posts]
by = {p["post_id"]: p for p in posts}
move, leg, ridge, job, ferry = (by[k] for k in ("pfbid0MoveDay88", "pfbid02XaLegDay7701", "pfbid0KqRidge4412",
                                                 "7612009933", "9001772233"))
assert all(p["source"] == "Facebook" for p in posts)
# a friend's post on his wall keeps her as the author
assert move["author"] == "Mara Quill" and move["fb_id"] == "100055512345678"
assert move["account_url"] == "https://www.facebook.com/profile.php?id=100055512345678"
assert move["url"] == "https://www.facebook.com/permalink.php?story_fbid=pfbid0MoveDay88&id=100055512345678"  # tracking gone
assert (move["posted_at"], move["posted_at_precision"]) == ("2026-10-27T18:30", "minute") and move["place"] is None
# the DOM says "3d"; the embedded JSON gives the exact second. The comment's text, date and avatar stay out
assert (leg["posted_at"], leg["posted_at_precision"], leg["posted_at_text"]) == ("2026-10-25T13:02:00+00:00", "second", "3d")
assert leg["text"] == "Leg day done. New PB on the deadlift 💪 180 kg" and "Beast" not in leg["text"]
assert leg["place"] == "Iron Harbor Gym" and leg["fb_id"] == "100087654321012"
assert (leg["reactions"], leg["comments"], leg["shares"]) == (23, 5, 2)
assert [Path(m).name for m in leg["media"]] == ["447120_n.jpg"]  # not the 16px emoji, the svg avatar or the logo
assert all(Path(m).is_file() for p in posts for m in p["media"])
# "See more" in the DOM; the full text comes from the JSON. Two photos and a video's poster; the blob: video isn't saved
assert ridge["activity"] == "feeling adventurous" and ridge["place"] == "Cedar Ridge Trailhead"
assert ridge["text"].endswith("30 kg of soggy retriever.") and not ridge["truncated"]
assert (ridge["posted_at"], ridge["posted_at_precision"]) == ("2026-04-12T09:41", "minute")
assert [Path(m).name for m in ridge["media"]] == ["448001_n.jpg", "448002_n.jpg", "448003_poster.jpg"]
assert (ridge["reactions"], ridge["comments"]) == (1200, 48)
assert job["life_event"] == "Started New Job at Harbor Freight Movers" and job["posted_at"] == "2024-04-20"
assert job["text"] == "First week on the loading dock. My back is going to hate me." and job["media"] == []
# a story only in the JSON (prefetched, never rendered) still comes through
assert ferry["text"] == "Ferry to Lisbon tomorrow, first trip in years." and ferry["posted_at"] == "2026-09-02T19:45:00+00:00"
assert ferry["url"] == "https://www.facebook.com/dorian.vell/posts/pfbid0FerryLis9001" and ferry["author"] == "Dorian Vell"
# the same saved profile's Intro card
assert fb.parse_profile(FIX / "Dorian Vell _ Facebook.html")["attrs"] == {
    "fullname": "Dorian Vell", "location": "Port Alder, Oregon", "hometown": "Bend, Oregon",
    "works_at": "Harbor Freight Movers"}

# Saved page 2: classic desktop layout, Spanish, plain HTML (pictures still on Facebook's CDN, so no media)
posts = fb.parse_saved(FIX / "classic_es.html", saved_at=REF)
assert len(posts) == 3
bench, hike, moved = posts
assert bench["posted_at"] == "2024-04-12T15:41:00+00:00" and bench["posted_at_precision"] == "second"
assert bench["posted_at_text"] == "viernes, 12 de abril de 2024 a las 9:41"  # data-utime wins; the tooltip is kept
assert bench["author"] == "Dorian Vell" and bench["fb_id"] == "100087654321012" and bench["place"] == "Gimnasio Hierro"
assert bench["text"] == "Hoy press de banca con 100 kg. ¡A por más! 🏋️" and "Bestia" not in bench["text"]
assert (bench["reactions"], bench["comments"], bench["shares"]) == (17, 3, 1) and bench["media"] == []
assert bench["url"] == "https://www.facebook.com/dorian.vell/posts/2210334455"
assert (hike["posted_at"], hike["posted_at_precision"]) == ("2026-10-28T12:00", "hour")  # "3 h", no data-utime
assert hike["activity"] == "se siente agotado" and hike["place"] == "Sendero Cedar Ridge"
assert hike["text"] == "Caminata de 15 km con la mochila cargada.\nLa rodilla aguantó." and hike["comments"] == 5
assert moved["life_event"] == "se mudó a Port Alder, Oregón" and moved["fb_id"] == "100087654321012"  # ID from his other posts

# Saved page 3: mobile site, French, single-file MHTML: pictures come out of the archive into a folder
with tempfile.TemporaryDirectory() as tmp:
    posts = fb.parse_saved(FIX / "mobile_fr.mhtml", media_dir=tmp)  # relative times count from the MHTML Date
    assert len(posts) == 3
    squat, rando, demenage = posts
    assert squat["posted_at"] == "2024-04-14T06:00:00+00:00"  # data-ft publish_time
    assert squat["activity"] == "se sent motivé" and squat["place"] == "Salle de sport Fer Rouge"
    assert squat["text"] == "Séance de muscu : 120 kg au squat. Le genou tient le coup !"
    assert (squat["reactions"], squat["comments"], squat["shares"]) == (23, 12, 2)
    assert squat["url"] == "https://www.facebook.com/story.php?story_fbid=5540011223&id=100087654321012"
    assert len(squat["media"]) == 1 and Path(squat["media"][0]).parent == Path(tmp)
    assert Image.open(squat["media"][0]).size == (48, 36)
    assert (rando["posted_at"], rando["posted_at_precision"]) == ("2026-10-24", "day")  # "3 j" before 27 Oct
    assert rando["place"] == "Parc national des Cèdres" and rando["truncated"] and rando["text"].endswith("le chien.")
    assert demenage["life_event"] == "a commencé à travailler chez Déménagements Port-Alder"
    assert demenage["posted_at"] == "2025-10-10" and demenage["fb_id"] == "100087654321012"

# Saved page 4: one public post saved logged out from Safari (.webarchive): only its link-preview tags
with tempfile.TemporaryDirectory() as tmp:
    [post] = fb.parse_saved(FIX / "public_post.webarchive", saved_at=REF, media_dir=tmp)
    assert post["author"] == "Port Alder Rowing Club" and post["account_url"] == "https://www.facebook.com/PortAlderRowing"
    assert post["fb_id"] == "61550123456789" and post["post_id"] == "pfbid0RowDawn5521"
    assert post["text"].startswith("Dawn session on the estuary. Dorian Vell back in the boat")
    assert post["posted_at"] == "2026-10-03T06:42" and len(post["media"]) == 1 and Path(post["media"][0]).is_file()

# Fail soft: an unrelated page gives no posts, a bare article still gives a partial one
assert fb.parse_saved(FIX / "public_page.html", saved_at=REF) == []
with tempfile.TemporaryDirectory() as tmp:
    bare = Path(tmp) / "bare.html"
    bare.write_text('<div role="article"><span>Back at it.</span><a href="/x/posts/123">2h</a></div>')
    [post] = fb.parse_saved(bare, saved_at=REF)
    assert post["text"] == "Back at it." and post["post_id"] == "123" and post["posted_at_precision"] == "hour"
    assert post["author"] is None and post["account_url"] == "https://www.facebook.com/x"

# A crafted page can't reach files outside its own folder, and absurd nesting doesn't crash
with tempfile.TemporaryDirectory() as tmp:
    outside, page = Path(tmp) / "private.jpg", Path(tmp) / "saved" / "page.html"
    page.parent.mkdir()
    Image.new("RGB", (80, 80)).save(outside)
    page.write_text(f'<div role="article"><a href="/x/posts/1">2h</a><img src="../private.jpg" width="500">'
                    f'<img src="{outside}" width="500"><img src="file://{outside}" width="500"></div>')
    assert fb.parse_saved(page, saved_at=REF)[0]["media"] == []
    page.write_text('<div role="article"><a href="/x/posts/1">2h</a>' + "<div>" * 5000 + "deep</div>")
    assert fb.parse_saved(page, saved_at=REF)[0]["post_id"] == "1"

# Screenshots: OCR lines as Apple Vision returns them (wrapped lines, chrome, "•" and the globe read as a symbol)
post = fb.parse_screenshot("shot.png", ["Facebook", "Search", "Dorian Vell is at Iron Harbor", "Gym.",
                                        "12 April at 09:41 • ©", "Leg day done. New PB on the", "deadlift 180 kg",
                                        "See more", "23", "5 comments 2 shares", "Like", "Comment", "Share"], REF)
assert (post["author"], post["place"], post["posted_at"]) == ("Dorian Vell", "Iron Harbor Gym", "2026-04-12T09:41")
assert post["text"] == "Leg day done. New PB on the deadlift 180 kg" and post["truncated"]
assert (post["reactions"], post["comments"], post["shares"]) == (23, 5, 2) and post["media"] == ["shot.png"]
post = fb.parse_screenshot("captura.png", ["Dorian Vell se siente agotado en Sendero Cedar Ridge.", "Ayer a las 21:15 · ®",
                                           "Caminata de 15 km.", "Me gusta", "Comentar", "5 comentarios"], REF)
assert (post["activity"], post["place"], post["posted_at"]) == ("se siente agotado", "Sendero Cedar Ridge", "2026-10-27T21:15")
assert post["text"] == "Caminata de 15 km." and post["comments"] == 5
post = fb.parse_screenshot("capture.png", ["Dorian Vell • Suivre", "3 j • @", "Randonnée de 15 km ce matin.",
                                           "A emménagé à Port Alder", "Toutes les réactions :", "9"], REF)
assert (post["author"], post["posted_at"], post["posted_at_precision"]) == ("Dorian Vell", "2026-10-25", "day")
assert post["life_event"] == "A emménagé à Port Alder" and post["reactions"] == 9
post = fb.parse_screenshot("nodate.png", ["Dorian Vell", "Back in the boat."], REF)
assert post["author"] == "Dorian Vell" and post["text"] == "Back in the boat." and post["posted_at"] is None
assert fb._shot_time(Path("Screenshot 2026-10-28 at 2.03.12 PM.png")) == datetime(2026, 10, 28, 14, 3, 12)
assert fb._shot_time(Path("Captura de pantalla 2026-10-28 a las 14.03.12.png")) == datetime(2026, 10, 28, 14, 3, 12)
if sys.platform == "darwin":  # the real thing: a rendered post through Apple Vision
    with tempfile.TemporaryDirectory() as tmp:
        img = Image.new("RGB", (900, 420), "white")
        draw, font = ImageDraw.Draw(img), lambda s: ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", s)
        draw.text((90, 30), "Dorian Vell is feeling adventurous at Cedar Ridge Trailhead.", fill="black", font=font(26))
        draw.text((90, 66), "3d · ", fill=(101, 103, 107), font=font(22))
        draw.text((30, 130), "Six miles up the ridge with the dog. Knee held up fine.", fill="black", font=font(26))
        draw.text((30, 330), "1.2K", fill=(101, 103, 107), font=font(22))
        draw.text((650, 330), "48 comments", fill=(101, 103, 107), font=font(22))
        draw.text((90, 380), "Like", fill=(101, 103, 107), font=font(24))
        shot = Path(tmp) / "Screenshot 2026-10-28 at 14.03.12.png"
        img.save(shot)
        post = fb.parse_screenshot(shot)
        assert (post["author"], post["activity"], post["place"]) == ("Dorian Vell", "feeling adventurous", "Cedar Ridge Trailhead")
        assert (post["posted_at"], post["posted_at_precision"]) == ("2026-10-25", "day")  # 3 days before the file name's date
        assert post["text"] == "Six miles up the ridge with the dog. Knee held up fine."
        assert (post["reactions"], post["comments"]) == (1200, 48)

# Logged-out public reads: what Facebook serves, and the login wall
page = fb.parse_public((FIX / "public_page.html").read_text(), "https://www.facebook.com/PortAlderRowing/")
assert page["state"] == "found"
assert page["attrs"] | {"image": None} == {
    "fullname": "Port Alder Rowing Club", "uid": "61550123456789", "followers": 2481, "talking_about": 37,
    "url": "https://www.facebook.com/PortAlderRowing/", "image": None,
    "description": "Port Alder Rowing Club. 2,481 followers · 37 talking about this. Community rowing on the Alder estuary since 1974."}
person = ('<html><head><title>Dorian Vell | Facebook</title><meta property="og:title" content="Dorian Vell">'
          '<meta property="og:description" content="Dorian Vell. Lives in Port Alder, Oregon · From Bend, Oregon · '
          'Works at Harbor Freight Movers · 312 followers"><meta property="al:ios:url" content="fb://profile/100087654321012">'
          '</head><body><div id="login_popup_cta_form">See more on Facebook</div></body></html>')
attrs = fb.parse_public(person, "https://www.facebook.com/dorian.vell")["attrs"]
assert (attrs["location"], attrs["hometown"], attrs["works_at"]) == ("Port Alder, Oregon", "Bend, Oregon", "Harbor Freight Movers")
assert attrs["uid"] == "100087654321012" and attrs["followers"] == 312
wall = ('<html><head><title>Log into Facebook</title></head><body><form id="login_form" action="/login/device-based/regular/login/">'
        '<input name="email"><input name="pass" type="password"></form></body></html>')
assert fb.parse_public(wall, "https://www.facebook.com/login/?next=https%3A%2F%2Fwww.facebook.com%2Fdorian.vell")["state"] == "login wall"
assert fb.parse_public(wall, "https://www.facebook.com/dorian.vell")["state"] == "login wall"
assert fb.parse_public("<html><head><title>Facebook</title></head><body></body></html>")["state"] == "unavailable"
gone = "<html><head><title>Facebook</title></head><body><h2>This content isn't available right now</h2></body></html>"
assert fb.parse_public(gone)["state"] == "unavailable"
error = ("<html><head><title>Error</title></head><body><h1>Sorry, something went wrong.</h1>"
         "<p>We're working on getting this fixed as soon as we can.</p></body></html>")
assert fb.parse_public(error, status=400)["state"] == "refused"
assert fb.parse_public("<html><head><title>Log into Facebook | Facebook</title></head></html>")["state"] == "login wall"

# The source: which seeds it reads (no request for impossible usernames), and its honest notes
assert source.target(Seed("username", "dorian.vell")) == "https://www.facebook.com/dorian.vell"
assert source.target(Seed("username", "kestrel_vane88")) is None  # underscores can't be a Facebook username
assert source.target(Seed("url", "https://m.facebook.com/profile.php?id=100087654321012&ref=x")) == \
    "https://www.facebook.com/profile.php?id=100087654321012"
assert source.target(Seed("url", "https://www.facebook.com/dorian.vell/posts/7612009933")) is None
assert source.target(Seed("url", "https://example.com/dorian.vell")) is None
assert asyncio.run(source.search(Seed("username", "kestrel_vane88")))[:2] == ([], 0)
seed = Seed("username", "PortAlderRowing")
findings, checked, note = source.result(seed, "https://www.facebook.com/PortAlderRowing", "https://www.facebook.com/PortAlderRowing/",
                                        200, (FIX / "public_page.html").read_text())
assert checked == 1 and findings[0].site == "Facebook" and findings[0].attrs["uid"] == "61550123456789"
assert findings[0].body and note.endswith("Facebook showed a login wall; nothing more is public")
findings, checked, note = source.result(seed, "https://www.facebook.com/dorian.vell", "https://www.facebook.com/login/", 200, wall)
assert (findings, checked) == ([], 0) and note.endswith("Facebook showed a login wall; nothing more is public")
assert "refused" in source.result(seed, "https://www.facebook.com/x.y.z.q", "https://www.facebook.com/x.y.z.q", 400, error)[2]
assert source.KINDS == {"username", "url"} and source.NAME == "facebook"

# Investigator links: opened by the investigator, never fetched by Hunt
links = fb.search_links([Seed("name", "Dorian Vell"), Seed("location", "Port Alder"), Seed("phone", "+15415550143"),
                         Seed("username", "dorian.vell"), Seed("url", "https://www.facebook.com/profile.php?id=100087654321012")])
urls = [link["url"] for link in links]
assert "https://www.facebook.com/search/people/?q=Dorian+Vell" in urls
assert "https://www.facebook.com/search/photos/?q=Dorian+Vell" in urls
assert "https://www.facebook.com/search/posts/?q=Dorian+Vell+Port+Alder" in urls
assert {"label": 'Google: site:facebook.com "Dorian Vell" "Port Alder"',
        "url": "https://www.google.com/search?q=site%3Afacebook.com+%22Dorian+Vell%22+%22Port+Alder%22"} in links
assert any('"(541) 555-0143" OR "+1 541-555-0143"' in link["label"] for link in links)
assert "https://www.facebook.com/dorian.vell" in urls
assert "https://www.facebook.com/profile.php?id=100087654321012&sk=about" in urls
assert len(urls) == len(set(urls))
assert all(u.startswith(("https://www.facebook.com/", "https://www.google.com/", "https://www.bing.com/")) for u in urls)
assert "https://www.facebook.com/kestrel_vane88" not in [l["url"] for l in fb.search_links(Seed("username", "kestrel_vane88"))]

# Clue mapping onto the scan's category keys
cats = lambda **post: [key for key, _ in fb.categories(post)]
assert cats(place="Iron Harbor Gym") == ["sport"]
assert cats(activity="feeling adventurous", place="Cedar Ridge Trailhead") == ["walks"]
assert cats(life_event="Started New Job at Harbor Freight Movers") == ["other_job"]
assert cats(activity="traveling to Lisbon") == ["travel"]
assert cats(activity="working out") == ["sport"]  # not other_job
assert cats(activity="feeling blessed") == []  # not French "blessé"
assert cats(life_event="Got a new car") == ["driving"]
assert cats(life_event="Moved to Port Alder") == ["activity"]
assert cats(place="Saint Alder Hospital") == ["injury"]
assert cats(activity="jugando al fútbol") == ["sport"]
assert cats(place="Sendero Cedar Ridge") == ["walks"]
assert cats(life_event="empezó a trabajar en Taller Ríos") == ["other_job"]
assert cats(place="Salle de sport Fer Rouge") == ["sport"]
assert "other_job" in cats(life_event="a commencé à travailler chez Déménagements Port-Alder")
assert cats(activity="fait de la randonnée") == ["walks"]
assert fb.categories({"place": "Iron Harbor Gym"}) == [("sport", 'Facebook check-in: "Iron Harbor Gym"')]

if os.environ.get("HUNT_LIVE"):  # one logged-out read of a public organisation's Page, never a person
    findings, checked, note = asyncio.run(source.search(Seed("url", "https://www.facebook.com/NASA")))
    print("live:", note)
    assert checked == 1 and findings[0].attrs["uid"].isdigit() and findings[0].attrs["fullname"].startswith("NASA")

print("ok")
