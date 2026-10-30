"""Screenshot + rendered HTML of likely matches for the evidence locker (headless, logged-out Chromium).

Never on a host whose robots.txt denies unnamed agents (sources._api.denied) or a platform under a hard stop
(browser.stopped). The browser says it's Hunt, not a person's Chrome. A wall ends that host's shots for this run:
a 429 only that (legal.md C7); a CAPTCHA, a block or a login wall also sets a hard stop on its platform (C8).
"""

import asyncio
import os
import re
from urllib.parse import urlparse

from playwright.async_api import async_playwright

from . import browser, extension
from .sources._api import UA, denied

WALL_PATH = re.compile(r"/(?:login|accounts/login|signin|checkpoint|challenge|captcha)(?:[/?#]|$)", re.I)
CAPTCHA = re.compile(r"captcha|verify you are (?:a )?human|are you a robot|unusual traffic|access denied|you(?:'ve| have) "
                     r"been blocked", re.I)


def wall(status: int | None, url: str, text: str) -> tuple[str, str] | None:
    """What a page shows instead of itself: ("limit", why) for a 429, ("stop", why) for a CAPTCHA, an IP block, a
    login wall or a checkpoint, else None."""
    if status == 429:
        return "limit", "a 429 (too many requests)"
    path = urlparse(url).path
    if WALL_PATH.search(path) or (reason := extension.revoked(extension.platform(url), url, text)):
        return "stop", f"a login or checkpoint page ({path})" if WALL_PATH.search(path) else reason
    if status == 403 or CAPTCHA.search(text[:5000]):
        return "stop", "a CAPTCHA or block page" + (" (403)" if status == 403 else "")
    return None


async def screenshots(urls: list[str], concurrency: int = 4) -> dict[str, tuple[bytes, str] | Exception]:
    results, todo = {}, []
    for url in urls:  # refused before any browser starts
        if denied(url):
            results[url] = PermissionError("robots.txt denies unnamed agents; open it from the worklist")
        elif stop := browser.stopped(url):
            results[url] = PermissionError(stop["message"])
        else:
            todo.append(url)
    if not todo:
        return results
    walled: dict[str, str] = {}  # host → why its remaining shots are skipped this run
    async with async_playwright() as p:
        proxy = os.environ.get("HUNT_PROXY")
        chrome = await p.chromium.launch(proxy={"server": proxy} if proxy else None)
        context = await chrome.new_context(viewport={"width": 1280, "height": 900}, user_agent=f"{UA} HeadlessChrome")
        sem = asyncio.Semaphore(concurrency)

        async def one(url):
            host = urlparse(url).hostname or ""
            async with sem:
                if host in walled or browser.stopped(url):
                    return url, PermissionError(walled.get(host) or browser.stopped(url)["message"])
                page = await context.new_page()
                try:
                    response = await page.goto(url, timeout=20_000, wait_until="load")
                    hit = wall(response.status if response else None, page.url, await page.inner_text("body"))
                    if hit:
                        kind, why = hit
                        walled[host] = f"{host} showed {why}; Hunt stopped its screenshots for this run"
                        if kind == "stop" and (site := extension.platform(page.url) or extension.platform(url)):
                            browser.stop(site, why, page.url, automatic=True)
                        return url, PermissionError(walled[host])
                    return url, (await page.screenshot(full_page=True), await page.content())
                except Exception as e:  # one bad page must not lose the rest
                    return url, e
                finally:
                    await page.close()

        results |= dict(await asyncio.gather(*map(one, todo)))
        await chrome.close()
    return results
