# Open-source tools and free APIs to build on

_Research date: 2026-10-29. Licences and last-commit dates come from the GitHub API on that date. Items marked **(unverified)** could not be confirmed from a primary source._

## Licence compatibility (Hunt is AGPL-3.0)

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
| **Bluesky (atproto)**, **Mastodon**, **GitHub** APIs | Official/open | Free | Low. **Wired in**, see [API sources in Hunt](#api-sources-in-hunt) |
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
| **OpenFEC** | `DEMO_KEY` (headers show 10 req/hr); free api.data.gov key 1,000 req/hr | Donor name, city, employer, occupation. **Wired in.** Use limits apply (see below) |
| **SEC EDGAR** | Keyless JSON, 10 req/s, User-Agent required | Insiders as filers; full-text search of filings. **Wired in** |
| **CourtListener / RECAP** | **Token required for every API call** (anonymous gets 401/403) | Free account reportedly 5/min, 50/hr, 125/day since 2026-05-07 (official docs still say 5,000/hr). **Wired in, opt-in** |
| **NPPES NPI Registry** | Keyless, no published limit | US healthcare providers by name. **Wired in** |
| **Wayback CDX** | Free, no key | ~60 req/min (2023 maintainer figure); back off on 429. **Wired in** |
| **Nominatim / OSM** | Public instance 1 req/s, ODbL attribution | Self-host for scale |
| PACER | $0.10/page (rising to $0.12 on 2027-01-01) | Not free; out of MVP |
| OpenCorporates | Free only for journalists/NGOs/academics | Paid investigators likely don't qualify |
| NSOPW / sex-offender registries | **No API; terms forbid automated search** | Link out only |
| Property/assessor | County by county, no free national API | Out of MVP |

## API sources in Hunt

_Checked live on 2026-10-29, logged out, with public organisations' handles, `example.com` emails and a made-up name. Each is one module in `hunt/sources/`, through `HUNT_PROXY`. Every key is optional and off by default._

| Source (module) | Seed → what it returns | Limits, logged out | Key | Terms and caveats |
|---|---|---|---|---|
| **GitHub** (`github`) | username → name, location, blog, bio, company, public email, Twitter handle, social links, avatar. Name or email → user search, first 10 profiles read | 60 profile reads/hr, 10 searches/min per IP; responses cached a day | `HUNT_GITHUB_TOKEN` (5,000/hr) | AUP bans selling personal data taken from GitHub (e.g. to recruiters) and spam |
| **Gravatar** (`gravatar`) | email → display name, location, job, company, avatar, **verified accounts** (owner signed in to each) | 100 profile lookups/hr; at most 4 verified accounts; no contact info | `HUNT_GRAVATAR_KEY` (1,000/hr, all accounts) | Docs discourage unauthenticated use but allow it |
| **Keybase** (`keybase`) | username → full name, location, bio, and accounts **proven with signed statements**. Looked up as Keybase, GitHub and Twitter handle | None published; 3 requests per username | none | Maintenance mode (Zoom); proofs only count while live |
| **Bluesky** (`bluesky`) | username → profile at `<u>.bsky.social` or a domain handle (domain = proven website). Name → actor search (loose: any word matches) | Unpublished, "generous" (public AppView) | none | Public AppView meant for this use |
| **Mastodon** (`mastodon`) | name → accounts mastodon.social knows. Username → exact-handle matches across instances. `@user@instance` → WebFinger on that instance. Returns display name, bio, profile fields, `rel=me` verified links | mastodon.social 300 req / 5 min per IP | none | `resolve=false`: never makes mastodon.social fetch remote servers |
| **Stack Exchange** (`stackexchange`) | name → Stack Overflow users whose display name contains it (username → exact matches). Location, website, and the email's MD5 from Gravatar avatars | 300 req/day per IP; `backoff` obeyed | none | Content CC BY-SA |
| **keys.openpgp.org** (`openpgp`) | email → key fingerprint, the name on the key, other confirmed addresses | Rate-limited, numbers unpublished | none | Identities appear only after the owner confirms by email |
| **Wayback CDX** (`wayback`) | url → capture history. Username → archived profiles on X/Twitter, Instagram, Facebook, TikTok, Reddit, YouTube (deleted accounts) | ~60/min; Hunt sends 1/s and stops at a 429 | none | An archived URL isn't proof an account existed |
| **OpenFEC** (`fec`) | name → itemized contributions (> $200) grouped per donor: city, ZIP, employer, occupation, totals, recipients, filing images | `DEMO_KEY` 10/hr | `HUNT_FEC_KEY` (1,000/hr) | **52 U.S.C. 30111(a)(4) / 11 CFR 104.15:** no use to solicit contributions or for commercial purposes like marketing. A report isn't solicitation; the firm should confirm |
| **SEC EDGAR** (`edgar`) | name → filers with their own CIK (insiders; address of record, form types) and companies whose filings contain the exact name | 10 req/s; ≤ 7 requests per name | `HUNT_SEC_UA` (your firm + contact) | SEC's firewall 403s any User-Agent containing "github.com" |
| **NPI Registry** (`npi`) | first + last name → providers' practice address and phone, specialty, licence numbers, **former names** | None published | none | Public CMS data (FOIA) |
| **CourtListener** (`courtlistener`) | name → federal RECAP dockets with that party: case, court, docket number, dates, parties | Free account 5/min, 50/hr, 125/day (third-party report) | `HUNT_COURTLISTENER_TOKEN`, **required**; off without it | RECAP is a sample of PACER, not every case |

### Considered and rejected

| Candidate | Why not |
|---|---|
| ORCID public API | Free only for non-commercial use: no use "in connection with any revenue-generating product or service". A paid investigation is that. The CC0 annual data file is the lawful route if academics matter |
| npm registry (maintainer emails) | npm's terms: "You will not copy or share any personally identifiable information of any other person without their specific permission" |
| GitHub commit emails (events API) | Harvesting authors' emails from commits is the use GitHub's AUP targets; profile `email` (public by choice) is kept |
| GitLab API | `/users/:id` (bio, location, links) now needs a login; logged out gives only name and avatar, and Maigret already checks existence |
| Docker Hub | Profiles rarely filled in (full name, location, company); Maigret covers existence |
| PyPI | No user API; user pages are behind a client challenge |
| FINRA BrokerCheck | Terms limit use to investor-protection, compliance or regulatory purposes, and forbid bulk automated collection |
| OFAC SDN list | Free and lawful, but a bulk list with fuzzy name matching, not a search API. Worth a separate sanctions-screen step |

## Image / identity

- **Reverse image search:** no free web-wide API. Bing Visual Search was retired Aug 2025. TinEye and Google Cloud Vision are paid. Hunt offers "open in browser" actions the investigator chooses, never automatic uploads.
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
| Skopenow | Automated person reports with match scoring. **Closest to Hunt.** |
| Pipl | Identity-resolution API over a large linked index |
| Social Links, ShadowDragon | Deep social/network mapping for law enforcement |
| IntelTechniques tools | Browser-side search URL builders |
| OSINT Framework | Free link directory, not an engine |
| TLOxp, Accurint, IRB, Tracers | Credit-header broker data (addresses, relatives, phones). **No OSS can replicate this; Hunt complements it.** |

## MVP picks

1. Maigret (core username engine)
2. WhatsMyName data (second engine)
3. user-scanner (email/username registration)
4. python-phonenumbers
5. rapidfuzz + jellyfish + nameparser + nicknames + usaddress for scoring (Splink later)
6. OpenFEC + SEC EDGAR (done)
7. CourtListener (done; opt-in token)
8. Wayback CDX (done)
9. Bluesky / Mastodon / GitHub official APIs (done); YouTube still to do
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
- API sources: [GitHub rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api), [GitHub AUP](https://docs.github.com/en/site-policy/acceptable-use-policies/github-acceptable-use-policies), [Gravatar REST API](https://docs.gravatar.com/rest-api/), [Bluesky rate limits](https://docs.bsky.app/docs/advanced-guides/rate-limits), [Mastodon rate limits](https://docs.joinmastodon.org/api/rate-limits/), [Stack Exchange throttles](https://api.stackexchange.com/docs/throttle), [SEC EDGAR access](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data), [NPI registry API (no documented limit)](https://docs.ropensci.org/npi/articles/npi.html)
- CourtListener limits: [free.law issue #7200](https://github.com/freelawproject/courtlistener/issues/7200), [third-party guide](https://www.vaquill.ai/blog/how-to-use-courtlistener-api)
- FEC use restriction: [FEC: sale or use of contributor information](https://www.fec.gov/updates/sale-or-use-contributor-information), [11 CFR 104.15](https://www.law.cornell.edu/cfr/text/11/104.15)
- Rejected: [ORCID API limits](https://info.orcid.org/ufaqs/what-are-the-api-limits/), [ORCID public API terms](https://info.orcid.org/public-client-terms-of-service/), [npm open-source terms](https://docs.npmjs.com/policies/open-source-terms), [BrokerCheck permitted uses](https://www.finra.org/investors/investing/working-with-investment-professional/about-brokercheck/permitted-uses)
- [Maltego plans](https://docs.maltego.com/support/solutions/articles/15000036759-maltego-products-and-plans)
- [IntelTechniques tools](https://inteltechniques.com/tools/)
- [OSINT Industries pricing](https://www.techjockey.com/detail/osint-industries)
- [Skopenow comparison](https://www.skopenow.com/people-and-business-search-comparison)
- [holehe vs user-scanner](https://dev.to/the_king89/rip-holehe-why-user-scanner-is-the-new-king-of-email-osint-2cff)
