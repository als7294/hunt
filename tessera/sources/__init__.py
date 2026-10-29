"""Every source is a module with NAME, KINDS (seed kinds it searches) and
`async def search(seed) -> (list[Finding], methodology_note)`."""

from . import maigret, phone, user_scanner, wmn

SOURCES = [maigret, wmn, user_scanner, phone]
