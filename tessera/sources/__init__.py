"""Every source is a module with NAME, KINDS (seed kinds it searches) and
`async def search(seed) -> (findings, checked, note)`.

`checked` counts sites that gave a definite yes/no answer (it feeds username
rarity); `note` is a one-line methodology summary. Network calls honour the
`TESSERA_PROXY` environment variable (unset = direct)."""

from . import maigret, phone, user_scanner, wmn

SOURCES = [maigret, wmn, user_scanner, phone]
