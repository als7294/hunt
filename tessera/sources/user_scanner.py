"""Email → sites it's registered on (user-scanner, MIT, github.com/kaifcodec/user-scanner).

Passive only: modules known or suspected to notify the subject (password-reset
emails, one-time codes) are never run, only counted as skipped.
"""

import asyncio
import os
import re
from pathlib import Path

from user_scanner.core.engine import check
from user_scanner.core.helpers import get_site_name, is_loud, load_categories, load_modules, set_proxy_manager
from user_scanner.core.result import Status

from ..seed import Finding

NAME = "user-scanner"
KINDS = {"email"}
# ponytail: a regex over module source catches reset/OTP flows upstream hasn't flagged
# as loud (Facebook, Dropbox, Walmart...). Replace with an audited allowlist per module.
MAY_NOTIFY = re.compile(r"forgot|reset|recover|otp|send-?code|verification", re.I)


def _quiet(module) -> bool:
    return not is_loud(get_site_name(module), is_email=True) and not MAY_NOTIFY.search(Path(module.__file__).read_text())


async def search(seed):
    proxy = os.environ.get("TESSERA_PROXY")
    set_proxy_manager(proxies=[proxy] if proxy else None)
    modules = [m for path in load_categories(is_email=True).values() for m in load_modules(path)]
    quiet = [m for m in modules if _quiet(m)]
    sem = asyncio.Semaphore(20)

    async def one(module):
        async with sem:
            try:
                return await asyncio.wait_for(check(module, seed.value), 30)
            except TimeoutError:
                return None

    results = [r for r in await asyncio.gather(*map(one, quiet)) if r]
    found = [Finding(NAME, seed, r.site_name, r.url or "", {"category": r.category, **r.extra})
             for r in results if r.status == Status.TAKEN]
    errors = sum(r.status == Status.ERROR for r in results) + len(quiet) - len(results)
    checked = sum(r.status in (Status.TAKEN, Status.AVAILABLE) for r in results)
    return found, checked, (f"checked {len(quiet)} sites, {errors} errors; "
                   f"skipped {len(modules) - len(quiet)} that may notify the subject")
