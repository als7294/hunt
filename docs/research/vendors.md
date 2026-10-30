# Vendor connectors: terms and prices on file

_Checked 2026-10-29 from the pricing page, the General Terms, the API docs and the Store API. Prices change at the developer's discretion (Terms §7.1), so the per-post prices Hunt budgets with are settings, not code. Policy: [automation-legal.md](automation-legal.md) §4 ("vendor connector rules": optional, off by default, the investigator's own key, provenance per record, the vendor's permitted-use clause on file)._

## The line

Hunt ships no vendor key and runs completely free by default. When the investigator, or Ethos on her behalf, adds an Apify key in Settings, they accept Apify's terms below for that account, and the Actors' output is obtained under their account, not Hunt's. Every post so obtained is marked `origin: vendor`, named "Instagram (via Apify)" or "Facebook (via Apify)", and each run is in the audit log with vendor, Actor, build, run id, status, cost, account and time, so the report can say "N posts obtained through Apify under the investigator's own account". Media are fetched by Hunt from the platforms' CDNs and hashed here like every other evidence file.

## Apify

**Plan and credit** ([apify.com/pricing](https://apify.com/pricing)): the Free plan includes **$5 of platform usage a month, no credit card**. Pay-per-event Actors draw on that credit. Over the limit, "your access to Apify's services will be blocked until the beginning of the next monthly cycle"; unused credit expires with the cycle. Free-plan limits: 16 GB max RAM, 5 concurrent runs. Hunt reads the live figures from `GET /v2/users/me/limits` (`current.monthlyUsageUsd`, `limits.maxMonthlyUsageUsd`, `monthlyUsageCycle.endAt`) before every run and shows "this run ≈ $0.17 · about $4.10 of this month's credit left".

**Terms** ([Apify General Terms and Conditions, effective 2026-07-09](https://docs.apify.com/legal/general-terms-and-conditions)):
- §6.1: use the Services and Actors in compliance with the Acceptable Use Policy; §6.2: "process only the Customer Data that you are authorized to access".
- §5.8: the user is "solely responsible for the legality, accuracy, quality, appropriateness, and use of all Customer Data"; §9.1: the Data Processing Addendum applies to personal data in Customer Data, and Apify is "not responsible for your privacy obligations".
- §3.1: Store Actors "are not part of the Services provided by Apify" and come under the Actor Terms and the Store Publishing Terms; §7.1: Actor prices are set, and changed, by the Actor developer; §7.4: fees are non-refundable.
- §11.1: the user indemnifies Apify for data extracted "from unauthorized sources" and for disputes with Actor developers.

So the permitted-use question sits with the Actor developer's terms and the platform's, as the legal brief's decision tables put it (row (e), "vendor's risk" for Instagram, Facebook and TikTok). Ethos's counsel should see this page before a key is added.

**API used by `hunt/vendor.py`** ([docs](https://docs.apify.com/api/v2)): `POST /v2/acts/{actor}/runs` with the Actor input as the body and `maxTotalChargeUsd` ("the maximum total cost of the run… for all pricing models") and `timeout` as query parameters; `GET /v2/actor-runs/{id}?waitForFinish=60` until a terminal status (`SUCCEEDED`, `FAILED`, `TIMED-OUT`, `ABORTED`); the cost `usageTotalUsd` is read again about 10 s later, since the first figures after a run are preliminary; `GET /v2/datasets/{id}/items?clean=true`. The token travels in the `Authorization: Bearer` header, never in a URL.

**Actors** (prices from the Store API's `currentPricingInfo`, FREE tier, 2026-10-29; higher plans pay less):

| Actor | Price on the Free plan | Inputs Hunt uses | Output fields Hunt maps | Notes |
|---|---|---|---|---|
| **`apify/instagram-post-scraper`** (default) | **$0.0017 a post** ($1.70 per 1,000); `post-details` $0.001 and `music-data` $0.007 events exist but aren't requested | `username: [profile URL]`, `resultsLimit`, `onlyPostsNewerThan` (`YYYY-MM-DD`, ISO or "2 months") | `url`/`shortCode`, `timestamp`, `caption`, `displayUrl`, `videoUrl`, `childPosts[]` (carousels), `type` | The cheapest of Apify's own Instagram Actors that returns post URL, date, caption and media |
| `apify/instagram-scraper` | $0.0027 a result | `directUrls`, `resultsType: posts`, `resultsLimit`, `onlyPostsNewerThan` | same shape | More content types; dearer |
| `apidojo/instagram-scraper` (community) | $0.0005 an item | `startUrls`, `maxItems`, `until` | not verified | About a third of the price; no `onlyPostsNewerThan`; untested. Swap in with `HUNT_APIFY_ACTORS` once its output is checked |
| **`apify/facebook-posts-scraper`** (default) | **$0.005 a post**, plus $0.002 a post when a date filter applies and $0.001 an Actor start; Hunt budgets **$0.007 a post** | `startUrls: [{url}]`, `resultsLimit`, `onlyPostsNewerThan`, `onlyPostsOlderThan` | `url`, `postId`, `time`, `text`, `media[].photo_image.uri`, `media[].thumbnail`, `user` | Public Pages only, "not personal profiles" (input schema). The README says the Free plan reaches "up to 1,000 posts (700 with the date filter)" a month |
| `curious_coder/facebook-post-scraper` (community) | $0.0015 an item + $0.005 an Actor start | `urls`, `count`, `scrapeUntil` | not verified | Takes a `cookie` input, which Hunt would never set; untested |

**Budget at the defaults** (`results_limit` 100, `fresh_days` 7, `monthly_cap_usd` 5): the first read of an account costs about $0.17 (Instagram) or $0.70 (Facebook); re-checks pass `onlyPostsNewerThan` the last read, so they cost only what is new; an account read in the last 7 days isn't run again unless asked. Apify stops a single run at `maxTotalChargeUsd` = 1.25 × the estimate + $0.01, and Hunt refuses a run that would take the month past the cap or the plan's credit.

**Settings.** The key is `HUNT_APIFY_TOKEN`, pasted on the app's "Connect free keys" screen (`hunt/keys.py` keeps it in `HUNT_HOME/keys.json`, mode 600, and in the process environment; `vendor.py` declares it in `keys.EXTRA`). The rest (`actors`, `price_per_post`, `monthly_cap_usd`, `results_limit`, `fresh_days`) live in `HUNT_HOME/vendor.json`, mode 600; `HUNT_APIFY_ACTORS` overrides the Actors. `vendor.shown()` gives them to the app with the key as a yes/no; `vendor.save_settings(**changes)` stores them. The key is never written into a case or an evidence bundle. A post Hunt Capture already holds (same URL, any source) isn't stored again; Facebook URLs are canonicalised as `facebook._canon` does, so a vendor post and the same post she views merge.

**Not built.** TikTok through a vendor (the logged-out page reads cover it), X, LinkedIn, any Actor that needs cookies or a login, and any shared or bundled key.
