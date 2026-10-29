"""Screenshot + rendered HTML of likely matches for the evidence locker (headless, logged-out Chromium)."""

import asyncio
import os

from playwright.async_api import async_playwright


async def screenshots(urls: list[str], concurrency: int = 4) -> dict[str, tuple[bytes, str] | Exception]:
    async with async_playwright() as p:
        proxy = os.environ.get("TESSERA_PROXY")
        browser = await p.chromium.launch(proxy={"server": proxy} if proxy else None)
        context = await browser.new_context(viewport={"width": 1280, "height": 900})
        sem = asyncio.Semaphore(concurrency)

        async def one(url):
            async with sem:
                page = await context.new_page()
                try:
                    await page.goto(url, timeout=20_000, wait_until="load")
                    return url, (await page.screenshot(full_page=True), await page.content())
                except Exception as e:  # one bad page must not lose the rest
                    return url, e
                finally:
                    await page.close()

        results = dict(await asyncio.gather(*map(one, urls)))
        await browser.close()
        return results
