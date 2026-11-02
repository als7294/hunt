"""Self-check for hunt/sources/medium.py. Run: uv run python test_medium.py  (offline; the author is fictional)"""

from sourcecheck import honest, run, serve, walls
from hunt.sources import medium

FEED = """<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>
<title><![CDATA[Stories by Kestrel Vane on Medium]]></title><description><![CDATA[Stories by Kestrel Vane on Medium]]></description>
<link>https://medium.com/@KVane?source=rss-1------2</link><image><url>https://cdn.example/kv.png</url></image>
<lastBuildDate>Mon, 02 Nov 2026 03:15:49 GMT</lastBuildDate>
<item><title><![CDATA[Coming back from a back injury]]></title><link>https://medium.com/@KVane/back-1</link>
<pubDate>Mon, 26 Oct 2026 10:00:00 GMT</pubDate><description><![CDATA[<p>Three months of rehab.</p>]]></description></item>
</channel></rss>"""
seen = serve(medium, {"feed/@kvane": (200, FEED)})
(f,), checked, _ = run(medium, "@kvane")
assert (f.url, f.attrs["fullname"], f.attrs["image"]) == ("https://medium.com/@KVane", "Kestrel Vane", "https://cdn.example/kv.png")
assert f.attrs["recent"][0]["title"] == "Coming back from a back injury" and f.attrs["recent"][0]["text"] == "Three months of rehab."
honest(seen)
serve(medium, {})
assert run(medium, "nobody")[:2] == ([], 1)
walls(medium, "kvane", "feed/@kvane")
print("ok")
