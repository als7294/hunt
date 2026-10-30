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
| **YouTube Data API v3** | Official | Free, 10K units/day | Low. **Wired in** on `HUNT_YOUTUBE_KEY` (`public.py`); RSS without a key |
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
| **YouTube** | The Data API v3 on `HUNT_YOUTUBE_KEY`: `channels.list` (`forHandle`, `forUsername` or `id`; 1 unit) → the uploads playlist → `playlistItems.list` (50 per unit), newest first, stopped at `since`. Without a key, the RSS feed as before | Every upload with its full description, published time and thumbnails (kept as evidence copies). Videos aren't downloaded | Quota 10,000 units a day per project; `quotaExceeded` or `keyInvalid` become a failed note. Developer Policies III.E.4: API data is stored at most 30 days unless refreshed or deleted (how a case file complies is for counsel; the note says so) | `MAX_POSTS` |
| **Instagram, Facebook** | **Not read automatically.** The fetcher answers with a note: robots.txt default-deny, and Meta's embed terms bar storing embed content. They come through the Hunt Browser, or through Apify on the investigator's own key | — | at the first request | — |
| X, Threads | **Not collected.** gallery-dl: `AuthRequired`, "authenticated cookies needed to access this timeline"; yt-dlp has no profile support (a single tweet only when it holds a video); Threads is unsupported in both; robots default-deny | — | at the profile | — |

**Tried and parked on 2026-10-29.** gallery-dl 1.32.16 walked a public Facebook Page's photos (fbid, caption, UTC date, CDN image that fetched logged out; one request per photo; `abort()` filter at `since`) and Instagram's per-post embed page (`/p/<code>/embed/captioned/`: caption, image or video, carousel children; `/<user>/embed/` listed the latest 6 posts). Both worked on `nasa` and both were dropped on the legal brief: Facebook's robots.txt is `Disallow: /` for unnamed agents, and Meta's embed terms bar storage and analysis. The code and its tests are on branch `parked/hunt-facebook-instagram-readers` (commit `7374c04`). yt-dlp's TikTok profile listing also worked (61 videos, streamed, stopped at `since`) and was dropped for the internal API it calls.

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
| **State licence and business portals** (Socrata) | Keyless; throttled by IP; free app token ~1,000 req/hr | TX, CO, DE, IL, WA, OR, NYC licences; NY, OR, CT, CO, PA business registries. **Wired in** |
| **FMCSA carrier census** | Keyless (data.transportation.gov) | Owner-operators and carrier officers. **Wired in** |
| **Court and hearing tables** (Socrata) | Keyless | NYC Housing Court, suits against NYC, OATH trials and DOB/ECB summonses, NYS tax warrants, Ohio Court of Claims, Chicago administrative hearings, Texas TCEQ judgments. **Wired in** (`courts`). Every other court portal is opened by hand: see [Court records](#court-records) |
| OpenCorporates | API key required; free keys only for public-benefit "Permitted Users" | Commercial use needs a paid key: rejected |
| FAA airmen registry | Monthly ZIP of CSVs (registry.faa.gov) | Server answers scripted requests with 503; not automated (see below) |
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
| **Wayback CDX** (`wayback`) | url → capture history. Username → archived profiles on X/Twitter, Instagram, TikTok, Reddit, YouTube (deleted accounts; Facebook is the `facebook` source's) | ~60/min; Hunt sends 1/s and stops at a 429 | none | An archived URL isn't proof an account existed |
| **OpenFEC** (`fec`) | name → itemized contributions (> $200) grouped per donor: city, ZIP, employer, occupation, totals, recipients, filing images | `DEMO_KEY` 10/hr | `HUNT_FEC_KEY` (1,000/hr) | **52 U.S.C. 30111(a)(4) / 11 CFR 104.15:** no use to solicit contributions or for commercial purposes like marketing. A report isn't solicitation; the firm should confirm |
| **SEC EDGAR** (`edgar`) | name → filers with their own CIK (insiders; address of record, form types) and companies whose filings contain the exact name | 10 req/s; ≤ 7 requests per name | `HUNT_SEC_UA` (your firm + contact) | SEC's firewall 403s any User-Agent containing "github.com" |
| **NPI Registry** (`npi`) | first + last name → providers' practice address and phone, specialty, licence numbers, **former names** | None published | none | Public CMS data (FOIA) |
| **CourtListener** (`courtlistener`) | name → federal RECAP dockets with that party (case, court, docket number, dates, parties, nature of suit) and **case law** with the name in the caption (every state's appellate courts, federal appellate and district opinions: case, court, docket number, date, citation, judge, parties split from the caption) | 5/min, 50/hr, 125/day per account (API docs); two requests per name | `HUNT_COURTLISTENER_TOKEN`, **required**; off without it | RECAP is a sample of PACER, not every case. A state trial case appears only if it was appealed |
| **Court and hearing tables** (`courts`) | first + last name → cases naming the person in 8 official tables: NYC Housing Court cases (HPD v. owner), civil suits by or against the City of New York (court, index number, disposition, payout), OATH trials (city employee discipline, licence matters), DOB summonses heard at OATH/ECB (respondent's address, hearing result, penalty), NYS tax warrants (docketed judgments: amount, county, the warrant PDF), Ohio Court of Claims (claims against the state), Chicago administrative hearings (ordinance violations: hearing, disposition, fine), Texas TCEQ civil judgments. Each record: court, case or docket number, the person's **role** (plaintiff, defendant, respondent, debtor…), filing date, case type, status or disposition, and the city or address shown | Socrata: throttled by IP; one request per table per name, 50 rows each | `HUNT_SOCRATA_TOKEN` | Public records. Coverage is a few jurisdictions, never a state's whole docket; `courts.search_links(seeds)` gives the portals to open by hand |
| **State licences** (`licences`) | first + last name → licences in 11 official tables: TX TDLR trades, TX real estate and inspectors (with sponsoring broker), TX Medical Board (with **year of birth**), CO DORA (all professions, with verify link), DE, IL IDFPR, WA L&I contractors and their principals (with dates), OR CCB contractors, NYC Buildings. Licence type and number, status, issue and expiry dates, business, city | Socrata: throttled by IP; one request per dataset per name, 50 rows each | `HUNT_SOCRATA_TOKEN` (~1,000/hr) | Public records; most tables public domain. Coverage is per state, never national |
| **Business registries** (`businesses`) | first + last name → businesses the person runs or fronts: NY active corporations (chief executive, registered agent, process name), OR active businesses (every role, including sole-proprietor registrants), CT principals (role, residence town; business name joined in), CO registered agents and trade-name registrants, PA parties. Role, business, entity type, status, dates, city | as above, 6 tables | `HUNT_SOCRATA_TOKEN` | Officers' home towns are published by the states; Hunt shows the town, not the street |
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
| California DCA / CSLB | No API. DCA posts monthly licensee files per board; CSLB's lookup is a web form. A bulk import could come later |
| Florida DBPR | No API; "instant public records" CSV files per profession. Same bulk-import route as California |
| FAA airmen registry | A monthly ZIP of CSVs (`registry.faa.gov/database/CS<MMYYYY>.zip`). The server answered Hunt's scripted HEAD with a 503, so Hunt doesn't fetch it; getting around that would be bot-check circumvention. Size not measured. **Decision for Aaron:** an investigator can download it by hand and Hunt could import the file |

### Adding a state

Most states publish licence or business tables on Socrata portals. To add one:
1. Find candidates with the discovery API: `https://api.us.socrata.com/api/catalog/v1?q=license&only=dataset`.
2. Read the columns (metadata only, no rows) at `https://<domain>/api/views/<id>.json`.
3. Add a `Dataset` to `licences.py` or `businesses.py`: which column(s) hold the name and what role it plays, a record mapping, and the column that identifies a record.

The search, filtering, proxy, health probe and note come with it. Tables already checked and ready to add:
- NY registered tax preparers (`data.ny.gov` `b7jj-bh4g`)
- NY home inspectors (`r9fr-48vu`)
- OR notaries (`data.oregon.gov` `j2pk-zk6z`)
- OR building-codes licences (`vhbr-cuaq`)
- IL asbestos workers (`illinois-edp.data.socrata.com` `437c-unzu`)
- Vermont fire-safety licences (`data.vermont.gov` `cy8e-89cz`)

ArcGIS Hub portals would need a second engine (`FeatureServer/0/query`); none of the states checked so far needed one.

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

Each probe is a HEAD through `HUNT_PROXY` (a GET when HEAD isn't served), with an 8-second timeout, to a URL that spends no quota: GitHub's `/rate_limit`, FEC's docs page, each Socrata table's metadata. A row never contains a key's value. Live on 2026-10-29: 18 of 19 ready; CourtListener wasn't, because it has no token.

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
| [TCEQ Civil Judgments](https://data.texas.gov/d/7ift-kbgd) `7ift-kbgd` | Texas district courts: environmental judgments the Attorney General obtained for TCEQ | respondent, district-court docket number, county, order date, penalty, fees, costs | small, yearly | Texas Open Data |

Rejected on inspection: [OATH Hearings Division Case Status](https://data.cityofnewyork.us/d/jz4z-kudi) `jz4z-kudi` (24M summonses) **dropped the respondent's first name, street, city and state on 2026-05-04**; a last name alone can't tell people apart, so it isn't searched. OATH's [Summons Finder](https://a820-ecbticketfinder.nyc.gov/searchHome.action) is the by-hand route.

**CourtListener** (`courtlistener`, already wired for RECAP) now also runs the case-law search (`type=o`, `caseName:"<name>"`), which covers every state's appellate courts, so a state case that was appealed shows up even where the trial court's portal bars scripts. Fields confirmed from the v4 search docs: `caseName`, `court`, `court_id`, `dateFiled`, `docketNumber`, `citation`, `judge`, `attorney`, `status`, `absolute_url`. Parties are split from the caption; there is no party field on opinions. Two requests per name against the free account's 5/min, 50/hr, 125/day (the API docs now state these; the earlier "third-party report" is official). Not verified live: Hunt has no token.

**PACER Case Locator**: the [developer page](https://pacer.uscourts.gov/file-case/developer-resources) offers an Authentication API and a PCL API, both against a PACER account, and the [fee schedule](https://pacer.uscourts.gov/pacer-pricing-how-fees-work) bills a search "by the number of pages it generates… even if the search displays 'no matches found'" at $0.10 a page (waived under $30 a quarter). Not keyless, not free, and the developer page tells scrapers to run "between 6 p.m. and 6 a.m. Central Time": a by-hand link under the investigator's own account.

### Per state

Built = searched by Hunt (`courts.DATASETS`); by hand = `courts.search_links` gives the URL and the investigator opens it under the portal's own terms. Liveness is one GET on 2026-10-29; a portal that was unreachable or 404 from a script that day isn't listed rather than guessed.

| State | Built | By hand (why not built) |
|---|---|---|
| CA | nothing published as open data | Appellate courts party search (form only; `robots.txt` allows generic crawlers but blocks named AI bots; WAF 403 to Hunt). LA Superior Court (civil name searches are paid, $1–4 a search, criminal $4.75; third-party reports). San Francisco (search page redirects to a CAPTCHA). San Diego (WAF 403). Orange, Santa Clara (403). Case law via CourtListener |
| TX | TCEQ civil judgments | re:SearchTX (registration with a card on file; licence "solely for… internal use", no bulk copying, no searchable third-party database; WAF 403). Appellate TAMES (`robots.txt` Disallow: /). Harris County District Clerk (`robots.txt` disallows every search page), Harris County Clerk, Harris justice courts, Dallas (Odyssey), Tarrant (Odyssey). Bexar's search host didn't answer a script; Travis has no stable public URL found |
| FL | nothing | DCAs via ACIS. Miami-Dade civil and criminal (the criminal system's requirements say "personal and public non-commercial (educational) use", search snippet, page 404s to scripts). Broward, Orange, Palm Beach, Pinellas (moved to courtrecords.mypinellasclerk.gov), Duval. Smaller clerks (Bay, Walton, Leon) gate the search behind a personal-use disclaimer. Hillsborough HOVER and the Supreme Court docket didn't answer a script |
| NY | Housing Court (HPD), Law Department suits, OATH trials, DOB/ECB summonses, NYS tax warrants | WebCivil Supreme, eCourts WebCivil Local, WebCrims, NYSCEF by party name (every iapps.courts.state.ny.us page answers scripts with 403; WebCrims reportedly needs a CAPTCHA, **unverified**). OATH Summons Finder. NYS tax warrant search (older warrants than the 2025 table) |
| PA | nothing | UJS portal (its terms say nothing about automation; it is a JavaScript application with docket sheets as PDFs and no API). Philadelphia civil docket (disclaimer page) |
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
| AL, AR, CT, DE, HI, KY, LA, ME, MS, MT, NE, NH, NJ, SD, TN, UT, VT, WV, WY | **not yet** | AL (Alacourt), KY (CourtNet), NE (JUSTICE), UT (Xchange), WV and MS are paid; CT's and VT's hosts didn't answer a script on the day; NJ's portal sits behind single sign-on; the rest have county-by-county or no online search |

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
| ArcGIS Hub | Only Cape Town and Arlington TX "court cases" layers came up (locations, not parties); no US name-level court data |

Ready to add with one `Dataset` line each, when a case needs them: Everett WA prosecutor hearing calendar (`data.everettwa.gov` `ppic-abeb`), NYC Open Article 7 tax-assessment petitions (`aht6-vxai`, nearly all LLCs), Chicago building-code scofflaw list (`crg5-4zyp`), Ohio Court of Claims public-records cases (`fxn9-cg25`, requester and respondent) and hearing calendar (`a5tk-vp2p`). Not courts but found on the way: NYS attorney registrations (`data.ny.gov` `eqw2-r5nb`) and Connecticut DPH, DCP and real-estate licence decisions (`262e-rymj`, `2twc-xaxs`, `9ky9-v9uu`) belong in `licences`; Colorado UCC debtors (`8upq-58vz`) in `businesses`.

### Adding a state (courts)

The three steps in [Adding a state](#adding-a-state) apply; two conventions on top:
- A table whose name column is a **case caption** ("A v. B", "A Plaintiff v. B Defendant") sets `caption` in its record mapping and an entry in `courts.SIDES` (the left and right roles). `courts.search` then keeps only the side that names the person as `fullname` and sets `roles` from the caption's own role word or the side.
- A portal that bars scripts goes in `courts.PORTALS[state]` as `(label, url)`, only after one GET (or a `robots.txt` disallow, which is a by-hand link but can't be checked) confirmed it is live. `{name}`, `{first}` and `{last}` in a URL or label are filled from the name seed. States without an entry are "not yet"; `states_in` reads state names and codes from location and address seeds.

## Free keys

Every key is optional except CourtListener's, and all are off until the investigator sets the env var. Each is free. `health()` carries the same facts per source (`key_status`, `key_url`, `key_free`), so the setup screen can show them live.

| Source(s) | What a free key unlocks | Get it | Env var | Free limit |
|---|---|---|---|---|
| GitHub (`github`) | More profile reads and searches | [Fine-grained token](https://github.com/settings/personal-access-tokens/new), no permissions needed | `HUNT_GITHUB_TOKEN` | 5,000 requests/hr, 30 searches/min (logged out: 60/hr, 10/min) |
| Gravatar (`gravatar`) | More lookups, and every verified account instead of 4 | [Developer dashboard](https://gravatar.com/developers/) → Create New Application | `HUNT_GRAVATAR_KEY` | 1,000 lookups/hr (logged out: 100) |
| OpenFEC (`fec`) | Its own quota instead of the shared `DEMO_KEY` | [api.data.gov sign-up](https://api.data.gov/signup/), approved instantly | `HUNT_FEC_KEY` | 1,000 requests/hr (DEMO_KEY: about 10) |
| CourtListener (`courtlistener`) | The source runs at all; without a token it is skipped | Free account, then [your token](https://www.courtlistener.com/profile/api-token/) | `HUNT_COURTLISTENER_TOKEN` | 5/min, 50/hr, 125/day (API docs, 2026-10-29); the profile page shows your actual usage |
| State portals (`licences`, `businesses`, `fmcsa`) | A token's own quota instead of a shared per-IP pool | Free account on any Data & Insights portal, then Developer Settings → Create New App Token (e.g. [data.texas.gov](https://data.texas.gov/profile/edit/developer_settings)) | `HUNT_SOCRATA_TOKEN` | About 1,000 requests/hr per token. Socrata documents tokens as working across its portals; if one portal rejects it, the note says so |
| SEC EDGAR (`edgar`) | Nothing to unlock; SEC asks callers to say who they are | No sign-up: set it to your firm and a contact email | `HUNT_SEC_UA` | 10 requests/s either way |

Not listed:
- YouTube Data API: Hunt reads no YouTube key.
- SerpApi, Google Programmable Search, Apify: no Hunt source uses them, and the image-search and social-scraping work they would serve was dropped.

## Records in the app (for the frontend)

**What triggers them.**
- A `name` seed runs every records source: `fec`, `edgar`, `npi`, `courtlistener` (with a token), `licences`, `businesses`, `fmcsa`. It also runs the name searches on GitHub, Bluesky, Mastodon and Stack Overflow; those are accounts, not records.
- `location` and `address` seeds don't run records, but they are what separates the subject from namesakes: the scorer compares each record's `location` with them. The wizard should ask for the subject's city or state whenever a name is given.
- A one-word name is not searched; the note says so.

**Group records by what they show:**

| Group | Sources | Investigator's question |
|---|---|---|
| Working | `licences`, `businesses`, `npi`, `fmcsa` (officers), `fec` (employer, occupation), `edgar` | Is the claimant licensed, trading or employed somewhere? |
| Driving | `fmcsa` (owner-operator; trucks, drivers, interstate) | Does the claimant run or drive for a carrier? |
| Courts | `courtlistener`, `courts` | Earlier suits, claims, judgments or hearings? Show `courts.search_links(seeds)` under this group as "Search Harris County records →" links: the portals Hunt can't query |
| Money and politics | `fec`, `edgar` | Where were they, and with whom, when they donated or filed? |

**On each record, show:**
1. The record's own name as written (`fullname`), not the searched name. "ROBERT J VANCE" vs "Robert Vance" is the first namesake check.
2. `roles`: licence holder, president, registered agent, company officer…
3. The organisation (`business`, `carrier`, `filer`) and the place (`location`, `county`; `business_location` where the business is elsewhere).
4. Identifiers: licence number, NPI, USDOT, CIK, registry number, `year_of_birth` (TX Medical Board); for a court record, `court`, `docket_number`, `case_type` and the `roles` the person has in it (plaintiff, defendant, respondent, debtor).
5. Status and dates (`status`, `issued`, `expires`, `registered`, `last_update`). Derive an **active now** badge from status and expiry. An expired licence or inactive carrier still shows the history.
6. The record page (the candidate's URL) and when it was fetched. The URL is the evidence; the raw response is in the evidence locker.
7. The match verdict and its reasons, as for accounts. Until name seeds get the corroboration cap in `match.py`, show records found by name alone with a "name only" label rather than the verdict.

**Coverage, from the run's note.** Each records run's note lists the tables searched, those rate-limited or failed, and the row cap. Show it under the group, e.g. "searched 11 licence tables (TX, CO, DE, IL, WA, OR, NYC); not covered: CA, FL and other states." "Nothing found" must not read as "has no licence".

**Don't surface by default:** street addresses of homes. CT's principal residences are in the raw record. Show the town, and keep the street one click away for the investigator who needs it.

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
- Court records: [CourtListener search API v4](https://wiki.free.law/c/courtlistener/help/api/rest/v4/search), [PACER developer resources](https://pacer.uscourts.gov/file-case/developer-resources), [PACER fees](https://pacer.uscourts.gov/pacer-pricing-how-fees-work), [eFileTexas / re:SearchTX usage agreement](https://www.efiletexas.gov/terms.htm), [re:SearchTX FAQ](https://research.txcourts.gov/CourtRecordsSearch/Assets/site/faq/TX_faq_Jan_1_2022.html), [UJS portal terms](https://ujsportal.pacourts.us/Home/Terms), [Maryland reCAPTCHA notice](https://www.mdcourts.gov/sites/default/files/import/mdec/updates/20220328recaptchanotice.pdf), [MiCOURT SCAO memo](https://courts.michigan.gov/4966da/siteassets/reports/psc/micourt-case-search-automatically-set-aside-convictions.pdf), [Judici access policy](https://courtsupport.judici.com/JSA0808P), [NYC Open Data](https://www.nyc.gov/opendata/get-started/what-is-open-data-), [Chicago data terms](https://www.chicago.gov/city/en/narr/foia/data_disclaimer.html), [OATH Hearings dataset note](https://data.cityofnewyork.us/d/jz4z-kudi), robots.txt of oscn.net, search.txcourts.gov, hcdistrictclerk.com, courtclerk.org, judici.com, courts.mo.gov, publicindex.sccourts.org, records.courts.alaska.gov, coloradojudicial.gov (read 2026-10-29)
- FEC use restriction: [FEC: sale or use of contributor information](https://www.fec.gov/updates/sale-or-use-contributor-information), [11 CFR 104.15](https://www.law.cornell.edu/cfr/text/11/104.15)
- Records: [Socrata discovery API](https://dev.socrata.com/docs/other/discovery), [Socrata app tokens](https://dev.socrata.com/docs/app-tokens), [TDLR All Licenses](https://data.texas.gov/d/7358-krk7), [Colorado DORA licences](https://data.colorado.gov/d/7s5z-vewr), [Illinois IDFPR licences](https://illinois-edp.data.socrata.com/d/pzzh-kp68), [WA L&I contractors](https://data.wa.gov/d/m8qx-ubtq), [NY active corporations](https://data.ny.gov/d/n9v6-gdp6), [Oregon active businesses](https://data.oregon.gov/d/tckn-sxa6), [CT principals](https://data.ct.gov/d/ka36-64k6), [FMCSA company census](https://catalog.data.gov/dataset/company-census-file), [FMCSA QCMobile](https://mobile.fmcsa.dot.gov/QCDevsite/home), [DCA open data](https://www.dca.ca.gov/data/index.shtml), [FAA releasable airmen](https://www.faa.gov/licenses_certificates/airmen_certification/releasable_airmen_download), [OpenCorporates terms](https://opencorporates.com/terms-of-use-2/)
- Rejected: [ORCID API limits](https://info.orcid.org/ufaqs/what-are-the-api-limits/), [ORCID public API terms](https://info.orcid.org/public-client-terms-of-service/), [npm open-source terms](https://docs.npmjs.com/policies/open-source-terms), [BrokerCheck permitted uses](https://www.finra.org/investors/investing/working-with-investment-professional/about-brokercheck/permitted-uses)
- [Maltego plans](https://docs.maltego.com/support/solutions/articles/15000036759-maltego-products-and-plans)
- [IntelTechniques tools](https://inteltechniques.com/tools/)
- [OSINT Industries pricing](https://www.techjockey.com/detail/osint-industries)
- [Skopenow comparison](https://www.skopenow.com/people-and-business-search-comparison)
- [holehe vs user-scanner](https://dev.to/the_king89/rip-holehe-why-user-scanner-is-the-new-king-of-email-osint-2cff)
