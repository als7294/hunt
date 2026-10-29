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
| **CourtListener / RECAP** | **Token required for every API call** (anonymous gets 401/403) | Free account reportedly 5/min, 50/hr, 125/day since 2026-05-07 (official docs still say 5,000/hr). **Wired in, opt-in** |
| **NPPES NPI Registry** | Keyless, no published limit | US healthcare providers by name. **Wired in** |
| **Wayback CDX** | Free, no key | ~60 req/min (2023 maintainer figure); back off on 429. **Wired in** |
| **Nominatim / OSM** | Public instance 1 req/s, ODbL attribution | Self-host for scale |
| PACER | $0.10/page (rising to $0.12 on 2027-01-01) | Not free; out of MVP |
| **State licence and business portals** (Socrata) | Keyless; throttled by IP; free app token ~1,000 req/hr | TX, CO, DE, IL, WA, OR, NYC licences; NY, OR, CT, CO, PA business registries. **Wired in** |
| **FMCSA carrier census** | Keyless (data.transportation.gov) | Owner-operators and carrier officers. **Wired in** |
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
| **CourtListener** (`courtlistener`) | name → federal RECAP dockets with that party: case, court, docket number, dates, parties | Free account 5/min, 50/hr, 125/day (third-party report) | `HUNT_COURTLISTENER_TOKEN`, **required**; off without it | RECAP is a sample of PACER, not every case |
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
- `ready`: reachable, or nothing to reach, and no required key missing

Each probe is a HEAD through `HUNT_PROXY` (a GET when HEAD isn't served), with an 8-second timeout, to a URL that spends no quota: GitHub's `/rate_limit`, FEC's docs page, each Socrata table's metadata. A row never contains a key's value. Live on 2026-10-29: 18 of 19 ready; CourtListener wasn't, because it has no token.

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
| Courts | `courtlistener` | Earlier federal suits or claims? |
| Money and politics | `fec`, `edgar` | Where were they, and with whom, when they donated or filed? |

**On each record, show:**
1. The record's own name as written (`fullname`), not the searched name. "ROBERT J VANCE" vs "Robert Vance" is the first namesake check.
2. `roles`: licence holder, president, registered agent, company officer…
3. The organisation (`business`, `carrier`, `filer`) and the place (`location`, `county`; `business_location` where the business is elsewhere).
4. Identifiers: licence number, NPI, USDOT, CIK, registry number, `year_of_birth` (TX Medical Board).
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
- CourtListener limits: [free.law issue #7200](https://github.com/freelawproject/courtlistener/issues/7200), [third-party guide](https://www.vaquill.ai/blog/how-to-use-courtlistener-api)
- FEC use restriction: [FEC: sale or use of contributor information](https://www.fec.gov/updates/sale-or-use-contributor-information), [11 CFR 104.15](https://www.law.cornell.edu/cfr/text/11/104.15)
- Records: [Socrata discovery API](https://dev.socrata.com/docs/other/discovery), [Socrata app tokens](https://dev.socrata.com/docs/app-tokens), [TDLR All Licenses](https://data.texas.gov/d/7358-krk7), [Colorado DORA licences](https://data.colorado.gov/d/7s5z-vewr), [Illinois IDFPR licences](https://illinois-edp.data.socrata.com/d/pzzh-kp68), [WA L&I contractors](https://data.wa.gov/d/m8qx-ubtq), [NY active corporations](https://data.ny.gov/d/n9v6-gdp6), [Oregon active businesses](https://data.oregon.gov/d/tckn-sxa6), [CT principals](https://data.ct.gov/d/ka36-64k6), [FMCSA company census](https://catalog.data.gov/dataset/company-census-file), [FMCSA QCMobile](https://mobile.fmcsa.dot.gov/QCDevsite/home), [DCA open data](https://www.dca.ca.gov/data/index.shtml), [FAA releasable airmen](https://www.faa.gov/licenses_certificates/airmen_certification/releasable_airmen_download), [OpenCorporates terms](https://opencorporates.com/terms-of-use-2/)
- Rejected: [ORCID API limits](https://info.orcid.org/ufaqs/what-are-the-api-limits/), [ORCID public API terms](https://info.orcid.org/public-client-terms-of-service/), [npm open-source terms](https://docs.npmjs.com/policies/open-source-terms), [BrokerCheck permitted uses](https://www.finra.org/investors/investing/working-with-investment-professional/about-brokercheck/permitted-uses)
- [Maltego plans](https://docs.maltego.com/support/solutions/articles/15000036759-maltego-products-and-plans)
- [IntelTechniques tools](https://inteltechniques.com/tools/)
- [OSINT Industries pricing](https://www.techjockey.com/detail/osint-industries)
- [Skopenow comparison](https://www.skopenow.com/people-and-business-search-comparison)
- [holehe vs user-scanner](https://dev.to/the_king89/rip-holehe-why-user-scanner-is-the-new-king-of-email-osint-2cff)
