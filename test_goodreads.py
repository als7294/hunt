"""Self-check for hunt/sources/goodreads.py. Run: uv run python test_goodreads.py  (offline; the members are fictional)"""

from sourcecheck import honest, run, serve, walls
from hunt.sources import goodreads


def page(details):
    return f"""<html><meta property="og:image" content="https://images.example/u/kv.jpg">
<h1 class="userProfileName">Kestrel Vane</h1>
<div class="infoBoxRowTitle">Details</div>
<div class="infoBoxRowItem">{details}</div>
<div class="infoBoxRowTitle">Website</div>
<div class="infoBoxRowItem"><a rel="nofollow noopener" href="https://vane.example">https://vane.example</a></div>
<div class="infoBoxRowTitle">Joined</div>
<div class="infoBoxRowItem">March 2015</div></html>"""


seen = serve(goodreads, {"goodreads.com/kvane": (302, "", {"location": "https://www.goodreads.com/user/show/123-kestrel"}),
                         "user/show/123-kestrel": (200, page("Age 34, Female, Tucson, AZ"))})
(f,), _, _ = run(goodreads, "kvane")
assert f.url == "https://www.goodreads.com/kvane", f
assert f.attrs == {"fullname": "Kestrel Vane", "age": "34", "location": "Tucson, AZ", "website": "https://vane.example",
                   "created_at": "March 2015", "image": "https://images.example/u/kv.jpg"}, f.attrs  # never gender
honest(seen)
serve(goodreads, {"goodreads.com/teen": (302, "", {"location": "https://www.goodreads.com/user/show/9-teen"}),
                  "user/show/9-teen": (200, page("Age 15, Tucson, AZ"))})
found, checked, note = run(goodreads, "teen")
assert (found, checked) == ([], 1) and "under 18" in note  # a minor's profile is withheld (A5)
serve(goodreads, {"goodreads.com/nobody": (200, "<html><h1>Page not found</h1></html>")})
assert run(goodreads, "nobody")[:2] == ([], 1)
walls(goodreads, "kvane", "goodreads.com/kvane")
print("ok")
