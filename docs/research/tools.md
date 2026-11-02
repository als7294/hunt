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
| **Maigret** | MIT, Python | v0.6.6 (2026-09-18), commits daily | Yes, documented import API | 3K+ sites; parses profiles for IDs/links and searches recursively. **Core pick**, pinned; Hunt checks 385 of its top 509 honestly (see Collection narrowed) |
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
| **YouTube Data API v3** | Official | Free, 10K units/day | Low. **Wired in** on `HUNT_YOUTUBE_KEY` (`public.py`); without a key there is no read, since YouTube's robots.txt disallows its feed |
| **Bluesky (atproto)**, **Mastodon**, **GitHub** APIs | Official/open | Free | Low. **Wired in**, see [API sources in Hunt](#api-sources-in-hunt) |
| instaloader | MIT | v4.16 (2026-10-26) | Logged-out access heavily throttled; login risks bans. High. |
| twscrape | MIT | v0.20.1 (2026-08) | Needs X accounts/cookies. High. |
| TikTok-Api | MIT | v7.3.3 (2026-04) | Unofficial, Playwright-based, fragile |
| PRAW (Reddit) | BSD-2 | Active | New OAuth apps need manual approval since Nov 2025 |
| X official API | n/a | Pay-per-use since Feb 2026, no free read tier (third-party reporting) | Low risk, not free |
| **yt-dlp** | Unlicense | 2026.8.19 pinned | Medium. **Wired in** to download a TikTok video from its page URL only; its profile listing calls an internal API and isn't used. See [Public posts, logged out](#public-posts-logged-out-tiktok-pages-the-youtube-data-api-apify) |
| Telethon | MIT | Moved to Codeberg; needs Telegram api_id | Medium |
| gallery-dl | **GPL-2.0-only** | 1.32.16 | Worked on Facebook Page photos as a subprocess; **parked** (Facebook robots default-deny), not a dependency |
| snscrape | GPL-3.0 | **Dead** (2023-11) | n/a |

### Public posts, logged out (TikTok pages, the YouTube Data API, Apify)

_Checked live on 2026-10-29 with the public organisation account `nasa` only, logged out, with Hunt's User-Agent. Policy: [automation-legal.md §4](automation-legal.md). Modules: `hunt/public.py` (TikTok, YouTube; in `posts.FETCHERS` beside Bluesky and Mastodon) and `hunt/vendor.py` (Apify, opt-in, see [vendors.md](vendors.md)). No private individual's account is used in any test._

| Platform | How Hunt reads it | What a logged-out visitor gets today | Where the wall starts | Caps |
|---|---|---|---|---|
| **TikTok** | The profile and video pages' `__UNIVERSAL_DATA_FOR_REHYDRATION__` JSON, Hunt's UA, a second apart. yt-dlp 2026.8.19 (`--ignore-config --no-plugin-dirs --no-cache-dir --no-cookies-from-browser --xff never`, `--retries 1`) downloads a video **from its page URL** only | **Profile page:** bio, verified and private flags, the uploader's download setting, follower, like and video counts, and an **empty item list** (`videoCount` 61, `itemList []`), so there is no profile listing without the internal API. **Video page:** caption, `createTime`, duration, cover, the author's `downloadSetting`; then the MP4 (16 s = 5.5 MB). **Photo post:** its images. Video URLs come from pasted links, the Downloads inbox, links in other posts, or the Hunt Browser | yt-dlp's own profile listing calls `/api/creator/item_list/` with a random `verifyFp` and a device id: an internal API, **not used** (US terms §3.4). robots.txt disallows `/embed/@` and `/search` (skipped). A 429, CAPTCHA page, login redirect or "IP blocked" status (10204) stops the read; a private account or post (10216, 10222) is reported as such | `MAX_POSTS` listed; `MAX_VIDEO_BYTES` 500 MB a video; `MAX_ACCOUNT_BYTES` 5 GB an account per read; downloads turned off by the uploader → the cover image only (§3.5) |
| **YouTube** | The Data API v3 on `HUNT_YOUTUBE_KEY`: `channels.list` (`forHandle`, `forUsername` or `id`; 1 unit) → the uploads playlist → `playlistItems.list` (50 per unit), newest first, stopped at `since`. Without a key, no read: a failed note says YouTube's robots.txt disallows its feed and names the key | Every upload with its full description, published time and thumbnails (kept as evidence copies). Videos aren't downloaded | Quota 10,000 units a day per project; `quotaExceeded` or `keyInvalid` become a failed note. Developer Policies III.E.4: API data is stored at most 30 days unless refreshed or deleted (how a case file complies is for counsel; the note says so) | `MAX_POSTS` |
| **Instagram, Facebook, Threads, X, LinkedIn, Reddit, Strava, Snapchat, Telegram** | **Not read automatically** (`public.ROBOTS_DENY`, legal.md C1 and C6, decision D2; Telegram by its terms, which bar using its data for machine learning: automation-legal.md). The fetcher answers with a note; a `threads.net/@user` address is never taken for a Mastodon handle. Instagram and Facebook come through the Hunt Browser, or through Apify on the investigator's own key | — | at the first request | — |
| X, Threads | **Not collected.** gallery-dl: `AuthRequired`, "authenticated cookies needed to access this timeline"; yt-dlp has no profile support (a single tweet only when it holds a video); Threads is unsupported in both; robots default-deny | — | at the profile | — |

**Tried and parked on 2026-10-29.** gallery-dl 1.32.16 walked a public Facebook Page's photos (fbid, caption, UTC date, CDN image that fetched logged out; one request per photo; `abort()` filter at `since`) and Instagram's per-post embed page (`/p/<code>/embed/captioned/`: caption, image or video, carousel children; `/<user>/embed/` listed the latest 6 posts). Both worked on `nasa` and both were dropped on the legal brief: Facebook's robots.txt is `Disallow: /` for unnamed agents, and Meta's embed terms bar storage and analysis. The code and its tests are on branch `parked/hunt-facebook-instagram-readers` (commit `7374c04`). yt-dlp's TikTok profile listing also worked (61 videos, streamed, stopped at `since`) and was dropped for the internal API it calls.

**Walls and hard stops** (legal.md C7, C8; decision D8). Every automatic read first asks `public.blocked(url)`: a platform under a capture hard stop (`browser.stops()`) is skipped with a note until she resumes it from the app. A 429 ends that platform's reads for the rest of the run (the remaining accounts are skipped with "stopped after a rate limit on …"); a CAPTCHA page, an IP-block status or a login redirect also sets a hard stop through `browser.stop`, audited `capture hard stop`. Nothing is retried. TikTok page requests keep at least `SLEEP` (1 s) apart, and yt-dlp is refused outright if `curl_cffi` would let it impersonate a browser (`public.impersonation()`; none installed today).

**What the records say.** The source note per account: how it was read, posts found, `since`, the caps or the API terms, and the wall if one was hit. The audit log: `posts collected`, `media downloaded` (tool and version, file, bytes), `media not saved` (the tool's words: a 429, a cap, downloads off). Vendor runs: `vendor run` (vendor, Actor, build, run id, status, cost, account, posts) and `vendor posts collected`.

## Public records (free APIs)

| Source | Access | Notes |
|---|---|---|
| **OpenFEC** | `DEMO_KEY` (headers show 10 req/hr); free api.data.gov key 1,000 req/hr | Donor name, city, employer, occupation. **Wired in.** Use limits apply (see below) |
| **SEC EDGAR** | Keyless JSON, 10 req/s, User-Agent required | Insiders as filers; full-text search of filings. **Wired in** |
| **CourtListener / RECAP** | **Token required for every API call** (anonymous gets 401/403) | 5/min, 50/hr, 125/day for authenticated users (API docs, 2026-10-29). Federal RECAP dockets by party and state and federal case law by caption. **Wired in, opt-in** |
| **NPPES NPI Registry** | Keyless, no published limit | US healthcare providers by name. **Wired in** |
| **Wayback CDX** | Free, no key | ~60 req/min (2023 maintainer figure); back off on 429. **Wired in** |
| **Nominatim / OSM** | Public instance 1 req/s, ODbL attribution | Self-host for scale |
| PACER | $0.10/page (rising to $0.12 on 2027-01-01) | Not free; out of MVP. The Case Locator API needs a PACER login and bills each search page, so it is a by-hand link (see Court records) |
| **State licence and business portals** (Socrata, one ArcGIS layer) | Keyless; throttled by IP; free app token ~1,000 req/hr | TX, CO, DE, IL, WA, OR, CT, NY, VT and NYC licences; NY, OR, CT, CO, PA, DE and DC business records. **Wired in** |
| **State bulk licence and business files** | Free downloads, loaded once into local tables | FL (DBPR licences; Sunbiz, imported by hand), VA, MN, NV, WV licences. **Wired in**; every state's channel is in [State records](#state-records-business-entities-and-licences) |
| **FMCSA carrier census** | Keyless (data.transportation.gov) | Owner-operators and carrier officers. **Wired in** |
| **OpenPowerlifting** | Public-domain bulk file (170 MB zip, 829 MB CSV, weekly) | Every powerlifting meet it can find, worldwide: 4.05M entries at 64.6K meets. **Wired in** (`activity`) as a local table loaded once; see [Activity records](#activity-records) |
| **Court and hearing tables** (Socrata) | Keyless | NYC Housing Court, suits against NYC, OATH trials and DOB/ECB summonses, NYS tax warrants, Ohio Court of Claims, Chicago administrative hearings, Texas TCEQ judgments. **Wired in** (`courts`). Every other court portal is opened by hand: see [Court records](#court-records) |
| **Florida voter roll** | The Division of Elections' monthly extract, free to anyone who asks (a public record; Florida puts no use condition on it) | Name → every registered voter of that name: residence address, birth date, registration date, status, household. **Wired in** (`voter`) as a local table the investigator loads from the files; Florida only, see [Voter registration](#voter-registration) |
| OpenCorporates | API key required; free keys only for public-benefit "Permitted Users" | Commercial use needs a paid key: rejected |
| FAA airmen registry | Monthly ZIP of CSVs (registry.faa.gov) | Server answers scripted requests with 503; not automated (see below) |
| NSOPW / sex-offender registries | **No API; terms forbid automated search** | Link out only |
| Property/assessor | County by county, no free national API | **Wired in** for FL (statewide), CT, NY, NYC, Cook, Harris, Philadelphia and seven more: see [Property](#property) |

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
| **Wayback CDX** (`wayback`) | url → capture history. Username → archived profiles on X/Twitter, Instagram, TikTok, Reddit, YouTube (deleted accounts; Facebook is the `facebook` source's) | ~60/min; Hunt sends 1/s and stops at a 429 | none | An archived URL isn't proof an account existed |
| **OpenFEC** (`fec`) | name → itemized contributions (> $200) grouped per donor: city, ZIP, employer, occupation, totals, recipients, filing images | `DEMO_KEY` 10/hr | `HUNT_FEC_KEY` (1,000/hr) | **52 U.S.C. 30111(a)(4) / 11 CFR 104.15:** no use to solicit contributions or for commercial purposes like marketing. A report isn't solicitation; the firm should confirm |
| **SEC EDGAR** (`edgar`) | name → filers with their own CIK (insiders; address of record, form types) and companies whose filings contain the exact name | 10 req/s; ≤ 7 requests per name | `HUNT_SEC_UA` (your firm + contact) | SEC's firewall 403s any User-Agent containing "github.com" |
| **NPI Registry** (`npi`) | first + last name → providers' practice address and phone, specialty, licence numbers, **former names** | None published | none | Public CMS data (FOIA) |
| **CourtListener** (`courtlistener`) | name → federal RECAP dockets with that party (case, court, docket number, dates, parties, nature of suit) and **case law** with the name in the caption (every state's appellate courts, federal appellate and district opinions: case, court, docket number, date, citation, judge, parties split from the caption) | 5/min, 50/hr, 125/day per account (API docs); two requests per name | `HUNT_COURTLISTENER_TOKEN`, **required**; off without it | RECAP is a sample of PACER, not every case. A state trial case appears only if it was appealed |
| **Competition results** (`activity`) | first + last name → OpenPowerlifting lifters (namesakes split by the data's own "#n"): every meet with date, meet, town, federation, division, weight class, lifts, total, place, tested; `first_date`/`last_date`, `birth_year` from the age at the latest meet, home state and country | Local table, no network; `python -m hunt.sources.activity update` loads or refreshes it (one HEAD, then the download only when upstream changed) | none | Public domain. Race results (Athlinks, RunSignup, UltraSignup, ITRA, CrossFit, USMS, USA Cycling, NYRR) are `activity.search_links` by-hand pages |
| **Court and hearing tables** (`courts`) | first + last name → cases naming the person in 8 official tables: NYC Housing Court cases (HPD v. owner), civil suits by or against the City of New York (court, index number, disposition, payout), OATH trials (city employee discipline, licence matters), DOB summonses heard at OATH/ECB (respondent's address, hearing result, penalty), NYS tax warrants (docketed judgments: amount, county, the warrant PDF), Ohio Court of Claims (claims against the state), Chicago administrative hearings (ordinance violations: hearing, disposition, fine), Texas TCEQ civil judgments. Each record: court, case or docket number, the person's **role** (plaintiff, defendant, respondent, debtor…), filing date, case type, status or disposition, and the city or address shown | Socrata: throttled by IP; one request per table per name, 50 rows each | `HUNT_SOCRATA_TOKEN` | Public records. Coverage is a few jurisdictions, never a state's whole docket; `courts.search_links(seeds)` gives the portals to open by hand |
| **Voter roll** (`voter`) | first + last name → the registered voters of that name in the Florida extract indexed on this Mac (actives first): `fullname` as registered, `dob`, `address` as one postal line, `location`, `county`, `registered`, `status`, `voter_id`. Runs only when the case's city, street, ZIP, date of birth or age narrows the name, 10 voters at most; household and evidence row stored only on "him"; never on a background case | Local table, no network; `python -m hunt.sources.voter update` indexes the files the investigator put in `~/Hunt/voter/FL/` | none | Public record (Fla. Stat. 97.0585 lists the confidential fields; exempt voters are left out by the Division). Party and race are dropped at import. Pennsylvania's list is for election use only: not built |
| **State licences** (`licences`) | first + last name → licences in 27 official tables: TX TDLR trades, TX real estate and inspectors (with sponsoring broker), TX Medical Board (with **year of birth**), TX TDI insurance agents and adjusters, TX notaries, CO DORA (all professions, with verify link) and real estate, DE (all professions, notaries), IL IDFPR, WA L&I contractors and their principals (with dates), WA DOH health professions (with **year of birth**), WA CPAs, OR CCB contractors, building trades and notaries, CT DCP (every credential), NY real estate, barbers and cosmetology, home inspectors, appraisers, notaries and attorneys, NYC Buildings, VT fire-safety trades. Plus local tables once loaded: FL DBPR, VA DPOR, MN DLI, NV real estate, WV Board of Medicine. Licence type and number, status, issue and expiry dates, business, street and city | Socrata: throttled by IP; one request per dataset per name, 50 rows each. Local tables: no network | `HUNT_SOCRATA_TOKEN` (~1,000/hr) | Public records; most tables public domain. Coverage is per state, never national: [State records](#state-records-business-entities-and-licences) |
| **Business registries** (`businesses`) | first + last name → businesses the person runs or fronts: NY active corporations (chief executive, registered agent, process name), OR active businesses (every role, including sole-proprietor registrants), CT principals and registered agents (role, town; business name joined in), CO registered agents and trade-name registrants, PA parties, DE trade-name filers and affiants, DC business-licence owners and agents (ArcGIS). Plus local tables once loaded: FL Sunbiz officers, registered agents and fictitious-name owners. Role, business, entity type, status, dates, city | as above, 9 tables | `HUNT_SOCRATA_TOKEN` | Officers' home towns are published by the states; Hunt shows the town, not the street |
| **FMCSA census** (`fmcsa`) | first + last name → carriers registered under that name (owner-operators) or listing it as a company officer: USDOT number, active or inactive, interstate or intrastate, trucks, drivers and CDL drivers, address, phone, email on file, last MCS-150 update | as above, 1 table, updated daily | `HUNT_SOCRATA_TOKEN` | Federal public data. SAFER snapshot is the record page |

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
| OpenCorporates | Every API call needs a key, and free keys go only to public-benefit "Permitted Users"; commercial use is paid |
| FMCSA QCMobile API | Needs a Login.gov web key. The keyless census on data.transportation.gov already gives the identity fields and officers; QCMobile would add only inspections and crashes |
| California DCA / CSLB | No API. DCA's monthly licensee files sit on Box, whose `robots.txt` disallows /; CSLB's free files come from a form postback with no stable URL. See [State records](#state-records-business-entities-and-licences) |
| FAA airmen registry | A monthly ZIP of CSVs (`registry.faa.gov/database/CS<MMYYYY>.zip`). The server answered Hunt's scripted HEAD with a 503, so Hunt doesn't fetch it; getting around that would be bot-check circumvention. Size not measured. **Decision for Aaron:** an investigator can download it by hand and Hunt could import the file |

### Adding a state

Most states publish licence or business tables on Socrata portals. To add one:
1. Find candidates with the discovery API: `https://api.us.socrata.com/api/catalog/v1?q=license&only=dataset`.
2. Read the columns (metadata only, no rows) at `https://<domain>/api/views/<id>.json`.
3. Add a `Dataset` to `licences.py` or `businesses.py`: which column(s) hold the name and what role it plays, a record mapping, and the column that identifies a record.

The search, filtering, proxy, health probe and note come with it. Tables already checked and ready to add:
- NY registered tax preparers (`data.ny.gov` `b7jj-bh4g`)
- IL asbestos workers (`illinois-edp.data.socrata.com` `437c-unzu`)
- NY elevator, crane, pyrotechnician, asbestos and mold individual licences (`cxfs-ya8e`, `bu6a-ty84`, `83wd-skw3`, `95bk-87hc`, `h6jr-vxqt`)
- TX Racing Commission and easement-agent licensees (`data.texas.gov` `yqzs-yaft`, `3p42-m5cn`)

An ArcGIS FeatureServer layer takes the same `Dataset` with `engine="arcgis"` and its service path as `id` (DC's business licences), and a Carto table `engine="carto"` (Philadelphia property); the where-clause is the same SQL. `order` (Socrata `$order`) puts the newest year first in a table that holds several.

A state that publishes files instead (no API) is a `_bulk.Table`: its file URLs (or a function reading the agency's index page) and a parser from one file to records and their people; add it to `licences.TABLES` or `businesses.TABLES`. `florida.py` and `statefiles.py` are the examples; `python -m hunt.sources.records update <table>` loads it.

### Source health

`hunt.sources.health()` returns one row per source, in registry order, for the startup screen:
- `source`, `kinds`
- `reachable`: True, False, or None when there is nothing to probe (Maigret, user-scanner and phonenumbers run offline or check their own sites)
- `detail`: "ok", "rate-limited right now", "refused (403)", "not found (404)", "server error 5xx" or "unreachable (…)"
- `checks`: one per probed URL, with status and milliseconds
- `key`: the env var name; `key_set`, `key_required`
- `key_status`: "none needed", "set", "not set (required)", "not set (free key available)" or "not set (optional)"
- `key_url` (where to get the free key) and `key_free` (what it unlocks): the same facts as the Free keys table below
- `ready`: reachable, or nothing to reach, and no required key missing

Each probe is a HEAD through `HUNT_PROXY` (a GET when HEAD isn't served), with an 8-second timeout, to a URL that spends no quota: GitHub's `/rate_limit`, FEC's docs page, each Socrata table's metadata. A row never contains a key's value. Live on 2026-10-29: 18 of 19 ready; CourtListener wasn't, because it had no token. Maintenance pass later the same day, with keys set for CourtListener, Socrata and GitHub: 21 of 21 ready (see the maintenance log).

## State records (business entities and licences)

_Checked 2026-11-01, every state and DC. Method: the Socrata discovery API for business, licence, credential, notary, agent and trade-name tables with a person-name column (catalogue metadata and three rows with the values masked); each Secretary of State's and main licensing agency's own pages for an API or a bulk file; `robots.txt` of every search and download host, read with Hunt's User-Agent; one GET of each search page, empty; HEAD for file sizes. Nothing went past a CAPTCHA, a login, a bot wall or a disallow, and no person's name was searched. Facts that came only from a search-engine copy of an official page are marked "(snippet)"._

**The finding.** No state publishes its business registry or its licensing boards as an open API outside the Socrata states Hunt already searched. The registries sell their bulk data ($40 a file in Wisconsin to $12,000 a year in South Carolina and West Virginia) and put their free search forms behind CAPTCHAs or bot walls (Cloudflare, Incapsula, Akamai, DataDome, F5, Radware) more often than not. A few agencies post free files that their `robots.txt` and terms allow a script to fetch: Florida DBPR, Virginia DPOR, Minnesota DLI, Nevada's Real Estate Division and the West Virginia Board of Medicine. Hunt loads those into local tables. Florida's Sunbiz files are free too, but only behind a login whose shared password the Division publishes: Hunt doesn't enter it, and imports the files the investigator downloads.

**Built** means `businesses` or `licences` searches it. **By hand** means an official search page the investigator opens herself under its own terms (Hunt never requests it). **Excluded** means there is no free page she may use for paid work. Inside a cell, "excluded:" marks a paid, login-only or terms-barred product beside the free route. A cell's status is its main channel.

| State | Business entities | Licences |
|---|---|---|
| AL | **By hand**: [SOS entity search](https://arc-sos.state.al.us/CGI/CORPNAME.MBR/INPUT) (officers and agents: `CORPAGENT.MBR`). Its host's `robots.txt` is Disallow: /. No bulk product | **By hand**: no umbrella agency. [Medical board](https://dashboard.albme.gov/Verification/search.aspx) (its free roster comes from a form post, not a file); [contractors board](https://licensesearch.alabama.gov/genconbd) (a free roster CSV, but it lists companies, not people: not built); real estate lists $10 |
| AK | **By hand**: [CBPL entity search](https://www.commerce.alaska.gov/cbp/main/search/entities). CBPL's own pages offer free corporation and officials CSVs, but a DataDome bot wall answers scripts with 403 everywhere on the host. Worth asking CBPL for an allowlisted channel | **By hand**: [CBPL professional search](https://www.commerce.alaska.gov/cbp/main/search/professional); its free licence download sits behind the same wall |
| AZ | **By hand**: [Arizona Business Center](https://arizonabusinesscenter.azcc.gov/EntitySearch/Index) (`robots.txt` Disallow: /). Excluded: the database extract, $1,000 with a commercial-purpose declaration | **By hand**: no umbrella. [Real estate](http://services.azre.gov/PdbWeb/); contractors (ROC), medical and nursing boards answer scripts with a Cloudflare 403 |
| AR | **By hand**: [SOS corporation search](https://www.ark.org/corp-search/) (AWS WAF CAPTCHA). Excluded: bulk data, a $150-a-year subscriber account | **By hand**: [Medical Board directory](https://armedicalboard.adh.arkansas.gov/public/directory/AdvancedDirectorySearch.aspx). Excluded: mailing lists ($100 to $250) |
| CA | **By hand**: [bizfile Online](https://bizfileonline.sos.ca.gov/search/business) (Incapsula; [terms](https://www.sos.ca.gov/business-programs/bizfile/privacy-warning-terms-and-conditions-use) ban any "robot" or "spider"). Excluded: bulk orders and the keyed developer API | **By hand**: [DCA search](https://search.dca.ca.gov/) (Turnstile) and [CSLB check a licence](https://www.cslb.ca.gov/OnlineServices/CheckLicenseII/CheckLicense.aspx). DCA's monthly licensee files sit on Box, whose `robots.txt` disallows /; CSLB's free licence and personnel files come from a form postback with no stable URL |
| CO | **Built**: SOS business entities (registered agents) and trade names (Socrata). The SOS search pages are disallowed to robots | **Built**: DORA, every profession, and DORA real estate (Socrata). The lookup has an AWS WAF CAPTCHA |
| CT | **Built**: SOTS principals and registered agents, joined to the business master (Socrata). [Business search](https://service.ct.gov/business/s/onlinebusinesssearch) | **Built**: DCP state licences and credentials, every credential (Socrata). The eLicense lookup has reCAPTCHA |
| DE | **Built**: One Stop trade names (filers and affiants; Socrata). By hand: [Division of Corporations name search](https://icis.corp.delaware.gov/ecorp/entitysearch/namesearch.aspx) (CAPTCHA; "strictly prohibits mining data"; registered agent only, directors only on purchased reports) | **Built**: Division of Professional Regulation, every profession, and notaries (Socrata) |
| DC | **Built**: DLCP basic business licences, with business owners and registered agents (ArcGIS FeatureServer, CC BY 4.0). Excluded: the corporate registry ([BOSS](https://boss.dc.gov/), `robots.txt` Disallow: /; an Access DC login, third-party report) | **By hand**: [DC Health licence verification](https://dohenterprise.my.site.com/ver/s/). Excluded: DLCP's occupational licence portal (Access DC login) |
| FL | **Built**: Sunbiz quarterly corporate file (officers and registered agents who are people) and fictitious-name file (owners), imported from the investigator's own download. By hand: [Sunbiz search](https://dos.fl.gov/sunbiz/search/) (its search host answers scripts with a Cloudflare challenge) | **Built**: DBPR, all 19 licensee files (every profession DBPR licenses). By hand: [Department of Health license verification](https://mqa-internet.doh.state.fl.us/MQASearchServices/HealthCareProviders) (doctors, nurses; its data portal needs a sign-in) |
| GA | **By hand**: [eCorp search](https://ecorp.sos.ga.gov/BusinessSearch) (Cloudflare). Excluded: bulk data, $1,000 or $500 a month under agreement | **By hand**: [Professional Licensing verification](https://verify.sos.ga.gov/verification/Search.aspx) (Cloudflare), [Medical Board](https://gateway.medicalboard.georgia.gov/verification/search.aspx) (reCAPTCHA). Rosters are paid (snippet) |
| HI | **By hand**: [business search](https://hbe.dcca.hawaii.gov/search-and-buy) (`robots.txt` Disallow: /; eHawaii's terms ban automated access). Excluded: Entity List Builder, $0.05 a record (snippet) | **By hand**: [PVL licence search](https://mypvl.dcca.hawaii.gov/public-license-search/) (Cloudflare 403). Excluded: PVL List Builder (snippet) |
| ID | **By hand**: [SOSBiz search](https://sosbiz.idaho.gov/search/business). No bulk entity file or API | **By hand**: [DOPL online services](https://edopl.idaho.gov/onlineservices/) (`robots.txt` Disallow: /; lists by paid records request) |
| IL | **By hand**: [business entity search](https://apps.ilsos.gov/businessentitysearch/) (Akamai 403). Excluded: corporation and LLC files, $1,500 each, no resale | **Built**: IDFPR, every profession (Socrata) |
| IN | **By hand**: [INBiz search](https://inbiz.in.gov/business-search) (reCAPTCHA). Excluded: bulk data, $8,000 | **By hand**: [PLA eVerification](https://mylicense.in.gov/everification/). Excluded: licence files, $150 plus $10 per 1,000 records |
| IA | **By hand**: [business search](https://sos.iowa.gov/search/business) (Cloudflare). Not yet: data.iowa.gov's free "Active Iowa Business Entities" (registered agents only, CC BY 4.0) has no stable file URL behind its download button. Excluded: officers through the paid SOS API ($2,400 a year) | **By hand**: [DIAL licence search](https://ia-plb.my.site.com/LicenseSearchPage). The nursing rosters' host disallows / |
| KS | **By hand**: [business entity search](https://www.sos.ks.gov/eforms/BusinessEntity/Search.aspx) (disallowed to robots). Excluded: data lists, $150 under a K.S.A. 45-230 certification | **By hand**: [Board of Nursing verification](https://portal.egov.ksbn.ks.gov/verification/) (reCAPTCHA). Healing Arts and Real Estate answer scripts with an Akamai 403 |
| KY | **By hand**: [business search](https://sosbes.sos.ky.gov/BusSearchNProfile/search.aspx). Excluded: Bulk Data Service, $2,000 a month for commercial use; the free tier is non-commercial and needs a login | **By hand**: [Department of Professional Licensing](https://oop.ky.gov/lic_search.aspx). Excluded: the nursing roster, $500 |
| LA | **By hand**: [commercial search](https://coraweb.sos.la.gov/commercialsearch/commercialsearch.aspx) (reCAPTCHA; disallowed to robots). Excluded: the Commercial API, a yearly fee | **By hand**: [medical](https://online.lasbme.org/#/verifylicense) and [nursing](https://www.lsbn.state.la.us/license-lookup/) boards (reCAPTCHA), [contractors](https://arlspublic.lslbc.louisiana.gov/Public/Search), [real estate](https://portal.lrec.gov/Public/Search). Excluded: the nursing CSV, $0.02 a name |
| ME | **By hand**: [corporate search](https://apps3.web.maine.gov/nei-sos-icrs/ICRS?MainPage=x) (reCAPTCHA; "strictly prohibits mining data"). Excluded: monthly data, $600 (snippet) | **By hand**: [ALMS licence search](https://www.pfr.maine.gov/ALMSOnline/ALMSQuery/SearchIndividual.aspx) (results and exports disallowed to robots) |
| MD | **By hand**: [Business Express](https://egov.maryland.gov/BusinessExpress/EntitySearch) (Turnstile). Excluded: the corporate master file | **By hand**: [Labor licence search](https://www.dllr.state.md.us/cgi-bin/ElectronicLicensing/OP_Search/OP_search.cgi?calling_app=ALL::ALL_personal_name) (reCAPTCHA). opendata.maryland.gov has only FY2018 veterinary lists |
| MA | **By hand**: [corporations search](https://corp.sec.state.ma.us/corpweb/CorpSearch/CorpSearch.aspx) (Incapsula). Excluded: the weekly extract, $4,800 a year (unverified) | **By hand**: [Check a Health License](https://checkahealthlicense.mass.gov/) (its free board exports load through undocumented endpoints: not built until the Bureau says automated use is fine), [Occupational Licensure](https://occupationallicensingandpermitting.mass.gov/madol/s/) |
| MI | **By hand**: [MiBusiness Registry](https://mibusinessregistry.lara.state.mi.us/) (Cloudflare). No bulk product | **By hand**: [verify a licence](https://www.michigan.gov/verifylicense) (Akamai 403; FOIA lists) |
| MN | **By hand**: [business search](https://mblsportal.sos.mn.gov/Business/Search) (Radware bot check). Excluded: bulk data, $710 under a licence agreement; free only for certified non-commercial use | **Built**: DLI construction licences, registrations and certificates (nightly file). By hand: the health boards on mn.gov (Radware) |
| MS | **By hand**: [business search](https://corp.sos.ms.gov/corpreporting/) (Cloudflare 403) | **By hand**: [medical](https://gateway.msbml.ms.gov/verification/search.aspx) and [nursing](https://gateway.licensure.msbn.ms.gov/Verification/search.aspx) boards (reCAPTCHA), [contractors](http://search.msboc.us/ConsolidatedSearch.cfm). Excluded: the medical roster, $300, no resale |
| MO | **By hand**: [business entity search](https://bsd.sos.mo.gov/BusinessEntity/BESearch.aspx). No bulk product | **By hand**: [MOPRO licence search](https://mopro.mo.gov/license/s/license-search). Its free nightly listings sit behind a JavaScript form with reCAPTCHA v3; data.mo.gov carries alcohol licences only |
| MT | **By hand**: [business search](https://biz.sosmt.gov/search) (Cloudflare challenge). Excluded: bulk data, 2¢ a record (unverified) | **By hand**: [public portal](https://ebizws.mt.gov/PUBLICPORTAL/) (F5 rejects scripts). Excluded: licensee lists, for a fee |
| NE | **Excluded**: [corporate search](https://www.nebraska.gov/sos/corp/corpsearch.cgi) and batch records ($15 per 1,000): Nebraska.gov's [terms](https://www.nebraska.gov/policies/) allow "personal and non-commercial use" only and ban bots | **Excluded**: [licence search](https://www.nebraska.gov/LISSearch/search.cgi) and the sold lists: the same terms |
| NV | **By hand**: [SilverFlume/ORION](https://orion.nv.gov/portal/public/) (Incapsula). Excluded: bulk download, an account | **Built**: Real Estate Division active licensees, nine lists (monthly). By hand: [contractors board](https://www.nvcontractorsboard.com/). Excluded: medical board lists, $75 |
| NH | **By hand**: [QuickStart](https://quickstart.sos.nh.gov/online/BusinessInquire) (Akamai 403) | **By hand**: [OPLC licence lookup](https://www.oplc.nh.gov/license-lookup) (Akamai 403) |
| NJ | **By hand**: [business name search](https://www.njportal.com/DOR/BusinessNameSearch/Search/BusinessName) (names only). Excluded: status reports and bulk access, $0.0185 a record | **By hand**: [Consumer Affairs verification](https://newjersey.mylicense.com/verification/Search.aspx). DCA's free "standard files" ([Box folder](https://app.box.com/v/DCAStandardFiles)) open only through Box's JavaScript app; Hunt could import them once downloaded by hand |
| NM | **By hand**: [business search](https://enterprise.sos.nm.gov/search/business) (Turnstile) | **By hand**: [RLD licence search](https://nmrldlpi.my.site.com/bcd/s/public-search-license-division) |
| NY | **Built**: active corporations (chief executive, registered agent, process name; Socrata) | **Built**: DOS real estate, barbers and cosmetology, home inspectors, appraisers and notaries; OCA attorney registrations; NYC Buildings trades (Socrata). Excluded: [NYSED Office of the Professions](https://eservices.nysed.gov/professions/verification-search) (doctors, nurses, CPAs…): its [terms](https://www.nysed.gov/terms-of-use) forbid "any commercial use" without written permission |
| NC | **By hand**: [business registration search](https://www.sosnc.gov/online_services/search/by_title/_Business_Registration) (Cloudflare; "automated or scripted searches… are not permitted", snippet). Excluded: data subscription, $750 plus $2,000 a year | **By hand**: [Medical Board](https://portal.ncmedboard.org/verification/search.aspx) (scraping "could result in… access being blocked"), nursing and contractors portals |
| ND | **By hand**: [FirstStop search](https://firststop.sos.nd.gov/search/business). Excluded: data lists, ND Login and $40 a type | **By hand**: FirstStop's contractor search; boards' lookups. Excluded: the nursing list ($65, snippet) |
| OH | **By hand**: [business search](https://businesssearch.ohiosos.gov/). The free monthly business reports sit behind the same JavaScript security check (403 to scripts) | **By hand**: [eLicense verification](https://elicense.ohio.gov/oh_verifylicense); Commerce's free rosters are generated by a form postback, with no file URL |
| OK | **By hand**: [corporation search](https://www.sos.ok.gov/corp/corpInquiryFind.aspx) (`robots.txt` Disallow: /; Turnstile) | **By hand**: board lookups (the medical board's host refuses scripts). Excluded: nursing list, $40 |
| OR | **Built**: active businesses, every associated name and role (Socrata) | **Built**: CCB contractors, Building Codes Division trades, notaries (Socrata). By hand: [Medical Board](https://omb.oregon.gov/search), [Board of Nursing](https://osbn.boardsofnursing.org/licenselookup) (Turnstile); excluded: their lists ($75; opt-in only) |
| PA | **Built**: registered businesses' parties, with county (Socrata). By hand: [business search](https://file.dos.pa.gov/search/business) (answers scripts with status 999) | **By hand**: [PALS verify a licence](https://www.pals.pa.gov/#!/page/search) (reCAPTCHA v3). Excluded: licensee lists, $71 setup plus $0.005 a name ([list requests](https://www.pa.gov/agencies/dos/programs/professional-licensing/list-requests)); data.pa.gov has counts per county only |
| RI | **By hand**: [corporate search](https://business.sos.ri.gov/CorpWeb/CorpSearch/CorpSearch.aspx) (Turnstile). Excluded: database, $250 or $3,000 a year | **By hand**: RIDOH licence verification; its free daily licensee lists answer scripts with a Cloudflare challenge |
| SC | **By hand**: [business entity search](https://businessfilings.sc.gov/BusinessFiling/Entity/Search) (reCAPTCHA). Excluded: bulk data, $12,000 a year | **By hand**: [LLR licence lookup](https://verify.llronline.com/LicLookup/LookupMain.aspx). Excluded: board lists (a Family Privacy Protection Act certification; $10 each) |
| SD | **By hand**: [filing search](https://sosenterprise.sd.gov/BusinessServices/Business/FilingSearch.aspx) (reCAPTCHA). Excluded: database, $1,500 plus updates | **By hand**: Labor and Regulation [real estate](https://dlr.sd.gov/realestate/license_verification_system.aspx) and [boards](https://dlr.sd.gov/btp/licensed_registry.aspx) registries |
| TN | **By hand**: [TNCaB entity search](https://tncab.tnsos.gov/business-entity-search) (reCAPTCHA and Turnstile scripts) | **By hand**: [Commerce search](https://search.cloud.commerce.tn.gov/), [Health licensure](https://apps.health.tn.gov/Licensure/default.aspx) (`robots.txt` Disallow: /) |
| TX | **By hand**: [Comptroller franchise-tax account status](https://comptroller.texas.gov/taxes/franchise/account-status/search) (free: officers and registered agent from the Public Information Report). Excluded: SOSDirect ($1 a search, an account), SOS bulk ($1,350), the Comptroller Public Data API (a key after registration) | **Built**: TDLR trades, TREC real estate and inspectors, Medical Board, TDI insurance agents and adjusters, SOS notaries (Socrata) |
| UT | **By hand**: [entity search](https://businessregistration.utah.gov/EntitySearch/OnlineEntitySearch) (Cloudflare). Excluded: the List Service (officers included), $0.01 to $0.05 a record | **By hand**: [DOPL licence lookup](https://secure.utah.gov/llv/search/index.html) (reCAPTCHA v3). Excluded: the List Service |
| VT | **By hand**: [business search](https://bizfilings.vermont.gov/online/BusinessInquire/). The SOS says its weekly bulk data is free (legislative memo, 2025-01-13), but the download's URL and access rules aren't confirmed: a candidate | **Built**: Division of Fire Safety trades (Socrata). By hand: OPR's [Find a Professional](https://sos.vermont.gov/opr/find-a-professional) (its roster download is an interactive session) |
| VA | **By hand**: [SCC entity search](https://cis.scc.virginia.gov/EntitySearch/Index) (`robots.txt` Disallow: /). Excluded: the weekly extract, $1,000 a month | **Built**: DPOR regulant lists, every profession DPOR regulates (weekly). Excluded: [DHP lookup](https://dhp.virginiainteractive.org/Lookup/Index) (health professions): "Not For Commercial Use!" |
| WA | **By hand**: [CCFS business search](https://ccfs.sos.wa.gov/#/BusinessSearch). The free corporations extract was discontinued (2024) | **Built**: L&I contractors and principals, DOH health professions (with birth year), Board of Accountancy CPAs (Socrata) |
| WV | **By hand**: [business organizations search](https://apps.sos.wv.gov/business/corporations/). Excluded: database, $12,000 plus $1,750 a month | **Built**: Board of Medicine rosters (physicians, PAs, podiatrists, genetic counsellors, radiologist assistants; weekly). By hand: the contractors board (`robots.txt` Disallow: /) |
| WI | **By hand**: [corporate search](https://apps.dfi.wi.gov/apps/corpsearch/search.aspx) (Cloudflare 403). Excluded: database files, $40 each, no officers | **By hand**: [DSPS credential search](https://online.drl.wi.gov/LicenseLookup/IndividualCredentialSearch.aspx) (Cloudflare 403). Excluded: lists, up to $2,000 (snippet) |
| WY | **By hand**: [WyoBiz filing search](https://wyobiz.wyo.gov/Business/FilingSearch.aspx) (F5 challenge with a CAPTCHA). Excluded: database download, $10,200 a year, no sharing | **By hand**: [Board of Medicine lookup](https://my.wyomedboard.wyo.gov/licensee_lookup_and_verification_empty_layout) (reCAPTCHA; lists on request) |

**Totals** (51 jurisdictions, two cells each): business entities 8 built, 42 by hand, 1 excluded; licences 14 built, 36 by hand, 1 excluded. Together **22 built, 78 by hand, 2 excluded**. Built covers 22 states and DC in at least one cell.

### Bulk files on this Mac

`python -m hunt.sources.records` lists what is loaded; `update [table…]` downloads and indexes (one file at a time, Hunt's User-Agent, skipped when every file's Last-Modified is unchanged, stopped by a 429 or a refusal, a 404'd list skipped and named); `load <table> <file>…` indexes files the investigator downloaded. A search reads the local table only; a table that isn't loaded is named in the note with the command. Each is a SQLite full-text index under `HUNT_HOME/data`, so the name's word order in the record doesn't matter.

| Table | Agency and files | Download | On disk | Refreshed upstream |
|---|---|---|---|---|
| `fl-dbpr` | Florida DBPR: 19 licensee files ("provides copies of electronic records to the public through free download") | about 270 MB | not measured (several times the download) | weekly |
| `fl-sunbiz-cor`, `fl-sunbiz-fic` | Sunbiz `cordata.zip` and `ficdata.zip`, which the investigator downloads from [quarterly data](https://dos.fl.gov/sunbiz/other-services/data-downloads/quarterly-data/) with the published public login | by hand; very large (not measured: Hunt can't reach the files) | not measured | quarterly |
| `va-dpor` | Virginia DPOR: the 122 regulant lists that can name a person, read from its [index](https://www.dpor.virginia.gov/RegulantLists) | about 30 MB | 112 MB (175,166 licensees, 2026-11-01) | every five business days |
| `mn-dli` | Minnesota DLI export (one zip) | 11 MB | 145 MB (221,390) | nightly |
| `nv-red` | Nevada Real Estate Division: nine active-licensee spreadsheets | 3.2 MB | 22 MB (32,556) | monthly |
| `wv-bom` | West Virginia Board of Medicine: five rosters | 6.5 MB | 27 MB (33,953) | weekly |

**Fields** are the shape the other records use: `fullname` (as the record writes it), `roles`, `licence`, `licence_number`, `status`, `issued`, `expires`, `business`, `address` (the street, as published: a home, office or mailing address), `location` ("City, ST"), `email` or `phone` where the agency publishes them, and `verify` (the agency's own search page). Sunbiz adds `business`, `entity_type`, `formed`, `last_filing`, `business_location`, `business_address` and `document_number`; the DBPR real-estate file adds `sponsor` (the broker). A record's URL is the agency's file (or Sunbiz's document-number search) with the licence or document number after `#`: no state gives these records a page of their own, and the raw row is in the evidence locker.

### Considered and rejected (state records)

| Candidate | Why not |
|---|---|
| Logging in to Sunbiz's SFTP with its published password | A login, however public; the investigator downloads, Hunt imports |
| Any registry's internal JSON behind its search page (Washington CCFS, North Dakota FirstStop, the Massachusetts health-licence exports) | Undocumented and not offered as an API; the page is for a person at a browser |
| Paid bulk and list products in every state above | Not free; most also bind the buyer to a licence agreement or a no-resale clause |
| Florida Department of Health data portal | Needs a sign-in |
| Alabama contractors board roster | Free and allowed, but it lists companies, not people |
| Iowa "Active Iowa Business Entities" | Free, but registered agents only, and its file has no stable URL yet; worth adding once it does |
| Maryland's FY2018 veterinary tables, Missouri's alcohol licences, data.pa.gov's licensee counts | Stale, businesses only, or counts without names |

## Property

_Checked 2026-11-02. Method: the Socrata catalogue for parcel, assessment, tax-roll and CAMA tables with an owner-name column (metadata, then one row per table with values masked); the counties' and states' own open-data and download pages; one GET of each by-hand search page. No person's name was searched._

`parcels` (name seeds) answers "what does this person own, and where": the owner as the roll writes it (`fullname`), `roles` (owner, co-owner, taxpayer), the parcel's `address` and `location`, the owner's `mailing_address` (where the tax bill goes, often the home of an owner who lets the parcel), `homestead` where the roll records the exemption (the owner lives there), `value`, `sale_date`/`sale_price` or `owned_since`, `parcel`, `county`, `year`. An owner whose mailing address is the parcel, or with a homestead exemption, is the strongest residence record Hunt has.

| Jurisdiction | Channel | Status |
|---|---|---|
| Florida, all 67 counties | Department of Revenue's statewide NAL roll ([data portal](https://floridarevenue.com/property/Pages/DataPortal_RequestAssessmentRollGISData.aspx); each county's newest final roll, else its preliminary one; 794 MB for the 60 final counties of 2026). The public files leave out owners exempt under s. 119.071 | **Built**, a local table: `python -m hunt.sources.records update fl-property` (`HUNT_FL_COUNTIES="Hillsborough, Miami-Dade"` loads fewer). The live record is the county appraiser's: [Hillsborough](https://gis.hcpafl.org/propertysearch/), [Miami-Dade](https://www.miamidade.gov/Apps/PA/propertysearch/), [Orange](https://ocpaweb.ocpafl.org/parcelsearch), [Pinellas](https://www.pcpao.gov/) (refuses scripts), [Duval](https://paopropertysearch.coj.net/Basic/Search.aspx), [Broward](https://web.bcpa.net/BcpaClient/), [Palm Beach](https://pbcpao.gov/index.htm) |
| Philadelphia | OPA properties (Carto SQL API): owners 1 and 2, mailing address, homestead, value, last sale | **Built** (live) |
| Allegheny County PA | WPRDC's property assessments (585K parcels) carry an owner *type*, not a name | **By hand**: [Real Estate Portal](https://realestate.alleghenycounty.us/) |
| Connecticut, every town | 2026 Parcel and CAMA data (Socrata) | **Built** (live) |
| New York State outside NYC | Local assessment rolls, 2021 to 2025, up to four owners (Socrata; newest roll first) | **Built** (live) |
| New York City | DOF property valuation and assessment (Socrata; "LAST, FIRST", searched by prefix) | **Built** (live) |
| Cook County IL | Assessor parcel addresses: owner and taxpayer names, 2021 to 2026 (Socrata; a slow full scan, 60 s allowed) | **Built** (live) |
| Harris County TX | HCAD public data download (owners joined to accounts; "can be imported into user databases") | **Built**, a local table: `… update tx-harris` (210 MB). The live record: [HCAD search](https://search.hcad.org/) (refuses scripts) |
| Denver, Providence, Baton Rouge, Norfolk VA, Prince George's County MD, Cambridge MA, Williamson County TX | Each assessor's own Socrata table | **Built** (live) |
| Los Angeles, Maricopa, Dallas, King WA, Clark NV, Tarrant, Bexar | Not yet checked for an owner-name file | **By hand**: [LA assessor portal](https://portal.assessor.lacounty.gov/), [Maricopa](https://mcassessor.maricopa.gov/), [DCAD](https://www.dallascad.org/), [King](https://blue.kingcounty.com/Assessor/eRealProperty/), [Clark](https://www.clarkcountynv.gov/government/assessor/), [TAD](https://www.tad.org/), [BCAD](https://www.bcad.org/). The Texas appraisal districts publish data downloads like HCAD's: the next candidates |

**Not surfaced by default:** as for officers, show the town and the parcel; the street is one click away (the report decides).

## UCC filings and discipline

_Checked 2026-11-02 (Socrata catalogue; the OIG's download page). No person's name was searched._

| Source | Tables | Record carries |
|---|---|---|
| `ucc` | Colorado UCC debtors (`8upq-58vz`) and farm-products financing statements (`ej2c-jkvh`); Connecticut UCC and lien filings (`xfev-8smz`), the person as debtor or as secured party | `roles` (debtor, additional debtor, secured party), `filing`, `lien`, `filing_type`, `status`, `filed`, `lapses`, the other party (`secured_party` or `debtor`), `collateral`, `address`, `location` |
| `discipline` | HHS-OIG List of Excluded Individuals/Entities (a local table: `… update us-leie`, 11 MB, monthly; individuals only, with **date of birth**); NY Board for Professional Medical Conduct (`ebmi-8ctw`, with year of birth); Delaware DPR (`dz6p-akeq`); Connecticut DCP and real-estate decisions (`2twc-xaxs`, `9ky9-v9uu`); NYC Buildings licensees (`ndq3-kuef`) and process servers (`b9yk-4pzk`) | `action`, `effective` (and `until`, `reinstated`), `licence`, `licence_number`, `case`, `decided`, `document` (the decision), `dob` or `year_of_birth`, `npi`; one record per action |

Not built: Connecticut DPH hearing decisions (`262e-rymj`, empty on 2026-11-02); SAM.gov exclusions (an API key); every other state's UCC search (by-hand forms or paid bulk, as for the business registries above) and board actions (PDF lists or lookups). Florida's federal tax liens are in Sunbiz's quarterly files (`flr`), behind the same shared login as its corporate data: a candidate for the investigator's own download.

## Court records

_Checked 2026-10-29. Method: the Socrata discovery API for court, docket, litigation, judgment, warrant and hearing tables with a party-name column (catalogue metadata only, then three sample rows of each candidate); ArcGIS Hub's dataset search; each portal's `robots.txt`, then one GET of its search page with Hunt's User-Agent where robots allowed it; the terms pages that answer to a script. "WAF 403" means the portal refused Hunt's honest request outright. Nothing here was fetched past a 403, a CAPTCHA or a robots.txt disallow._

**The finding:** no state publishes its trial-court docket as an open API. Every statewide and county case-search portal is a web form for a person at a browser: Tyler Odyssey and re:Search portals (TX, NC, GA, MI, IN, NM, KS, OR, RI, ID, ND…) license use "for internal use" after registration and forbid bulk copying; New York, Maryland, California, Florida and Texas answer scripts with a 403 or a CAPTCHA; Oklahoma, Missouri, South Carolina, Alaska and Texas's appellate search disallow all robots. What courts and cities do publish as open data are specific tables: housing, administrative and claims courts, tax warrants, and civil suits involving a city. Hunt searches those and gives the investigator every portal's search page to open by hand.

### What Hunt searches (`courts`, plus `courtlistener`)

| Table | Jurisdiction and court | What a record carries | Rows | Terms |
|---|---|---|---|---|
| [HPD Housing Litigations](https://data.cityofnewyork.us/d/59kj-x8nc) `59kj-x8nc` | NYC Housing Court: cases HPD brings against building owners | respondent (owner), case type, opened, status, judgment, harassment finding, penalty, building address, borough | 242K | NYC Open Data (open by default under the Open Data Law; citywide [terms](https://www.nyc.gov/main/terms-of-use)) |
| [Civil litigation](https://data.cityofnewyork.us/d/pjgc-h7uv) `pjgc-h7uv` | NYC Law Department: suits by or against the City in state and federal courts | caption, court (e.g. "Supreme Court - Kings"), index number, started, closed, disposition, amounts | 547K | as above |
| [OATH Trials Division](https://data.cityofnewyork.us/d/y3hw-z6bm) `y3hw-z6bm` | NYC administrative law court: agency v. employee or licensee | caption, case number, type and category (e.g. Section 75 discipline), opened, trial, disposition | 3K | as above |
| [DOB ECB Violations](https://data.cityofnewyork.us/d/6bgk-3dad) `6bgk-3dad` | NYC OATH Hearings Division: Buildings summonses | respondent's name and address, issued, hearing date and result, severity, penalty, paid, balance | 1.8M | as above |
| [NYS Tax Warrants from 2025-07-01](https://data.ny.gov/d/v7ua-z23v) `v7ua-z23v` | NYS Tax Department warrants docketed with the Department of State and county clerks | up to four debtor names, address, county, amount, filed, satisfied, vacated, expires, the warrant PDF | 737K | NY Open Data |
| [Court of Claims case index](https://data.ohiocourtofclaims.gov/d/etc6-cwcf) `etc6-cwcf` | Ohio Court of Claims: claims against the state, public-records disputes | caption with role words ("X Plaintiff v. Y Defendant"), case number, type, filed, status, agencies, last event | 253K | the court's own Socrata portal; `robots.txt` asks for a 1 s crawl delay |
| [Ordinance Violations](https://data.cityofchicago.org/d/6br9-quuz) `6br9-quuz` | Chicago Department of Administrative Hearings | respondents (pipe-separated; "LLC C/O person"), docket, department, hearing date, disposition, fine, violation, property address | 825K | City of Chicago data [terms](https://www.chicago.gov/city/en/narr/foia/data_disclaimer.html) (the page 403s to scripts; reuse licence **unverified** today) |
| [Code Complaints, Violations & Permits](https://data.cityofgainesville.org/d/vu9p-a5f7) `vu9p-a5f7` | City of Gainesville, FL: code-enforcement cases heard by its special magistrate | owner named as primary party, property address, case type, infraction date, status, parcel | 42K | Gainesville open data (Socrata). Florida's only open-data case table that names a party (checked 2026-11-01) |
| [TCEQ Civil Judgments](https://data.texas.gov/d/7ift-kbgd) `7ift-kbgd` | Texas district courts: environmental judgments the Attorney General obtained for TCEQ | respondent, district-court docket number, county, order date, penalty, fees, costs | small, yearly | Texas Open Data |

**Fields for the matcher.** `address` is one postal line ("100 Example St, Brooklyn, NY 11201"), the form `match.place_text` geocodes whole; `location` is "City, ST"; `employer` is set where a case is an employer against its employee (OATH personnel trials: the agency); `roles` and `court` say what the person was to the case. No open court table carries a date of birth or age (`dob`, `age`), so those seed kinds can't be scored against court records; OSCN's by-hand form filters on date of birth, and the Texas Medical Board licence table (`licences`) is the one records table with a birth year.

Rejected on inspection: [OATH Hearings Division Case Status](https://data.cityofnewyork.us/d/jz4z-kudi) `jz4z-kudi` (24M summonses) **dropped the respondent's first name, street, city and state on 2026-05-04**; a last name alone can't tell people apart, so it isn't searched. OATH's [Summons Finder](https://a820-ecbticketfinder.nyc.gov/searchHome.action) is the by-hand route.

**CourtListener** (`courtlistener`, already wired for RECAP) now also runs the case-law search (`type=o`, `caseName:"<name>"`), which covers every state's appellate courts, so a state case that was appealed shows up even where the trial court's portal bars scripts. Fields confirmed from the v4 search docs: `caseName`, `court`, `court_id`, `dateFiled`, `docketNumber`, `citation`, `judge`, `attorney`, `status`, `absolute_url`. Parties are split from the caption; there is no party field on opinions. Two requests per name against the free account's 5/min, 50/hr, 125/day (the API docs now state these; the earlier "third-party report" is official). Not verified live: Hunt has no token.

**PACER Case Locator**: the [developer page](https://pacer.uscourts.gov/file-case/developer-resources) offers an Authentication API and a PCL API, both against a PACER account, and the [fee schedule](https://pacer.uscourts.gov/pacer-pricing-how-fees-work) bills a search "by the number of pages it generates… even if the search displays 'no matches found'" at $0.10 a page (waived under $30 a quarter). Not keyless, not free, and the developer page tells scrapers to run "between 6 p.m. and 6 a.m. Central Time": a by-hand link under the investigator's own account.

### Per state

Built = searched by Hunt (`courts.DATASETS`); by hand = `courts.search_links` gives the URL and the investigator opens it under the portal's own terms. Liveness is one GET on 2026-10-29 (a browser visit where the host refuses scripts); a portal that was unreachable or 404 that day isn't listed rather than guessed. 47 states and DC have at least one link; the Socrata catalogue has no court or hearing table with a party name for any state beyond NY, OH, IL and TX.

| State | Built | By hand (why not built) |
|---|---|---|
| CA | nothing published as open data | Appellate courts party search (form only; `robots.txt` allows generic crawlers but blocks named AI bots; WAF 403 to Hunt). LA Superior Court (civil name searches are paid, $1–4 a search, criminal $4.75; third-party reports). San Francisco (search page redirects to a CAPTCHA). San Diego (WAF 403). Orange, Santa Clara (403). Case law via CourtListener |
| TX | TCEQ civil judgments | re:SearchTX (registration with a card on file; licence "solely for… internal use", no bulk copying, no searchable third-party database; WAF 403). Appellate TAMES (`robots.txt` Disallow: /). Harris County District Clerk (`robots.txt` disallows every search page), Harris County Clerk, Harris justice courts, Dallas (Odyssey), Tarrant (Odyssey). Bexar's search host didn't answer a script; Travis has no stable public URL found |
| **FL** (checked county by county 2026-11-01) | Gainesville code-enforcement cases (`vu9p-a5f7`). Nothing else: no Florida clerk or county publishes case-level data as open data. The clerks' feeds are commercial: Miami-Dade's bulk files are $80 a folder a month after a notarised form; Broward's Commercial Data API needs a notarised agreement and a fee; St. Lucie sells monthly reports; Duval takes a "complex records request". Under the Supreme Court's Standards for Access to Electronic Court Records, the anonymous public gets the case-search web page, and bulk goes to "commercial purchasers" under agreement | Fifteen county portals, the case's own county first: Miami-Dade civil and criminal (the criminal system says "personal and public non-commercial (educational) use"; both 404 to scripts), Broward, Palm Beach, Hillsborough HOVER (refuses scripts; live in a browser), Orange, Pinellas, Duval, Lee (live in a browser), Polk Records Online (civil; criminal moved to the clerk's site), Volusia (disclaimer to accept), Manatee, Lake, Leon and Escambia (WAF 403 to scripts), plus the DCAs via ACIS. Not listed, because neither a script nor the built-in browser reached them on the day: Brevard, Seminole, Sarasota, Collier, Pasco, Osceola, Marion, St. Lucie (robots.txt disallow), Alachua (login page). Bay, Walton and Leon gate the search behind a personal-use disclaimer |
| NY | Housing Court (HPD), Law Department suits, OATH trials, DOB/ECB summonses, NYS tax warrants | WebCivil Supreme, eCourts WebCivil Local, WebCrims, NYSCEF by party name (every iapps.courts.state.ny.us page answers scripts with 403; WebCrims reportedly needs a CAPTCHA, **unverified**). OATH Summons Finder. NYS tax warrant search (older warrants than the 2025 table) |
| **PA** (checked 2026-11-01) | nothing: data.pa.gov, OpenDataPhilly and WPRDC have no case table with a party name. WPRDC's Allegheny County tax liens (2.2M, CC0) carry parcel, amount and assignee but no debtor; its mortgage foreclosures (41K) name the plaintiff lender, never the homeowner. Neither answers "is this person in a case" | UJS portal first for everyone: criminal, magisterial-district and appellate docket sheets statewide. It is a script-rendered form (no CAPTCHA seen; terms silent on automation; no robots.txt); the AOPC's channel for automated or recurring data is its Public Access Unit's fee-scheduled data files, and the Electronic Case Record Public Access Policy treats "bulk distribution requests" as requests to the court or office, with fees, so Hunt doesn't scrape the form. Common Pleas **civil** dockets are county-level: Philadelphia (FJD, disclaimer), Allegheny (Pittsburgh; name search needs a free registration behind a BotDetect CAPTCHA, a case-number lookup doesn't), Montgomery (registration), Bucks (robots.txt disallow). Lancaster, Chester, Delaware and York publish no civil search page a script or browser could find |
| IL | Chicago administrative hearings | Cook County Clerk of the Circuit Court (JavaScript application; "violation of the Terms of Use may result in revocation of access"; CAPTCHA reported, **unverified**). Judici for 70+ other counties (`robots.txt` Disallow: /; its policy allows "Automated Access" only where specifically provided). Cook County's open data has no party names |
| OH | Court of Claims | Franklin, Cuyahoga, Hamilton (`robots.txt` disallows /case-summary/ and /data/) clerks; Supreme Court of Ohio. No statewide portal |
| GA | nothing | PeachCourt (registration; participating counties). Fulton County clerk (its Odyssey portal didn't answer a script). Supreme Court docket, Court of Appeals. GSCCCA is a paid subscription |
| NC | nothing | eCourts Portal (Tyler; WAF 403; "violation of the terms of use may result in revocation of access") |
| MI | nothing | MiCOURT (SCAO: offered as a courtesy, no right or licence conferred; third-party report of the terms: no bulk download, no scraping, no VPN; some courts hide convictions sentenced more than 7 years ago). Wayne County Third Circuit. Appellate courts |
| OK | nothing | OSCN (`robots.txt` Disallow: /; the party form takes last and first name, so the link is prefilled). ODCR for the other counties: not listed |
| MD | nothing | Case Search (WAF 403; reCAPTCHA since 2022 by official notice) |
| WA | nothing | Washington Courts case search (dw.courts.wa.gov). JIS-Link data is a paid subscription |
| AZ | nothing | Public Access to Court Information; Maricopa docket |
| CO | nothing | Judicial Branch docket search (`robots.txt` disallows /dockets); CoCourts is paid |
| MA, VA, WI, MN, MO, IN, OR, NV, SC, KS, NM, DC, AK, ID, RI, ND, IA | nothing | One statewide or main-county portal each (WI's WCCA REST interface is paid; MO Case.net, SC public index and AK CourtView disallow robots; OR needs free registration; RI's portal answered 403) |
| AR, CT, DE, HI, NJ, TN | nothing (no open-data court tables on any of their portals, checked 2026-10-29) | Arkansas CourtConnect; Connecticut Superior Court party search (civil, family, housing, small claims; the host refuses scripts, confirmed live in a browser); Delaware CourtConnect; Hawaii eCourt Kokua (guest access); New Jersey Courts public records (civil case jackets by party, judgments, Tax Court); Tennessee appellate public case history plus Davidson County circuit and criminal clerks and Shelby County's criminal justice portal (no statewide trial-court search) |
| AL, KY, MS, SD, UT | nothing | The only online search is paid: Alacourt (per search), CourtNet 2.0 (`robots.txt` Disallow: /), Mississippi Electronic Courts, South Dakota PARS, Utah Xchange. Linked with "(paid)" in the label for an investigator who holds a subscription |
| LA, ME, MT, NE | nothing | Only a partial public search: Louisiana Supreme Court docket (parish clerks are subscription services), Maine eCourts information page (its Odyssey portal didn't answer a script), Montana Supreme Court docket, Nebraska JUSTICE court calendar by name (case search is paid) |
| NH, VT, WV, WY | **not yet** | NH's and VT's Odyssey portals didn't answer a script or the built-in browser on the day; WV's case search (Circuit Express) is paid and its public pages 404; WY has no public online case search |

### Considered and rejected (courts)

| Candidate | Why not |
|---|---|
| PACER Case Locator API | PACER login and $0.10 a page per search, including empty ones. By-hand link only |
| Tyler Odyssey and re:Search portals (TX, GA, NC, and most of the smaller states) | Registration, "internal use" licence, no bulk copying, WAF; the public form is the only interface |
| OATH Hearings Division Case Status (`jz4z-kudi`) | First name and address removed 2026-05-04 |
| NYS Child Support Warrants (`8pp4-isha`) | Family status: outside what Hunt reports (`legal.md`). Decision for Aaron if a lawful purpose ever needs it |
| King County jail bookings (`j56h-zgnm`), Montgomery County MD daily arrests (`xhwt-7h2h`) | Arrests and bookings aren't court outcomes; Hunt reports what a court decided |
| Judyrecords, UniCourt, Trellis, CourtTrax, Docketbird | Unofficial aggregators or paid; a record there can't be cited to its court |
| GSCCCA (GA), WCCA REST (WI), Xchange (UT), Alacourt (AL), JUSTICE (NE), CourtNet (KY), CoCourts (CO), JIS-Link (WA) | Paid |
| Harvard Caselaw Access Project, GovInfo USCOURTS opinions | Already inside CourtListener's case law |
| NOLA sheriff sales (`d52w-8nva`) | Last updated 2018 |
| King County Superior Court microfiche index (`vu5j-8bgd`) | An index of microfiche files, not of cases |
| ArcGIS Hub | Only Cape Town and Arlington TX "court cases" layers came up (locations, not parties); no US name-level court data. For FL and PA (2026-11-01): Orange County FL's "Clerk of Courts" and "Ninth Judicial Circuit" items are GIS locations |
| Florida DHSMV driver and vehicle records | Personal information is DPPA-protected; not a public-records source for Hunt, as the main session ruled |
| Florida clerks' bulk and commercial data (Miami-Dade bulk files, Broward Commercial Data API, St. Lucie monthly reports, Duval complex requests) and CCIS | Paid, under notarised agreements, or restricted to clerks and the judiciary |
| Florida and Pennsylvania corrections inmate locators | Custody records, not court outcomes; sensitive. By-hand only, outside Hunt |
| PA UJS portal as a scraped form; AOPC recurring data files | The form is for a person at a browser; automated and bulk access is the AOPC's fee-scheduled data channel |
| Allegheny County DCR civil docket, Montgomery County PSI | Name search needs a registered login (Allegheny's behind a BotDetect CAPTCHA); linked by hand with that said |
| WPRDC Allegheny tax liens (`allegheny-county-tax-liens-filed-and-satisfied`) and mortgage foreclosures | No debtor or defendant name: parcels, amounts, assignees and plaintiffs only |
| Orlando code-enforcement cases (`data.cityoforlando.net` `k6e8-nw6w`) | "casename" is the street location, not a party |

Ready to add with one `Dataset` line each, when a case needs them: Everett WA prosecutor hearing calendar (`data.everettwa.gov` `ppic-abeb`), NYC Open Article 7 tax-assessment petitions (`aht6-vxai`, nearly all LLCs), Chicago building-code scofflaw list (`crg5-4zyp`), Ohio Court of Claims public-records cases (`fxn9-cg25`, requester and respondent) and hearing calendar (`a5tk-vp2p`). Not courts but found on the way: NYS attorney registrations (`data.ny.gov` `eqw2-r5nb`) and Connecticut DPH, DCP and real-estate licence decisions (`262e-rymj`, `2twc-xaxs`, `9ky9-v9uu`) belong in `licences`; Colorado UCC debtors (`8upq-58vz`) in `businesses`.

### Adding a state (courts)

The three steps in [Adding a state](#adding-a-state) apply; two conventions on top:
- A table whose name column is a **case caption** ("A v. B", "A Plaintiff v. B Defendant") sets `caption` in its record mapping and an entry in `courts.SIDES` (the left and right roles). `courts.search` then keeps only the side that names the person as `fullname` and sets `roles` from the caption's own role word or the side.
- A portal that bars scripts goes in `courts.PORTALS[state]` as `(label, url)`, only after one GET (or a `robots.txt` disallow, which is a by-hand link but can't be checked) confirmed it is live. `{name}`, `{first}` and `{last}` in a URL or label are filled from the name seed. States without an entry are "not yet"; `states_in` reads state names and codes from location and address seeds.

## Maintenance log

- **2026-10-29**, with keys loaded from `~/Hunt/keys.env` (CourtListener, Socrata, GitHub):
  - `health()`: 21 of 21 sources ready, including other sessions' `courts` and `facebook`.
  - Logged-out live checks (`test_sources.py --live`: public organisations, `example.com`, a made-up name): all pass.
  - Parsed fields on real public-org hits (GitHub `nasa`, Bluesky `bsky.app`, Mastodon's own account, Wayback for `github.com/nasa`) are unchanged.
  - Keyed paths with a made-up name: GitHub search with a token; CourtListener RECAP and case-law captions; `licences`, `businesses` and `fmcsa` with a Socrata token. All answered.
  - The one Socrata token worked on all 11 portals: data.texas.gov, data.colorado.gov, data.delaware.gov, illinois-edp.data.socrata.com, data.wa.gov, data.oregon.gov, data.cityofnewyork.us, data.ny.gov, data.ct.gov, data.pa.gov, data.transportation.gov.
  - No endpoint or response shape had changed, so no code changes.
- **2026-11-01**: `voter` added (Florida's extract, indexed locally; no network). `test_voter.py` is offline; `test_sources.py` still passes with the new registry entry. Nothing to probe in `health()`: the row says "local files only".

## Activity records

_Checked 2026-10-29. A claimant who can't lift entering a powerlifting meet, or who can't walk far finishing a 10K, is in the published results. Method as for courts: each platform's API docs, `robots.txt`, terms page and one GET of its search page with Hunt's User-Agent; the Socrata catalogue for results tables (none with athlete names: only a Chicago Marathon course map)._

| Platform | What it has | Access and terms | Decision |
|---|---|---|---|
| **OpenPowerlifting** | Every sanctioned powerlifting meet it can find, worldwide, since the 1960s: 4,054,260 entries at 64,582 meets in the 2026-10-24 file; lifter, sex, age at the meet (exact, or "22.5" = 22 or 23), division, weight class, lifts, total, place, drug-tested flag, home state and country, meet town and federation | Public domain (its LICENSE.txt: "contributed to the public domain"; attribution optional). The data page: "There is no need to scrape our websites: you can download everything here"; the site's `robots.txt` disallows `/api/`. One zip, 170 MB (829 MB CSV), refreshed weekly | **Built**: `python -m hunt.sources.activity update` streams the zip into a 538 MB SQLite table under `HUNT_HOME/data` (40 s on a laptop); later runs HEAD the file and download only when its Last-Modified changed. A search reads the table only. OpenIPF (68 MB) is the IPF-only subset, not needed |
| RunSignup | Results and registrations for the races that use it | REST API under an Apache licence ("no more than 2 concurrent API calls"); `get-results` filters by first and last name **within one race** and lists api_key/api_secret under security; no cross-race name search; `robots.txt` disallows `/Race/FindARunner/` and `/Race/Results/Simple/` | By hand: Find a Runner, prefilled with the name |
| Athlinks (ChronoTrack) | The largest race-results index (Ironman, Spartan, most big-city marathons) | JavaScript application, no public API; `robots.txt` disallows `/search/athletes`; the terms page is a script shell | By hand: athlete search, prefilled |
| UltraSignup | Ultra and trail results by name (`results_participant.aspx?fname=&lname=`) | HTML only; `robots.txt` allows all; terms live on a Notion page that renders nothing to a script | By hand, prefilled |
| ITRA | Trail runners' performance index | JavaScript application (202 to scripts) | By hand |
| CrossFit Games | Open leaderboard, athlete pages | Terms forbid "data mining, robots, scraping or similar data gathering or extraction methods"; the leaderboard API behind the site is undocumented | By hand: the Open leaderboard |
| U.S. Masters Swimming | Individual meet results by name | WAF 403 to scripts | By hand |
| USA Cycling | Results, on Sport80 | JavaScript application | By hand |
| New York Road Runners | NYC Marathon and NYRR race results | JavaScript application | By hand |

Rejected: Strava (private by design; `robots.txt` disallows athlete search; API terms forbid this use), parkrun (403 to scripts; results are by athlete number, no name search; terms reportedly forbid scraping, **unverified** today), Ironman's own results page (404 today; its results are on Athlinks), Boston Athletic Association results search (404), MarathonGuide (per-race pages, no runner search), Smoothcomp, RaceRoster (event search only), USA Triathlon and bowl.com (result pages 404), World Triathlon (terms forbid automated collection).

**Fields for the matcher and the timeline.** One record per lifter: `fullname`, `sex`, `location` ("Arizona, USA"), `federations`, `meet_count`, `first_date`, `last_date`, `date` (the latest meet), `best_total_kg`, `age_class`, and `meets[]` with `date`, `meet`, `location`, `division`, `event`, `equipment`, `weight_class_kg`, `bodyweight_kg`, `age`, `squat_kg`, `bench_kg`, `deadlift_kg`, `total_kg`, `place`, `tested`. `birth_year` (a key `match.py` reads as a date of birth) is the meet year minus the age at the latest meet; `age` is deliberately **not** set at the top level, since the matcher would read it as today's age. `data_date` says which weekly file answered; the record's `body` is the lifter's rows as CSV, so the evidence locker holds what the data said.

## Voter registration

_Checked 2026-11-01. People-search sites lock a person down from a name and a place because they hold the states' voter rolls: residence address, date of birth, and who else is registered at the address. Hunt does the same only where the state hands its list to anyone and puts no condition on its use that an insurer's investigation would break. The survey is NCSL's "Access To and Use Of Voter Registration Lists" (updated 2026-06-10), checked against the statute or the election office's own page wherever a script or the built-in browser could read one; the legal-automation session has the final word on every "possible"._

### Florida (`voter`, built)

- **The rules it runs under** are legal.md V1–V6 (decisions D21–D23): Florida is an allowed state; the import keeps identity only; protected voters are never sought and a miss proves nothing; a background case never runs it; the statewide file is queried only by the case's own seeds, each lookup audited, matches only; a report cites it as corroboration.
- **The record.** The Division of Elections generates a monthly extract of every active and inactive voter in the Florida Voter Registration System and gives it to anyone who asks: an email to VoterExtract@dos.fl.gov with contact details and a postal address, and the disk comes by mail (or is collected in Tallahassee) on the month's scheduled day; a standing request covers a calendar year; the page says the data "IS NOT available by email or online". The Division calls it "public record under Florida law": chapter 119 applies, and Fla. Stat. 97.0585 keeps back only declinations to register, where a person registered, SSN, driver-licence and Florida ID numbers, 16- and 17-year-old preregistrants and (for copying) signatures. A voter exempt under 119.071(4)(d) (judges, police, prosecutors and the other listed classes who ask) is in the extract with a "Y" in field 7 and the protected fields blank, and Hunt drops the row; Address Confidentiality Program participants (741.401–741.465) and preregistered minors the Division leaves out. Florida puts **no use condition** on the list (NCSL: "Not stated"; nothing in chapters 97–98). The brief's 98.0981 is the voting-history and legislative-summary section; the extract's public status rests on chapter 119 and the 97.0585 exemptions.
- **The files.** Two zips a month: `Voter_Registration_YYYYMMDD.zip` with 67 tab-delimited county files (`ALA_20261016.txt` … `WAS_20261016.txt`; 38 columns, no header; the layout PDF has the county, party and race codes) and `Voter_History_YYYYMMDD.zip` (`ALA_H_…`, five columns per vote). A `Y` in column 7, "Requested public records exemption", marks a voter whose protected fields the Division blanked.
- **What Hunt keeps.** The investigator drops the registration files, or the zip itself, into `~/Hunt/voter/FL/` and runs `python -m hunt.sources.voter update` (the app can call `voter.update()`); `voter.meta()` says what is loaded. The import reads the 13 columns in `voter.KEEP`: county, voter ID, last, suffix, first, middle, residence address lines 1 and 2, city, ZIP, birth date, registration date, status. **Race (column 21) and party (column 24) are dropped at import** and never reach the disk; gender, mailing address, precinct and district codes, phone and email are not kept; exempt rows and the history files are not read. Expect a few minutes and about 2 GB for all of Florida (some 14 million voters). The table is built whole and swapped in, so a search during an import still sees the old one; a new month is the same drop-and-run.
- **The search.** `search.fan_out` hands the source the name seed with the case's `location`, `address`, `dob` and `age` seeds (`voter.NARROWS`); without one of those it doesn't run, since a name alone would list strangers (V5). A `location` or `address` seed narrows to its city, street line or ZIP, a `dob` seed to that date, an `age` seed to the birth years it allows; the first name is a prefix match (the rule the other records sources use), actives first, **at most 10 voters** per lookup, and the note says when more fit ("add a street or a date of birth"). Each record enters the case as identity only: `fullname` as registered, `dob` (`match.py` scores it against the subject's dob or age), `address` as one postal line, `location` ("Gainesville, FL"), `county`, `registered`, `status`, `voter_id`, `state`, `file` and `data_date`; its URL is the Division's extract page with `#FL-<voter id>`. **No household and no evidence row until she marks the record "him"**: the page reads who else is registered at the address live from the local table (`voter.household(url)`, names only, at most 12), and `voter.confirm(case, url)` stores the household and the stored columns as the record's evidence, audited. A zero-match note adds that ACP participants and exempt voters aren't in the extract and that no match isn't evidence about where someone lives (V3). A background case never runs the source, and screening leaves it out of the report (V4). In a report a voter record is name, address, registration date and date of birth, cited as "Florida voter extract dated …" (V6).
- **Never:** a request to any website during a search; Florida's "Voter Information Lookup" for anyone but the user (it is the voter's own check); voterrecords.com and the other republishers (their terms bar automation, and some of the lists they carry were released under no-internet conditions).

### Pennsylvania (not built)

Pennsylvania's Full Voter Export (every voter in a county, with date of birth, party, addresses and voting history; $20 from the Department of State, refreshed weekly) is sold under the Voter Registration Act, not the public records law: 25 Pa.C.S. § 1207(b), "The material may not be used for commercial or improper purposes"; § 1404(b), the requester states in writing, on the Department's form, that the information "will not be used for purposes unrelated to elections, political activities or law enforcement"; 4 Pa. Code § 183.14(b)(4)–(5) (the written statement, with identification) and (k), "The list may not be published on the Internet" (upheld against Voter Reference Foundation on 2026-04-24). An insurance investigation is none of elections, political activities or law enforcement, so Hunt builds nothing for Pennsylvania and offers no by-hand link either: the Department's "Find Voter Registration Status" page is for the voter. (The brief's cite, 25 P.S. § 2602, is the Election Code's definitions section; the operative sections are the ones above.)

### Other states

_The Hunt column: **built** (Florida); **possible** = anyone may obtain the list and NCSL records no use restriction, so the statute and the request form must be read before an import is built; **no** = the list is confined to election, political, governmental or law-enforcement use, or to non-commercial use (an insurer's investigation is a commercial purpose), or to requesters Hunt's investigator isn't (a party, a candidate, a registered voter of that state)._

| State | How the list is available | Use restriction (NCSL, 2026-06-10) | Hunt |
|---|---|---|---|
| Alabama | Parties get the state list; others apply to the Secretary of State or the county, for a fee (Ala. Code 17-4-33, 17-4-38) | Electioneering, campaigning or other election purposes; no sale, publication or commercial use | No |
| Alaska | Anyone, for a fee (AS 15.07.127, 15.07.195) | None stated | Possible |
| Arizona | Parties get a list; public inspection at local offices (A.R.S. 16-168) | Non-commercial; political, campaign, election or district-boundary purposes only; no internet distribution | No |
| Arkansas | Anyone, for a fee (Ark. Code 7-5-109) | None stated | Possible |
| California | Candidates, parties, committees, and anyone for election, scholarly, journalistic, political or governmental purposes as the Secretary of State decides (Elec. Code 2194) | Non-commercial; no harassment, solicitation, marketing or online display | No |
| Colorado | Anyone, on request (C.R.S. 1-2-302, 24-72-204) | None stated | Possible |
| Connecticut | Inspection and copies from municipal registrars (C.G.S. 9-35) | Election, scholarly, journalistic, political or governmental use only; no personal, private or commercial use | No |
| Delaware | Parties, candidates and governments free; others may request, for a fee (15 Del. C. 1305) | None stated | Possible |
| District of Columbia | Any person, on request (3 DCMR 510) | Signatures viewed but not copied | Possible |
| Florida | Anyone, the monthly extract on request (Fla. Stat. 97.0585, 119.071) | None | **Built** |
| Georgia | Anyone (O.C.G.A. 21-2-225) | Non-commercial | No |
| Hawaii | Name, address, district and status are public (HRS 11-97) | Other personal information for election or governmental purposes only | No: the public part has no birth date |
| Idaho | Any person (Idaho Code 34-437) | Non-commercial | No |
| Illinois | State political committees and governments; the public views on a screen at the Board's office (10 ILCS 5/1A-25) | Non-commercial; no printing, copying or transmitting | No |
| Indiana | Parties, independent candidates, news media, courts for juries, legislative leaders (IC 3-7-26.4) | Non-commercial; political activities only | No |
| Iowa | Anyone, at cost (Iowa Code 48A.38) | Non-commercial; voting-related, political, official or bona fide political research only | No |
| Kansas | Any person, supervised or as a copy (K.S.A. 25-2320) | Non-commercial (campaign and election use isn't commercial) | No |
| Kentucky | Any citizen may inspect or copy; lists to candidates and committees, others at the Board's discretion (KRS 117.025) | Non-commercial | No |
| Louisiana | Inspection locally; 25 voters together may request a copy (La. R.S. 18:154) | Non-commercial | No |
| Maine | Parties, get-out-the-vote groups, officeholders, governments, law enforcement (21-A M.R.S. 196-A) | Party, get-out-the-vote and campaign activities only | No |
| Maryland | Registered Maryland voters (Elec. Law 3-506) | None stated | No: requester restricted |
| Massachusetts | State party committees, statewide candidate and ballot committees, the jury commissioner, others the Secretary designates (M.G.L. c. 51 § 47C) | None stated | No: requester restricted |
| Michigan | Any person (MCL 168.522, 168.509gg) | None stated | Possible |
| Minnesota | Inspection; copies to any registered voter, for a fee (Minn. Stat. 201.091) | Elections, political activities or law enforcement only | No |
| Mississippi | Any person under the Public Records Act (Miss. Code 23-15-165) | Non-commercial | No |
| Missouri | Any member of the public, for a fee (RSMo 115.157) | Non-commercial | No |
| Montana | Any individual, for a fee (MCA 13-2-115) | Non-commercial | No |
| Nebraska | Any person, for a fee (Neb. Rev. Stat. 32-330) | Elections, political activities, voter registration, law enforcement or jury selection only | No |
| Nevada | Anyone, for a fee (NRS 293.440) | Non-commercial; nothing unrelated to an election | No |
| New Hampshire | Parties and candidates get a copy; any person may view (RSA 654:31) | Non-commercial; no printing, copying or transmitting | No |
| New Jersey | Any voter who pays; parties free (N.J.S.A. 19:31-18.1) | Non-commercial | No |
| New Mexico | On written request (NMSA 1-4-5.5) | Governmental, election and campaign purposes only | No |
| New York | Inspection; copies for purchase after registration closes (Elec. Law 3-103, 5-602) | No non-election use | No |
| North Carolina | Any person, at cost; the State Board posts the files online (G.S. 163-82.10) | None stated; the statute (read 2026-11-01) makes birth dates, SSNs, licence numbers and emails confidential and keeps birth dates off every list | Possible: name and address only |
| North Dakota | Candidates, parties and committees (N.D.C.C. 16.1-02-15) | Election-related purposes | No |
| Ohio | Public inspection; the statewide file is a public record (R.C. 3503.13, 3503.15) | NCSL says non-commercial; the text of 3503.13 (read 2026-11-01) has no use clause | Counsel's call |
| Oklahoma | Oklahoma residents, parties, candidates and others authorised by law (26 O.S. 4-115.2) | None stated | No: requester restricted |
| Oregon | Parties free; any person for a fee (ORS 247.955) | Non-commercial | No |
| Pennsylvania | Inspection; copies to any registered elector, the Full Voter Export at $20 (25 Pa.C.S. 1207, 1404) | Nothing unrelated to elections, political activities or law enforcement; no commercial use; no internet publication | No (above) |
| Rhode Island | Public records; lists to parties and candidates (R.I.G.L. 17-9.1-15) | Political purposes and candidacy only | No |
| South Carolina | Inspection; lists to qualified South Carolina voters (S.C. Code 7-5-170) | Non-commercial | No |
| South Dakota | County file open to inspection (SDCL 12-4-9) | Election purposes only; no sale, commercial use or internet posting | No |
| Tennessee | Any person certifying political purposes (T.C.A. 2-2-138) | Political purposes only | No |
| Texas | Any person (Elec. Code 18.005, 18.008) | Non-commercial (Elec. Code 18.009) | No |
| Utah | Qualified persons under a confidentiality agreement: governments, health care providers, insurers, financial institutions, parties (Utah Code 20A-2-104) | Birth month and year for political purposes only | Counsel's call: insurers are named, the agreement and the birth-date rule are not read |
| Vermont | Any person, at cost, from town clerks (17 V.S.A. 2154) | Non-commercial; no disclosure to foreign governments or federal registration databases | No |
| Virginia | Candidates, committees, incumbents; the public only to promote voter participation (Va. Code 24.2-406) | Campaign and political purposes | No |
| Washington | Any party, committee or person, as a public records request (RCW 29A.08.720) | Non-commercial, a class C felony; any political purpose allowed | No |
| West Virginia | Anyone, for a fee (W. Va. Code 3-2-30) | Non-commercial; no commercial or charitable solicitation, advertising, sale or resale | No |
| Wisconsin | Open to inspection and electronically accessible to any person (Wis. Stat. 6.36) | None in 6.36 (read 2026-11-01); birth dates, licence and SSN are withheld from everyone but officials | Possible: no birth date |
| Wyoming | Candidates, committees, officials, PACs, ballot-issue and voter-participation groups (W.S. 22-2-113) | Political purposes only (non-commercial) | No |

Not built anywhere, whatever the state: third-party voter sites (voterrecords.com and the like; their terms bar scripts, and they republish lists some states released under no-internet conditions), and the states' "check your registration" pages for anyone but the user (they are the voter's own lookup, most want a birth date or licence number, and all bar automation).

### Adding a state

1. Read the statute and the election office's request form, not a summary, and record both here with the verdict; a "possible" above is a reading list, not a go.
2. Get the file by the office's own route (a request, a purchase, a download the office itself publishes) into `~/Hunt/voter/<ST>/`.
3. In `voter.py`: add the state to `BUILT` with the office's page, and give `FILE`, `COLUMNS` and `KEEP` the state's layout (today they are Florida's; make them per-state when the second state arrives). Party, race and whatever the state marks confidential stay out of `KEEP`. `_load`, `lookup` and the record shape need no change.
4. Fixture rows with fictional people in `test_voter.py`; `uv run python test_voter.py`.

## Collection narrowed (compliance audit §3.6, 2026-10-29)

DS1–DS5 of `docs/research/compliance-audit.md`, under decisions D1 (b) (existence checks stay: one request per site, Hunt's own User-Agent, no TLS or header impersonation) and D2 (b) (strava.com and snapchat.com join the deny list). The deny list is `hunt.sources._api.ROBOTS_DENY`, matched by hostname by `_api.denied(url)`. Measured with a public organisation's handle (`nasa`), before and after, from one laptop on one day; sites change their minds, so treat the numbers as the order of magnitude.

| Engine | Before | After | What changed |
|---|---|---|---|
| **Maigret** (`maigret`, pinned 0.6.6) | 509 top sites; 408 answered (243 claimed, 165 available, 100 unknown); 18 s | **385 sites; 273 answered** (151 claimed, 122 available, 111 unknown); 48 s | `maigret.sites()` leaves out 7 deny-list hosts (Facebook, Instagram, Twitter, LinkedIn, Reddit, Threads, Snapchat), 118 sites behind bot walls Maigret would otherwise impersonate Chrome to pass (67 TLS-fingerprint, 31 Cloudflare JS challenge, 19 IP reputation, 10 Cloudflare firewall, 6 custom; overlapping), and 5 that need an activation step (X's guest token among them). The 2 non-GET checks (Discord, LeetCode) were read and kept. 13 sites' browser `User-Agent` and `sec-ch-*` headers are stripped; every request carries Hunt's UA |
| **WhatsMyName** (`whatsmyname`, list pinned to commit `2de6024` of 2026-10-26) | 691 entries; 406 answered (242 found, 164 not found, 278 unknown, 7 error); 31 s | **684 entries; 408 answered** (241 found, 167 not found, 267 unknown, 9 error); 79 s | 7 deny-list entries skipped (Facebook, Instagram, Reddit, Snapchat, Strava, Threads, X); 12 entries' Chrome UA dropped for Hunt's; the 23 POST entries were read (each sends only the handle to a username or profile lookup) and kept in `POST_OK`; an entry added upstream with a POST is skipped until read. No loss from the honest UA |
| **user-scanner** (`user-scanner`, pinned 1.5.2.3) | 127 of 220 modules ran; an unread module could run if its text looked harmless | **103 run** | `_skip` fails closed: nothing runs unless read at 1.5.2.3 and judged silent. Of the 127, 22 impersonate a browser's TLS (`curl_cffi`) and 2 name deny-list hosts (`instagram`, `x`); they are skipped and counted in the note |
| **Facebook** (`facebook`) | Ran in every batch search, one GET per seed | **Out of `SOURCES`** | The app's click action (`sources.facebook.search` for one profile) stays |

The 111 Maigret unknowns after the change: 72 "Request failed" inside Maigret's aiohttp client (four of six such sites sampled, GoodReads, ThemeForest, Flickr groups and WordPress, answer one honest `httpx` GET with a normal 200 page, so this is the client, not a refusal; open question for whoever next upgrades Maigret), 18 bot protection, 5 access denied, 5 login walls, 4 DNS, 4 server errors. A first run straight after the change gave 54 answering and 330 unknown; it didn't repeat and is treated as transient. `search.avatars` imports `wmn.UA`, so avatar downloads now carry Hunt's UA too.

## Free keys

Every key is optional except CourtListener's, and all are off until the investigator sets the env var. Each is free. `health()` carries the same facts per source (`key_status`, `key_url`, `key_free`), so the setup screen can show them live.

| Source(s) | What a free key unlocks | Get it | Env var | Free limit |
|---|---|---|---|---|
| GitHub (`github`) | More profile reads and searches | [Fine-grained token](https://github.com/settings/personal-access-tokens/new), no permissions needed | `HUNT_GITHUB_TOKEN` | 5,000 requests/hr, 30 searches/min (logged out: 60/hr, 10/min) |
| Gravatar (`gravatar`) | More lookups, and every verified account instead of 4 | [Developer dashboard](https://gravatar.com/developers/) → Create New Application | `HUNT_GRAVATAR_KEY` | 1,000 lookups/hr (logged out: 100) |
| OpenFEC (`fec`) | Its own quota instead of the shared `DEMO_KEY` | [api.data.gov sign-up](https://api.data.gov/signup/), approved instantly | `HUNT_FEC_KEY` | 1,000 requests/hr (DEMO_KEY: about 10) |
| CourtListener (`courtlistener`) | The source runs at all; without a token it is skipped | Free account, then [your token](https://www.courtlistener.com/profile/api-token/) | `HUNT_COURTLISTENER_TOKEN` | 5/min, 50/hr, 125/day (API docs, 2026-10-29); the profile page shows your actual usage |
| State portals (`licences`, `businesses`, `fmcsa`) | A token's own quota instead of a shared per-IP pool | Free account on any Data & Insights portal, then Developer Settings → Create New App Token (e.g. [data.texas.gov](https://data.texas.gov/profile/edit/developer_settings)) | `HUNT_SOCRATA_TOKEN` | About 1,000 requests/hr per token. One token was accepted by all 11 portals Hunt searches (checked 2026-10-29); if one ever rejects it, the note says so |
| SEC EDGAR (`edgar`) | Nothing to unlock; SEC asks callers to say who they are | No sign-up: set it to your firm and a contact email | `HUNT_SEC_UA` | 10 requests/s either way |

Not listed:
- YouTube Data API: Hunt reads no YouTube key.
- SerpApi, Google Programmable Search, Apify: no Hunt source uses them, and the image-search and social-scraping work they would serve was dropped.

## Records in the app (for the frontend)

**What triggers them.**
- A `name` seed runs every records source: `fec`, `edgar`, `npi`, `courtlistener` (with a token), `licences`, `businesses`, `fmcsa`, `voter` (once a Florida extract is indexed; otherwise its note starts "not run"). It also runs the name searches on GitHub, Bluesky, Mastodon and Stack Overflow; those are accounts, not records.
- `location` and `address` seeds don't run records, but they are what separates the subject from namesakes: the scorer compares each record's `location` with them. The wizard should ask for the subject's city or state whenever a name is given. `voter` is the exception: `search.fan_out` hands it the case's city, street, ZIP, date of birth and age seeds, and it runs only when one of them narrows the name (legal.md V5), returning at most 10 voters; never on a background case (V4).
- A one-word name is not searched; the note says so.

**Group records by what they show:**

| Group | Sources | Investigator's question |
|---|---|---|
| Working | `licences`, `businesses`, `npi`, `fmcsa` (officers), `fec` (employer, occupation), `edgar` | Is the claimant licensed, trading or employed somewhere? |
| Driving | `fmcsa` (owner-operator; trucks, drivers, interstate) | Does the claimant run or drive for a carrier? |
| Courts | `courtlistener`, `courts` | Earlier suits, claims, judgments or hearings? Show `courts.search_links(seeds)` under this group as "Search Harris County records →" links: the portals Hunt can't query. They come ordered: the case's own states first (from its location and address seeds), within each the county whose name or city the place names, then the national links. `state` is on each link for grouping |
| Money and politics | `fec`, `edgar` | Where were they, and with whom, when they donated or filed? |
| Who and where | `voter` | Is the claimant registered at that address, since when, and who else is registered there? Each record's `dob` and `address` are what the Florida roll adds that no other source has. The household isn't in the record: show it from `voter.household(url)` (names only) when the page opens, and on "him" call `voter.confirm(case, url)`, which stores it with the evidence row. If the note says "not run" for want of an extract, the setup screen should offer the import: the investigator drops the Division's files in `~/Hunt/voter/FL/` and Hunt runs `voter.update()` (a few minutes); if for want of a place or birth date, the wizard asks for one. Never shown on a background case |
| Activity | `activity` | Competing after the injury date? Each record's `meets[]` carries a `date`; show the ones after `injury_date` first, with the lift totals. Show `activity.search_links(seeds)` under the group for the race-results sites. If the note says "not run", the setup screen should offer the one-time 170 MB load (`activity.update()`) |

**On each record, show:**
1. The record's own name as written (`fullname`), not the searched name. "ROBERT J VANCE" vs "Robert Vance" is the first namesake check.
2. `roles`: licence holder, president, registered agent, company officer…
3. The organisation (`business`, `carrier`, `filer`) and the place (`location`, `county`; `business_location` where the business is elsewhere).
4. Identifiers: licence number, NPI, USDOT, CIK, registry number, `year_of_birth` (TX Medical Board), `voter_id` and `dob` (voter roll); for a court record, `court`, `docket_number`, `case_type` and the `roles` the person has in it (plaintiff, defendant, respondent, debtor).
5. Status and dates (`status`, `issued`, `expires`, `registered`, `last_update`). Derive an **active now** badge from status and expiry. An expired licence or inactive carrier still shows the history.
6. The record page (the candidate's URL) and when it was fetched. The URL is the evidence; the raw response is in the evidence locker.
7. The match verdict and its reasons, as for accounts. Until name seeds get the corroboration cap in `match.py`, show records found by name alone with a "name only" label rather than the verdict.

**Coverage, from the run's note.** Each records run's note lists the tables searched, those rate-limited or failed, and the row cap. Show it under the group, e.g. "searched 27 licence tables (TX, CO, DE, IL, WA, OR, CT, NY, VT, NYC) and the FL and VA files; not covered: CA and other states." A local table that isn't loaded is named in the note with its load command: the setup screen can offer it. "Nothing found" must not read as "has no licence".

**Don't surface by default:** street addresses of homes. CT's principal residences are in the raw record. Show the town, and keep the street one click away for the investigator who needs it. The voter roll is the exception: its `address` is the answer the investigator asked for, so it shows on the record (never in screening mode's shared output; `household` stays names only).

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
- CourtListener limits: [API overview (5/min, 50/hr, 125/day)](https://wiki.free.law/c/courtlistener/help/api/rest/v4/overview), [free.law issue #7200](https://github.com/freelawproject/courtlistener/issues/7200)
- Activity records: [OpenPowerlifting data](https://openpowerlifting.gitlab.io/opl-csv/), [its FAQ](https://www.openpowerlifting.org/faq), [RunSignup API](https://runsignup.com/API), [RunSignup get-results](https://runsignup.com/API/race/:race_id/results/get-results/GET), [CrossFit terms](https://www.crossfit.com/terms-of-use), robots.txt of openpowerlifting.org, runsignup.com, athlinks.com, ultrasignup.com, strava.com (read 2026-10-29)
- Court records: [CourtListener search API v4](https://wiki.free.law/c/courtlistener/help/api/rest/v4/search), [PACER developer resources](https://pacer.uscourts.gov/file-case/developer-resources), [PACER fees](https://pacer.uscourts.gov/pacer-pricing-how-fees-work), [eFileTexas / re:SearchTX usage agreement](https://www.efiletexas.gov/terms.htm), [re:SearchTX FAQ](https://research.txcourts.gov/CourtRecordsSearch/Assets/site/faq/TX_faq_Jan_1_2022.html), [UJS portal terms](https://ujsportal.pacourts.us/Home/Terms), [Maryland reCAPTCHA notice](https://www.mdcourts.gov/sites/default/files/import/mdec/updates/20220328recaptchanotice.pdf), [MiCOURT SCAO memo](https://courts.michigan.gov/4966da/siteassets/reports/psc/micourt-case-search-automatically-set-aside-convictions.pdf), [Judici access policy](https://courtsupport.judici.com/JSA0808P), [NYC Open Data](https://www.nyc.gov/opendata/get-started/what-is-open-data-), [Chicago data terms](https://www.chicago.gov/city/en/narr/foia/data_disclaimer.html), [OATH Hearings dataset note](https://data.cityofnewyork.us/d/jz4z-kudi), robots.txt of oscn.net, search.txcourts.gov, hcdistrictclerk.com, courtclerk.org, judici.com, courts.mo.gov, publicindex.sccourts.org, records.courts.alaska.gov, coloradojudicial.gov (read 2026-10-29)
- Voter registration: [NCSL, Access To and Use Of Voter Registration Lists (2026-06-10)](https://www.ncsl.org/elections-and-campaigns/access-to-and-use-of-voter-registration-lists), [Florida voter extract request](https://dos.fl.gov/elections/data-statistics/voter-registration-statistics/voter-extract-request/), [Florida extract file layout (May 2025)](https://files.floridados.gov/media/708728/final-voter-extract-disk-file-layout-rev-20250516.pdf), [Fla. Stat. 97.0585](http://www.leg.state.fl.us/statutes/index.cfm?App_mode=Display_Statute&URL=0000-0099/0097/Sections/0097.0585.html), [Fla. Stat. 98.0981](http://www.leg.state.fl.us/statutes/index.cfm?App_mode=Display_Statute&URL=0000-0099/0098/Sections/0098.0981.html), [Fla. Stat. 119.071](http://www.leg.state.fl.us/statutes/index.cfm?App_mode=Display_Statute&URL=0100-0199/0119/Sections/0119.071.html), [25 Pa.C.S. § 1207](https://www.palegis.us/statutes/consolidated/view-statute?txtType=HTM&ttl=25&div=0&chapter=12&section=7&subsctn=0), [25 Pa.C.S. § 1404](https://www.palegis.us/statutes/consolidated/view-statute?txtType=HTM&ttl=25&div=0&chapter=14&section=4&subsctn=0), [4 Pa. Code § 183.14](https://www.pacodeandbulletin.gov/Display/pacode?file=/secure/pacode/data/004/chapter183/s183.14.html), [PA Full Voter Export](https://www.pavoterservices.pa.gov/pages/purchasepafullvoterexport.aspx), [Bloomberg Law on the PA internet ban, 2026-04-24](https://news.bloomberglaw.com/litigation/pennsylvanias-voter-data-online-sharing-ban-stands-judge-says), [G.S. 163-82.10](https://www.ncleg.gov/EnactedLegislation/Statutes/HTML/BySection/Chapter_163/GS_163-82.10.html), [Wis. Stat. 6.36](https://docs.legis.wisconsin.gov/statutes/statutes/6/II/36), [R.C. 3503.13](https://codes.ohio.gov/ohio-revised-code/section-3503.13)
- FEC use restriction: [FEC: sale or use of contributor information](https://www.fec.gov/updates/sale-or-use-contributor-information), [11 CFR 104.15](https://www.law.cornell.edu/cfr/text/11/104.15)
- Records: [Socrata discovery API](https://dev.socrata.com/docs/other/discovery), [Socrata app tokens](https://dev.socrata.com/docs/app-tokens), [TDLR All Licenses](https://data.texas.gov/d/7358-krk7), [Colorado DORA licences](https://data.colorado.gov/d/7s5z-vewr), [Illinois IDFPR licences](https://illinois-edp.data.socrata.com/d/pzzh-kp68), [WA L&I contractors](https://data.wa.gov/d/m8qx-ubtq), [NY active corporations](https://data.ny.gov/d/n9v6-gdp6), [Oregon active businesses](https://data.oregon.gov/d/tckn-sxa6), [CT principals](https://data.ct.gov/d/ka36-64k6), [FMCSA company census](https://catalog.data.gov/dataset/company-census-file), [FMCSA QCMobile](https://mobile.fmcsa.dot.gov/QCDevsite/home), [DCA open data](https://www.dca.ca.gov/data/index.shtml), [FAA releasable airmen](https://www.faa.gov/licenses_certificates/airmen_certification/releasable_airmen_download), [OpenCorporates terms](https://opencorporates.com/terms-of-use-2/)
- Rejected: [ORCID API limits](https://info.orcid.org/ufaqs/what-are-the-api-limits/), [ORCID public API terms](https://info.orcid.org/public-client-terms-of-service/), [npm open-source terms](https://docs.npmjs.com/policies/open-source-terms), [BrokerCheck permitted uses](https://www.finra.org/investors/investing/working-with-investment-professional/about-brokercheck/permitted-uses)
- [Maltego plans](https://docs.maltego.com/support/solutions/articles/15000036759-maltego-products-and-plans)
- [IntelTechniques tools](https://inteltechniques.com/tools/)
- [OSINT Industries pricing](https://www.techjockey.com/detail/osint-industries)
- [Skopenow comparison](https://www.skopenow.com/people-and-business-search-comparison)
- [holehe vs user-scanner](https://dev.to/the_king89/rip-holehe-why-user-scanner-is-the-new-king-of-email-osint-2cff)
