"""Self-check for hunt/sources/letterboxd.py. Run: uv run python test_letterboxd.py  (offline; the member is fictional)"""

from sourcecheck import honest, run, serve, walls
from hunt.sources import letterboxd

FEED = """<?xml version='1.0' encoding='utf-8'?><rss version="2.0" xmlns:letterboxd="https://letterboxd.com"><channel>
<title>Letterboxd - Kestrel Vane</title><link>https://letterboxd.com/kvane/</link><description>Letterboxd - Kestrel Vane</description>
<item><title>Rocky, 1976 - ★★★★</title><link>https://letterboxd.com/kvane/film/rocky/</link>
<pubDate>Sat, 31 Oct 2026 22:00:00 +1300</pubDate><letterboxd:watchedDate>2026-10-31</letterboxd:watchedDate>
<description><![CDATA[<p>Watched after leg day.</p>]]></description></item>
<item><title>Favourites</title><link>https://letterboxd.com/kvane/list/favourites/</link><pubDate>Fri, 01 Aug 2025 10:00:00 +1200</pubDate>
<description><![CDATA[<p>My list</p>]]></description></item></channel></rss>"""
seen = serve(letterboxd, {"letterboxd.com/kvane/rss/": (200, FEED)})
(f,), _, _ = run(letterboxd, "kvane")
assert f.url == "https://letterboxd.com/kvane" and f.attrs["fullname"] == "Kestrel Vane"
assert f.attrs["recent"][0] == {"title": "Rocky, 1976 - ★★★★", "url": "https://letterboxd.com/kvane/film/rocky/",
                                "date": "Sat, 31 Oct 2026 22:00:00 +1300", "text": "Watched after leg day.", "watched": "2026-10-31"}
assert "watched" not in f.attrs["recent"][1]  # a list, not a diary entry
honest(seen)
assert [r.url.path for r in seen] == ["/kvane/rss/"]  # never the profile page
serve(letterboxd, {})
assert run(letterboxd, "nobody")[:2] == ([], 1)
walls(letterboxd, "kvane", "letterboxd.com/kvane/rss/")
print("ok")
