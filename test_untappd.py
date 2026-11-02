"""Self-check for hunt/sources/untappd.py. Run: uv run python test_untappd.py  (offline; the member is fictional)"""

from sourcecheck import honest, run, serve, walls
from hunt.sources import untappd

PAGE = """<html><div class="user-info"><div class="user-avatar"><div class="avatar-holder">
<img src="https://cdn.example/kv.jpg" alt="User avatar"></div></div><div class="info"> <h1> Kestrel V. </h1>
<div class="user-details"><p class="username">kvane</p><p class="location">Tucson, AZ</p><p class="bio">IPA fan</p></div></div></div>
<div id="main-stream">
<div class="item " id="checkin_9001" data-checkin-id="9001"><div class="checkin"><div class="top">
<p class="text"><a href="/user/kvane" class="user">Kestrel V.</a> is drinking a <a href="/b/x/1">Desert Haze IPA</a> by
<a href="/w/x/2">Sample Brewing Co.</a> at <a href="/v/x/3">Sample Taproom</a></p></div>
<div class="bottom"><a class="time timezoner track-click" href="/user/kvane/checkin/9001">Sat, 31 Oct 2026 03:12:00 +0000</a></div></div></div>
</div></html>"""
seen = serve(untappd, {"untappd.com/user/kvane": (200, PAGE)})
(f,), _, _ = run(untappd, "kvane")
assert f.url == "https://untappd.com/user/kvane" and f.attrs["fullname"] == "Kestrel V." and f.attrs["location"] == "Tucson, AZ"
assert f.attrs["bio"] == "IPA fan" and f.attrs["image"] == "https://cdn.example/kv.jpg"
assert f.attrs["recent"] == [{"text": "Kestrel V. is drinking a Desert Haze IPA by Sample Brewing Co. at Sample Taproom",
                              "date": "Sat, 31 Oct 2026 03:12:00 +0000", "url": "https://untappd.com/user/kvane/checkin/9001"}], f.attrs
honest(seen)
serve(untappd, {"untappd.com/user/quiet": (200, '<div class="info"> <h1> Quiet One </h1></div><div class="private_user box"></div>')})
(f,), _, note = run(untappd, "quiet")
assert f.attrs == {"fullname": "Quiet One", "private": True} and "private" in note
serve(untappd, {})
assert run(untappd, "nobody")[:2] == ([], 1)
walls(untappd, "kvane", "untappd.com/user/kvane")
print("ok")
