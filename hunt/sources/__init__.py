"""Every source is a module with NAME, KINDS (seed kinds it searches) and
`async def search(seed) -> (findings, checked, note)`.

`checked` counts sites that gave a definite yes/no answer (it feeds username
rarity); `note` is a one-line methodology summary. Network calls honour the
`HUNT_PROXY` environment variable (unset = direct). `_api` is shared plumbing,
not a source.
"""

from . import (bluesky, courtlistener, edgar, fec, github, gravatar, keybase, maigret, mastodon, npi, openpgp, phone,
               stackexchange, user_scanner, wayback, wmn)

SOURCES = [maigret, wmn, user_scanner, phone,
           github, keybase, bluesky, mastodon, stackexchange, wayback,  # username / name → profiles
           gravatar, openpgp,  # email → verified name and accounts
           fec, edgar, npi, courtlistener]  # name → public records
