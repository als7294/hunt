"""Self-check for hunt/sources/telegram.py. Run: uv run python test_telegram.py  (offline; the accounts are fictional)"""

from sourcecheck import honest, run, serve, walls
from hunt.sources import telegram

CHANNEL = """<html><div class="tgme_channel_info_header_title"><span dir="auto">Vane Lifting Club</span></div>
<i class="tgme_page_photo_image bgcolor4" data-content="VL"><img src="https://cdn.example/vl.jpg"></i>
<div class="tgme_channel_info_description">Tucson meet-ups &amp; results</div>
<span class="counter_value">1.2K</span> <span class="counter_type">subscribers</span>
<div class="tgme_widget_message_wrap"><div class="tgme_widget_message" data-post="vanelifts/7">
<div class="tgme_widget_message_text js-message_text" dir="auto">Meet at <b>Reid Park</b> Saturday</div>
<a class="tgme_widget_message_date"><time datetime="2026-10-30T09:00:00+00:00">Oct 30</time></a></div></div>
<div class="tgme_widget_message_wrap"><div class="tgme_widget_message" data-post="vanelifts/8">
<div class="tgme_widget_message_text js-message_text" dir="auto">New squat record</div>
<a class="tgme_widget_message_date"><time datetime="2026-10-31T18:00:00+00:00">Oct 31</time></a></div></div></html>"""
CARD = """<html><div class="tgme_page_title" dir="auto"><span dir="auto">Kestrel Vane</span></div>
<div class="tgme_page_extra">@kvane_tg</div><div class="tgme_page_description" dir="auto">coach, AZ</div></html>"""
NOBODY = '<html><div class="tgme_page_description">If you have Telegram, you can contact @x right away.</div></html>'

seen = serve(telegram, {"t.me/s/vanelifts": (200, CHANNEL)})
(f,), checked, note = run(telegram, "@vanelifts")
assert (f.url, f.attrs["fullname"], f.attrs["bio"], f.attrs["subscribers"]) == \
    ("https://t.me/vanelifts", "Vane Lifting Club", "Tucson meet-ups & results", "1.2K"), f
assert [p["url"] for p in f.attrs["recent"]] == ["https://t.me/vanelifts/8", "https://t.me/vanelifts/7"]  # newest first
assert f.attrs["recent"][1]["text"] == "Meet at Reid Park Saturday" and f.attrs["recent"][0]["date"] == "2026-10-31T18:00:00+00:00"
assert f.attrs["image"] == "https://cdn.example/vl.jpg" and "robots.txt" in note
honest(seen)
serve(telegram, {"t.me/s/kvane_tg": (302, "", {"location": "https://t.me/kvane_tg"}), "t.me/kvane_tg": (200, CARD)})
(f,), _, note = run(telegram, "kvane_tg")
assert f.attrs == {"fullname": "Kestrel Vane", "bio": "coach, AZ", "kind": "@kvane_tg"} and "no posts" in note, f.attrs
serve(telegram, {"t.me/s/nobodyhere": (302, "", {"location": "https://t.me/nobodyhere"}), "t.me/nobodyhere": (200, NOBODY)})
assert run(telegram, "nobodyhere")[:2] == ([], 1)
assert run(telegram, "abc")[:2] == ([], 0)  # too short to be a Telegram name
walls(telegram, "vanelifts", "t.me/s/vanelifts")
print("ok")
