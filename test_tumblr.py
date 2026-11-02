"""Self-check for hunt/sources/tumblr.py. Run: uv run python test_tumblr.py  (offline; the blog is fictional)"""

from sourcecheck import honest, refused, run, serve, walls
from hunt.sources import tumblr

FEED = """<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><description>Lifting in the desert</description>
<title>Kestrel Lifts</title><generator>Tumblr (3.0; @kvanelifts)</generator><link>https://kvanelifts.tumblr.com/</link>
<item><title>Meet day</title><description>&lt;p&gt;Placed second at the &lt;b&gt;Desert Open&lt;/b&gt;&lt;/p&gt;</description>
<link>https://kvanelifts.tumblr.com/post/1/meet-day</link><pubDate>Sat, 31 Oct 2026 18:00:00 -0700</pubDate></item>
</channel></rss>"""
seen = serve(tumblr, {"kvanelifts.tumblr.com/rss": (200, FEED)})
(f,), checked, note = run(tumblr, "KVaneLifts")
assert (f.url, f.site, checked) == ("https://www.tumblr.com/kvanelifts", "Tumblr", 1), f
assert f.attrs["fullname"] == "Kestrel Lifts" and f.attrs["bio"] == "Lifting in the desert", f.attrs
assert f.attrs["recent"] == [{"title": "Meet day", "url": "https://kvanelifts.tumblr.com/post/1/meet-day",
                              "date": "Sat, 31 Oct 2026 18:00:00 -0700", "text": "Placed second at the Desert Open"}], f.attrs
honest(seen)
assert [r.url.path for r in seen] == ["/rss"]  # only the feed, never the blog page
serve(tumblr, {"nobody.tumblr.com/rss": (403, "<title>Checking your browser...</title>")})
assert "403" in refused(tumblr, "nobody")  # Tumblr's answer for a blog nobody has: a wall, so Tumblr stops
assert run(tumblr, "no_underscores")[:2] == ([], 0)
walls(tumblr, "kvanelifts", "kvanelifts.tumblr.com/rss")
print("ok")
