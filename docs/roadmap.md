# Roadmap

## M0: research and design (in progress)
- Research: [tools](research/tools.md), [pain points](research/pain-points.md), [legal](research/legal.md), [geolocation](research/geolocation.md)
- [Practitioner interview](research/practitioner-interview.md)
- [Design brief](design-brief.md): 4 concepts → pick one → full prototype

## M1: search engine (CLI, no UI) ✅
- `tessera search SEED... --case NAME --purpose TEXT`. A new case can't start without a purpose.
- Sources (`tessera/sources/`):
  - Maigret: top 500 sites, with profile parsing
  - WhatsMyName: about 690 sites
  - user-scanner: email registrations, passive modules only
  - libphonenumber: offline
- Scoring (`tessera/match.py`): hand-set Fellegi-Sunter-style weights with ICD 203 verdicts, and a reason behind every point. It also handles nicknames, Gravatar email hashes, linked accounts, and display names that just repeat the username.
- Evidence: raw page source plus a Playwright screenshot and rendered HTML of likely matches, all SHA-256-named, with the audit log in per-case SQLite.
- Live test: username + name + location seeds take about 40 s, with about 1,200 site checks across both engines.

**M1 hardening (done)**
- ✅ **Username rarity** comes from the measured hit rate across sites. `nasa` is taken on 469 of 788 sites, so it's common.
- ✅ **Two-identifier rule:** a handle alone can't lift a profile above "roughly even chance". This stops a namesake who holds the same rare handle from rating as "likely".
- ✅ **Name matching** has graded tiers (similar / part of). A shared word that is just the handle counts for nothing, so "Nasa Nguyen" isn't evidence for NASA.
- ✅ **Locations** are geocoded (`tessera/geo.py`, Nominatim, cached) and compared by distance tier. Placeholders like "Unknown" and "Earth" are dropped first: there is a real village called Unknown in India.
- ✅ **Proxy routing** (`--proxy` / `TESSERA_PROXY`) covers every network call.
- ✅ **Self-check** covers the case store end to end (purpose gate, evidence hashes, engine merging, pivots).
- ✅ **Email checks audited.** All 220 user-scanner modules have been read and classified (`NOTIFIES` / `AUDITED_SILENT` in `tessera/sources/user_scanner.py`, one reason per module):
  - 51 flagged loud upstream
  - 42 more never run: password login attempts, sign-ups that only a captcha stops, reset and recovery flows
  - 127 audited silent

  `uv run python -m tessera.sources.user_scanner` re-checks coverage after an upgrade, and the silent list is only trusted for the audited release. The proxy also now reaches the 172 modules that open their own connections.
- ✅ **WhatsMyName validated** against each site's known account and a nonsense handle (`scripts/validate_wmn.py`). Redirects are now handled the way WMN's own checker does:
  - known accounts found: 424 → 447
  - both checks right: 335 → 348
  - false "found" on nonsense: 0
- ✅ **Geocoding hardened:**
  - US state codes and metro nicknames ("AZ" was Azerbaijan)
  - falls back to the part after the last comma
  - a joke-location stoplist
  - a street or shop hit only counts if the string has a number
  - ambiguous names ("Washington", "Portland") keep only the country; "Georgia" stays unplaced

**Still open**
- Recognise acronyms, so "NASA" matches "National Aeronautics and Space Administration".
- Five email modules (Facebook, Amazon, Patreon, Vedantu, HackTheBox) are off only because a notification couldn't be ruled out. Testing each against an account the investigator owns could bring them back.
- About 100 WhatsMyName sites block automated checks (Cloudflare etc.), and some entries are stale (Mastodon titles, Fiverr status codes). Report those fixes upstream to WMN.

## M2: app UI
- Local FastAPI server, results streamed live; frontend built from the chosen design prototype.

## M3: photo geolocation
- EXIF → GeoCLIP + OCR + script ID → local VLM rerank (Ollama) → ranked hypotheses with radius → investigator-triggered verification (Overpass, Mapillary, sun position). See [geolocation.md](research/geolocation.md).

## M4: records and reports
- OpenFEC, SEC EDGAR, CourtListener, Wayback CDX, plus YouTube, Bluesky, Mastodon and GitHub APIs.
- Report builder: BLUF drafted by a local LLM with enforced citations, ICD 203 language, hash manifest, PDF via Playwright, FCRA mode.

## M5: ship
- One-command install (`uvx tessera`).
- Landing page with a fictional-data demo on GitHub Pages.
- Transfer the repo to Laura.
