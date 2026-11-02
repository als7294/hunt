"""Self-check for hunt/sources/reddit.py. Run: uv run python test_reddit.py  (offline; the account is fictional)"""

from sourcecheck import honest, refused, run, serve, walls
from hunt.sources import reddit

ABOUT = {"kind": "t2", "data": {"name": "kvane_lifts", "created_utc": 1600000000, "total_karma": 1234, "is_suspended": False,
                                "icon_img": "https://styles.example/kv.png?width=256&amp;s=1",
                                "subreddit": {"title": "Kestrel Vane", "public_description": "Tucson. Deadlifts."}}}
OVERVIEW = {"data": {"children": [
    {"kind": "t3", "data": {"title": "New PR at the gym today", "subreddit_name_prefixed": "r/powerlifting",
                            "created_utc": 1793000000, "permalink": "/r/powerlifting/comments/abc/new_pr/"}},
    {"kind": "t1", "data": {"body": "Anyone know a good physio near Oro Valley?", "subreddit_name_prefixed": "r/Tucson",
                            "created_utc": 1792900000, "permalink": "/r/Tucson/comments/def/x/ghi/"}}]}}

seen = serve(reddit, {"about.json": (200, ABOUT), "overview.json": (200, OVERVIEW)})
(f,), checked, note = run(reddit, "kvane_lifts")
assert f.url == "https://www.reddit.com/user/kvane_lifts" and f.site == "Reddit" and checked == 1, f
assert f.attrs["fullname"] == "Kestrel Vane" and f.attrs["bio"] == "Tucson. Deadlifts." and f.attrs["karma"] == 1234
assert f.attrs["image"] == "https://styles.example/kv.png" and f.attrs["created_at"].startswith("2020-09-13")
assert [r["subreddit"] for r in f.attrs["recent"]] == ["r/powerlifting", "r/Tucson"] and f.attrs["recent"][1]["kind"] == "comment"
assert f.attrs["recent"][0]["url"] == "https://www.reddit.com/r/powerlifting/comments/abc/new_pr/" and "disallows" in note
honest(seen)
assert [r.url.path for r in seen] == ["/user/kvane_lifts/about.json", "/user/kvane_lifts/overview.json"]

serve(reddit, {"about.json": (200, {"kind": "t2", "data": {"name": "kvane_lifts", "is_suspended": True}})})
(f,), _, note = run(reddit, "kvane_lifts")
assert f.attrs == {"suspended": True} and "suspended" in note  # a suspended account: no posts requested
serve(reddit, {})
assert run(reddit, "nobody_here")[:2] == ([], 1)  # 404
assert run(reddit, "not a handle!")[:2] == ([], 0)
walls(reddit, "kvane_lifts", "about.json")
serve(reddit, {"about.json": (302, "", {"location": "https://old.reddit.com/login/?reason=lor2"}), "/login/": (404, "Not Found")})
assert "login page" in refused(reddit, "kvane_lifts")  # what Reddit does today to a logged-out read
print("ok")
