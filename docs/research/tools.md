# Open-source tools and free APIs to build on

_Research date: 2026-10-29. Licences and last-commit dates come from the GitHub API on that date. Items marked **(unverified)** could not be confirmed from a primary source._

## Licence compatibility (Tessera is AGPL-3.0)

- **MIT, BSD, Apache-2.0, Unlicense, GPL-3.0, AGPL-3.0:** can be embedded directly.
- **GPL-2.0-only:** incompatible with (A)GPL-3; run it as a separate subprocess only.
- **No licence:** no rights granted; don't embed.
- **CC BY-SA data** (WhatsMyName): usable with attribution; modified data stays CC BY-SA. Don't use the "WhatsMyName" name for a product.

## Username enumeration

| Tool | Licence | Activity | Library? | Notes |
|---|---|---|---|---|
| **Maigret** | MIT, Python | v0.6.6 (2026-09-18), commits daily | Yes, documented import API | 3K+ sites; parses profiles for IDs/links and searches recursively. **Core pick.** |
| **WhatsMyName** data (`wmn-data.json`) | CC BY-SA 4.0 | 2026-10-27 | JSON file | 700+ sites, curated for low false positives. Second engine: agreement raises confidence. |
| Sherlock | MIT, Python | v0.16.2 (2026-09-08) | CLI-first, no documented API | 400+ sites. Optional plugin. |
| user-scanner | MIT, Python | v1.5.2 (2026-09-17) | Yes | Usernames *and* emails. |
| Naminter | MIT, Python | 2026-08 | Async lib over WMN data | Small project. |
| social-analyzer | AGPL-3.0, JS+Py | 2026-01 | Python API | Activity slowing. |
| Blackbird | **No licence file** | 2026-10 | CLI | **Do not embed.** Uses WMN data; use WMN directly. |

## Email

| Tool | Licence | Status | Notes |
|---|---|---|---|
| **user-scanner** | MIT | Active | Registration checks across ~95 platforms. **Pick.** Replaces holehe. |
| holehe | GPL-3.0 | **Stale** (last commit 2024-09), modules reported broken | Registration/password-reset checks, medium ToS risk. |
| GHunt | AGPL-3.0 | Commits to 2026-04 | **Needs Google session cookies from a burner account.** High ToS risk, so optional plugin only. |
| Mailcat | Apache-2.0 | Active | Finds which providers have a mailbox for a username. |
| h8mail | BSD-3 | **Dead** (2022) | Needs breach API keys. |
| HIBP API | Commercial | n/a | **No free email search.** Core 1 is $4.39/mo (10 RPM). Bring-your-own key, off by default. |

## Phone

| Tool | Licence | Notes |
|---|---|---|
| **python-phonenumbers** / libphonenumber-js | Apache-2.0 / MIT | Offline validation, normalisation, region, original carrier, line type. Every phone input goes through this. |
| PhoneInfoga | GPL-3.0, Go | Last release 2024-02. Mostly Google dorks plus numverify (needs a key). Low value. |
| ignorant | GPL-3.0 | Stale (2023-12), likely broken. |

Live carrier/CNAM lookup needs paid services (e.g. Twilio Lookup), so it's out of scope.

## Frameworks / aggregators (the existing landscape)

| Tool | Licence | Status | Fit |
|---|---|---|---|
| SpiderFoot (upstream) | MIT | **Dormant**: last default-branch commit 2023-11, v4.0 in 2022 | 200+ modules, infrastructure-focused |
| SpiderFoot fork (poppopjmp) | MIT | v6.1.0 (2026-06) | Small community |
| recon-ng | GPL-3.0 | Commits to 2026-10, no tagged releases | Infrastructure; many modules need keys |
| theHarvester | **GPL-2.0-only** | 4.11.1 (2026-06) | Domains/emails; subprocess only |
| BBOT | AGPL-3.0 | Very active | Attack surface, not people |

**None of these is person-centric.** Identity scoring plus an evidence-grade report is the open gap.

## Social platforms

| Option | Licence | Status | Risk |
|---|---|---|---|
| **YouTube Data API v3** | Official | Free, 10K units/day | Low |
| **Bluesky (atproto)**, **Mastodon**, **GitHub** APIs | Official/open | Free | Low, easy wins |
| instaloader | MIT | v4.16 (2026-10-26) | Logged-out access heavily throttled; login risks bans. High. |
| twscrape | MIT | v0.20.1 (2026-08) | Needs X accounts/cookies. High. |
| TikTok-Api | MIT | v7.3.3 (2026-04) | Unofficial, Playwright-based, fragile |
| PRAW (Reddit) | BSD-2 | Active | New OAuth apps need manual approval since Nov 2025 |
| X official API | n/a | Pay-per-use since Feb 2026, no free read tier (third-party reporting) | Low risk, not free |
| yt-dlp | Unlicense | Active | Medium |
| Telethon | MIT | Moved to Codeberg; needs Telegram api_id | Medium |
| snscrape | GPL-3.0 | **Dead** (2023-11) | n/a |

## Public records (free APIs)

| Source | Access | Notes |
|---|---|---|
| **OpenFEC** | Free api.data.gov key (~1,000 req/hr, **unverified**) | Donor name, address, employer, occupation: strong identity anchor |
| **SEC EDGAR** | Free JSON at data.sec.gov, 10 req/s, User-Agent required | Officers, insiders |
| **CourtListener / RECAP** | Free API token | **Free limits cut 2026-05-07**; exact new limits **unverified** |
| **Wayback CDX** | Free, no key | ~60 req/min community estimate; back off on 429 |
| **Nominatim / OSM** | Public instance 1 req/s, ODbL attribution | Self-host for scale |
| PACER | $0.10/page (rising to $0.12 on 2027-01-01) | Not free; out of MVP |
| OpenCorporates | Free only for journalists/NGOs/academics | Paid investigators likely don't qualify |
| NSOPW / sex-offender registries | **No API; terms forbid automated search** | Link out only |
| Property/assessor | County by county, no free national API | Out of MVP |

## Image / identity

- **Reverse image search:** no free web-wide API. Bing Visual Search was retired Aug 2025. TinEye and Google Cloud Vision are paid. Tessera offers "open in browser" actions the investigator chooses, never automatic uploads.
- **EXIF:** ExifTool (GPL/Artistic, subprocess); exif-py (BSD-3). Most platforms strip EXIF.
- **Face recognition:** out of MVP (see `legal.md` and `geolocation.md`).

## Entity resolution / name matching

| Library | Licence | Status | Use |
|---|---|---|---|
| **Splink** | MIT | v5.0.0 (2026-09-18) | Fellegi-Sunter probabilistic matching with explainable weights. Target once labelled data exists. |
| **rapidfuzz**, **jellyfish** | MIT | Active | Fuzzy + phonetic string matching |
| **nameparser** | LGPL-2.1+ | Active | Name components (fine as a dependency) |
| **nicknames** | Apache-2.0 | Active | Bob ↔ Robert |
| **probablepeople**, **usaddress** | MIT | 2025 | Name/address parsing |
| libpostal | MIT, C | 2026-05 | International address normalisation |
| dedupe | MIT | Last commit 2025-07 | Needs active-learning labels |
| recordlinkage | BSD-3 | Stale (2023) | n/a |
| Zingg | AGPL-3.0, Java/Spark | Active | Too heavy |

## Commercial landscape (what investigators pay for)

| Product | Strength |
|---|---|
| OSINT Industries | Real-time email/phone/username lookups, clean reports; from ~£19/mo (third-party figure) |
| Maltego | Graph link analysis plus a transform marketplace; Pro ~$5–6.6K/yr |
| Skopenow | Automated person reports with match scoring. **Closest to Tessera.** |
| Pipl | Identity-resolution API over a large linked index |
| Social Links, ShadowDragon | Deep social/network mapping for law enforcement |
| IntelTechniques tools | Browser-side search URL builders |
| OSINT Framework | Free link directory, not an engine |
| TLOxp, Accurint, IRB, Tracers | Credit-header broker data (addresses, relatives, phones). **No OSS can replicate this; Tessera complements it.** |

## MVP picks

1. Maigret (core username engine)
2. WhatsMyName data (second engine)
3. user-scanner (email/username registration)
4. python-phonenumbers
5. rapidfuzz + jellyfish + nameparser + nicknames + usaddress for scoring (Splink later)
6. OpenFEC + SEC EDGAR
7. CourtListener
8. Wayback CDX
9. YouTube / Bluesky / Mastodon / GitHub official APIs
10. HIBP (bring your own key, off by default)
11. Nominatim + ExifTool

**Optional user-enabled subprocess plugins** (GPL or ToS risk; user supplies their own sessions): Sherlock, GHunt, instaloader, twscrape, PhoneInfoga, theHarvester.

**Excluded:** Blackbird (no licence), NSOPW scraping, face recognition, upstream SpiderFoot (dormant), snscrape and h8mail (dead).

## Sources

- Repos: [maigret](https://github.com/soxoj/maigret), [sherlock](https://github.com/sherlock-project/sherlock), [WhatsMyName](https://github.com/WebBreacher/WhatsMyName), [user-scanner](https://github.com/kaifcodec/user-scanner), [Naminter](https://github.com/3xp0rt/Naminter), [blackbird](https://github.com/antoniaci/blackbird), [social-analyzer](https://github.com/qeeqbox/social-analyzer), [holehe](https://github.com/megadose/holehe), [GHunt](https://github.com/mxrch/GHunt), [h8mail](https://github.com/khast3x/h8mail), [mailcat](https://github.com/sharsil/mailcat), [phoneinfoga](https://github.com/sundowndev/phoneinfoga), [ignorant](https://github.com/megadose/ignorant), [python-phonenumbers](https://github.com/daviddrysdale/python-phonenumbers), [spiderfoot](https://github.com/smicallef/spiderfoot), [spiderfoot fork](https://github.com/poppopjmp/spiderfoot), [recon-ng](https://github.com/lanmaster53/recon-ng), [theHarvester](https://github.com/laramies/theHarvester), [bbot](https://github.com/blacklanternsecurity/bbot), [instaloader](https://github.com/instaloader/instaloader), [twscrape](https://github.com/vladkens/twscrape), [TikTok-Api](https://github.com/davidteather/TikTok-Api), [Telethon](https://codeberg.org/Lonami/Telethon), [splink](https://github.com/moj-analytical-services/splink), [dedupe](https://github.com/dedupeio/dedupe), [zingg](https://github.com/zinggAI/zingg)
- [HIBP pricing](https://haveibeenpwned.com/Subscription)
- CourtListener: [Free Law Project 2026-05-07](https://free.law/2026/05/07/api-included-in-memberships/), [third-party limits guide](https://www.vaquill.ai/blog/how-to-use-courtlistener-api-2026)
- [PACER fee change](https://www.njb.uscourts.gov/news/temporary-pacer-fee-increase-effective-january-1-2027)
- NSOPW: [suspended](https://www.nsopw.gov/suspended), [conditions](https://organizations.nsopw.gov/Conditions)
- OpenCorporates: [pricing](https://opencorporates.com/pricing/), [terms](https://opencorporates.com/terms-of-use-2/)
- [Reddit API 2026](https://www.redditapis.com/blogs/reddit-data-api-2026)
- [X pay-per-use](https://opentermsarchive.org/en/memos/x-replaces-its-dollar200-entry-level-api-plan-with-a-pay-per-use-model/)
- [Wayback rate limit](https://cirosantilli.com/wayback-machine-rate-limit)
- [Maltego plans](https://docs.maltego.com/support/solutions/articles/15000036759-maltego-products-and-plans)
- [IntelTechniques tools](https://inteltechniques.com/tools/)
- [OSINT Industries pricing](https://www.techjockey.com/detail/osint-industries)
- [Skopenow comparison](https://www.skopenow.com/people-and-business-search-comparison)
- [holehe vs user-scanner](https://dev.to/the_king89/rip-holehe-why-user-scanner-is-the-new-king-of-email-osint-2cff)
