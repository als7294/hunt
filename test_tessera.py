"""Self-check for seed detection and identity scoring. Run: uv run python test_tessera.py

All subjects here are fictional.
"""

import hashlib

from tessera.match import score, verdict
from tessera.seed import Seed, detect

# Seed detection
assert detect("marisol.vance@example.com") == [Seed("email", "marisol.vance@example.com")]
assert detect("(520) 555-0143") == [Seed("phone", "+15205550143")]
assert detect("Marisol Vance") == [Seed("name", "Marisol Vance")]
assert detect("@kestrel_vane88") == [Seed("username", "kestrel_vane88")]
assert detect("1420 Saguaro Way, Tucson AZ") == [Seed("address", "1420 Saguaro Way, Tucson AZ")]
assert detect("location:Tucson, AZ") == [Seed("location", "Tucson, AZ")]
assert detect("https://www.youtube.com/@kestrel_vane88/about")[1] == Seed("username", "kestrel_vane88")
assert detect("https://www.linkedin.com/in/marisol-vance")[1] == Seed("username", "marisol-vance")
assert detect("https://www.facebook.com/profile.php?id=1") == [Seed("url", "https://www.facebook.com/profile.php?id=1")]

# ICD 203 bands
assert verdict(0.03) == "almost no chance" and verdict(0.5) == "roughly even chance" and verdict(0.97) == "almost certain"

subject = [Seed("username", "kestrel_vane88"), Seed("name", "Robert Vance"), Seed("location", "Tucson, AZ"),
           Seed("email", "rv@example.com")]
rare = Seed("username", "kestrel_vane88")

# Rare handle + matching name (via nickname) + matching city: the subject
p, v, why = score(rare, "https://site.test/kestrel_vane88", {"fullname": "Bob Vance", "location": "Tucson, Arizona"}, subject)
assert v == "almost certain", (p, why)
assert any("name 'Bob Vance' matches" in r for r in why), why

# Common handle, someone else's name, another city: a namesake
p, v, why = score(Seed("username", "kv"), "https://site.test/kv", {"fullname": "Dana Holt", "location": "Leeds"}, subject)
assert p < 0.05, (p, why)

# A display name that just echoes a common handle is not a name match (namesakes default to it)
p, v, why = score(Seed("username", "vance"), "https://site.test/vance", {"fullname": "Vance"},
                  subject + [Seed("name", "Vance")])
assert p < 0.45 and any("only repeats the username" in r for r in why), (p, why)

# Gravatar hash of the subject's email outweighs a weak handle
gh = hashlib.md5(b"rv@example.com").hexdigest()
p, v, _ = score(Seed("username", "kv"), "https://site.test/kv", {"gravatar_email_md5_hash": gh}, subject)
assert v == "almost certain", p

# Linking to another account with the subject's handle helps; a self-link doesn't
base, _, _ = score(rare, "https://a.test/kestrel_vane88", {}, subject)
linked, _, _ = score(rare, "https://a.test/kestrel_vane88", {"website": "https://b.test/kestrel_vane88"}, subject)
self_link, _, _ = score(rare, "https://a.test/kestrel_vane88", {"website": "https://a.test/kestrel_vane88"}, subject)
assert linked > base == self_link, (base, linked, self_link)

# Email registrations are the subject's by construction
p, v, _ = score(Seed("email", "rv@example.com"), "https://shop.test", {}, subject)
assert v == "almost certain", p

print("ok")
